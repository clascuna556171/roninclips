"""
Stream moment detection: finds chat floods and audio spikes in a VOD.

Signals are built per second, scored against their own recent baseline
(median + MAD), combined, and the strongest peaks become clip windows.
Everything except `audio_loudness()` is pure and unit-tested.
"""
import json
import re
import subprocess
from collections import Counter

import numpy as np

# ── Tuning constants (owner-approved 2026-11-18; lag + window re-tuned on jasontheween VOD 2932190650
#    against two viewer clips: chat reacted 0-5s after the audio, and fixed windows cut long events short) ──
CHAT_WEIGHT = 0.6
AUDIO_WEIGHT = 0.4
CHAT_LAG_S = 3           # chat reacts this many seconds after the event
CHAT_SMOOTH_S = 5
AUDIO_SMOOTH_S = 2
BASELINE_S = 120         # rolling baseline length
BASELINE_GAP_S = 10      # ignore the seconds right before t, so a ramp-up doesn't hide the spike
MIN_BASELINE_S = 30      # below this, fall back to the whole-VOD baseline
Z_CAP = 10.0             # one signal can't drown the other
MIN_GAP_S = 90           # minimum distance between picked peaks
PRE_ROLL_S = 15         # window starts this long before the peak
MIN_CLIP_S = 30
MAX_CLIP_S = 60
KEEP_RATIO = 0.35        # window keeps going while activity stays >= this share of the peak
TAIL_S = 5               # extra seconds after activity drops
CHAT_FLOOR = 0.5         # msgs/s: minimum spread so a quiet chat's +1 msg isn't a "spike"
AUDIO_FLOOR_DB = 1.0
SILENCE_DB = -50.0       # quieter seconds (muted intro / BRB) are left out of the audio baseline
AUDIO_RATE = 8000        # Hz, plenty for loudness

_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)


def normalize_message(text):
    """'KEKW KEKW kekw!!!' -> 'kekw'; used to spot copy-paste spam."""
    words = _PUNCT_RE.sub(' ', str(text or '').lower()).split()
    out = []
    for w in words:
        if not out or out[-1] != w:
            out.append(w)
    return ' '.join(out)


def load_chat(path):
    """Read chat.jsonl -> list of (t_seconds, message). Bad lines are skipped."""
    messages = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                messages.append((float(row['t']), str(row.get('message', ''))))
            except (ValueError, KeyError, TypeError):
                continue
    return messages


def chat_series(messages, duration):
    """
    Per-second chat activity: message count plus the size of the biggest
    group of identical (normalized) messages, so emote spam counts double.
    Returns (activity, raw_counts), both float arrays of length `duration`.
    """
    duration = int(duration)
    counts = np.zeros(duration, dtype=float)
    per_second = [[] for _ in range(duration)]
    for t, msg in messages:
        s = int(t)
        if 0 <= s < duration:
            counts[s] += 1
            norm = normalize_message(msg)
            if norm:
                per_second[s].append(norm)
    dup = np.zeros(duration, dtype=float)
    for s, msgs in enumerate(per_second):
        if len(msgs) >= 2:
            top = Counter(msgs).most_common(1)[0][1]
            if top >= 2:
                dup[s] = top
    return counts + dup, counts


def smooth(x, width):
    """Centered moving average; keeps the length. Edges are padded with the edge value,
    not zeros, so a dB signal (negative) doesn't look loud at the start/end."""
    x = np.asarray(x, dtype=float)
    width = int(width)
    if width <= 1 or len(x) == 0:
        return x.copy()
    left = (width - 1) // 2
    padded = np.pad(x, (left, width - 1 - left), mode='edge')
    return np.convolve(padded, np.ones(width) / width, mode='valid')


def baseline_values(win, ignore_below=None):
    """The part of a window that counts toward a baseline (drops silence when asked)."""
    if ignore_below is None:
        return win
    return win[win >= ignore_below]


def rolling_zscore(x, floor, rel_floor=0.0, baseline_s=BASELINE_S, gap_s=BASELINE_GAP_S,
                   min_baseline_s=MIN_BASELINE_S, ignore_below=None):
    """
    How far each second sits above its preceding baseline, in robust z units
    (median / 1.4826*MAD). Only upward spikes count: result is clipped to [0, Z_CAP].
    `floor` is the minimum spread, so flat signals don't explode; `rel_floor` adds a
    minimum spread proportional to the baseline (for counts, not for dB).
    `ignore_below` leaves values under it out of the baseline, so talking after a
    silent stretch isn't scored against the silence.
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    z = np.zeros(n, dtype=float)
    if n == 0:
        return z
    g_vals = baseline_values(x, ignore_below)
    if len(g_vals) == 0:
        g_vals = x
    g_med = float(np.median(g_vals))
    g_mad = float(np.median(np.abs(g_vals - g_med)))
    for t in range(n):
        lo, hi = max(0, t - baseline_s), max(0, t - gap_s)
        win = baseline_values(x[lo:hi], ignore_below)
        if len(win) >= min_baseline_s:
            med = float(np.median(win))
            mad = float(np.median(np.abs(win - med)))
        else:
            med, mad = g_med, g_mad
        scale = max(1.4826 * mad, floor, rel_floor * abs(med))
        z[t] = (x[t] - med) / scale
    return np.clip(z, 0.0, Z_CAP)


def loudness_from_pcm(stream, sample_rate=AUDIO_RATE, chunk_seconds=60):
    """Read mono s16le PCM from a binary stream -> RMS loudness in dBFS per second."""
    bytes_per_sec = sample_rate * 2
    out = []
    leftover = b''
    while True:
        data = stream.read(bytes_per_sec * chunk_seconds)
        if not data:
            break
        data = leftover + data
        usable = len(data) - (len(data) % bytes_per_sec)
        leftover = data[usable:]
        if usable:
            samples = np.frombuffer(data[:usable], dtype='<i2').astype(np.float32).reshape(-1, sample_rate)
            rms = np.sqrt(np.mean(samples * samples, axis=1)) / 32768.0
            out.extend((20.0 * np.log10(rms + 1e-6)).tolist())
    if len(leftover) >= sample_rate:  # keep a trailing partial second if it's at least half a second
        samples = np.frombuffer(leftover[:len(leftover) - len(leftover) % 2], dtype='<i2').astype(np.float32)
        rms = float(np.sqrt(np.mean(samples * samples))) / 32768.0
        out.append(20.0 * np.log10(rms + 1e-6))
    return np.asarray(out, dtype=float)


def audio_loudness(media_path, sample_rate=AUDIO_RATE):
    """Stream the audio track through FFmpeg (constant memory) and return dBFS per second."""
    proc = subprocess.Popen(
        ['ffmpeg', '-v', 'error', '-i', media_path, '-vn', '-ac', '1', '-ar', str(sample_rate),
         '-f', 's16le', '-'],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    try:
        loud = loudness_from_pcm(proc.stdout, sample_rate)
    finally:
        proc.stdout.close()
        proc.wait()
    if len(loud) == 0:
        raise RuntimeError('Could not read any audio for moment detection.')
    return loud


def combine_scores(audio_z, chat_z=None, lag_s=CHAT_LAG_S):
    """Weighted score per second. Chat is shifted earlier by `lag_s` to line up with the event."""
    audio_z = np.asarray(audio_z, dtype=float)
    if chat_z is None:
        return audio_z.copy()
    n = len(audio_z)
    shifted = np.zeros(n, dtype=float)
    chat_z = np.asarray(chat_z, dtype=float)
    src = chat_z[lag_s:lag_s + n]
    shifted[:len(src)] = src
    return CHAT_WEIGHT * shifted + AUDIO_WEIGHT * audio_z


def pick_peaks(score, count, min_gap_s=MIN_GAP_S):
    """Greedy non-max suppression: highest seconds first, at least `min_gap_s` apart, score > 0."""
    score = np.asarray(score, dtype=float)
    picked = []
    for t in np.argsort(-score, kind='stable'):
        if len(picked) >= count or score[t] <= 0:
            break
        if all(abs(int(t) - p) >= min_gap_s for p in picked):
            picked.append(int(t))
    return picked


def clip_window(score_s, peak, duration, pre=PRE_ROLL_S, min_len=MIN_CLIP_S, max_len=MAX_CLIP_S,
                keep=KEEP_RATIO, tail=TAIL_S):
    """
    Adaptive window: start `pre` seconds before the peak, then follow the (smoothed) score
    while it stays >= `keep` x the peak's value, plus a short `tail`. Length is clamped to
    [min_len, max_len]; near the VOD end the start shifts back instead of shrinking.
    """
    start = max(0, peak - pre)
    threshold = keep * float(score_s[peak])
    end = peak
    while (threshold > 0 and end + 1 < duration and (end + 1 - start) < max_len
           and score_s[end + 1] >= threshold):
        end += 1
    end = min(duration, start + max_len, max(end + tail, start + min_len))
    if end - start < min_len:
        start = max(0, end - min_len)
    return float(start), float(end)


def describe(moment):
    """One-line human reason, e.g. 'Chat spiked 8x (142 msgs in 10s) + audio peak (+9 dB)'."""
    parts = []
    if moment.get('chat_msgs_10s') is not None and moment.get('chat_z', 0) >= 1:
        ratio = moment.get('chat_ratio')
        ratio_txt = f"{ratio:.0f}x " if ratio and ratio >= 1.5 else ''
        parts.append(f"Chat spiked {ratio_txt}({moment['chat_msgs_10s']} msgs in 10s)")
    if moment.get('audio_z', 0) >= 1:
        parts.append(f"audio peak (+{moment['audio_db_above']:.0f} dB)")
    if not parts:
        return 'Strongest chat/audio activity in this part of the VOD'
    text = ' + '.join(parts)
    return text[0].upper() + text[1:]


def detect_moments_from_signals(loudness_db, messages, count):
    """
    Core detector. `loudness_db`: dBFS per second (defines the VOD length).
    `messages`: list of (t, text) or None when there's no chat (Kick / local files).
    Returns up to `count` moments sorted by score (best first).
    """
    loud = np.asarray(loudness_db, dtype=float)
    duration = len(loud)
    if duration == 0 or count <= 0:
        return []

    audio_s = smooth(loud, AUDIO_SMOOTH_S)
    audio_z = rolling_zscore(audio_s, AUDIO_FLOOR_DB, ignore_below=SILENCE_DB)
    heard = baseline_values(audio_s, SILENCE_DB)
    if len(heard) == 0:
        heard = audio_s

    chat_z = raw_counts = chat_s = None
    has_chat = bool(messages)
    if has_chat:
        # Pad by the lag so reactions after the last video second still line up
        activity, raw_counts = chat_series(messages, duration + CHAT_LAG_S)
        chat_s = smooth(activity, CHAT_SMOOTH_S)
        chat_z = rolling_zscore(chat_s, CHAT_FLOOR, rel_floor=0.25)

    score = combine_scores(audio_z, chat_z)
    score_s = smooth(score, CHAT_SMOOTH_S)
    moments = []
    for peak in pick_peaks(score, count):
        start, end = clip_window(score_s, peak, duration)
        lo, hi = max(0, peak - BASELINE_S), max(0, peak - BASELINE_GAP_S)
        base_win = baseline_values(audio_s[lo:hi], SILENCE_DB)
        base_db = float(np.median(base_win)) if len(base_win) else float(np.median(heard))
        m = {
            'peak': float(peak),
            'start': start,
            'end': end,
            'score': round(float(score[peak]), 2),
            'audio_z': round(float(audio_z[peak]), 2),
            'audio_db_above': round(max(0.0, float(audio_s[peak]) - base_db), 1),
            'chat_z': None,
            'chat_msgs_10s': None,
            'chat_ratio': None,
        }
        if has_chat:
            c = peak + CHAT_LAG_S
            m['chat_z'] = round(float(chat_z[c]), 2)
            m['chat_msgs_10s'] = int(raw_counts[max(0, c - 5):c + 5].sum())
            clo, chi = max(0, c - BASELINE_S), max(0, c - BASELINE_GAP_S)
            base_rate = float(np.median(chat_s[clo:chi])) if chi > clo else float(np.median(chat_s))
            rate = m['chat_msgs_10s'] / 10.0
            m['chat_ratio'] = round(rate / base_rate, 1) if base_rate > 0 else None
        else:
            m['chat_z'] = 0.0
        m['summary'] = describe(m)
        moments.append(m)
    return moments


def drop_clipped(candidates, windows):
    """Candidates whose peak isn't inside an already-clipped [start, end] span (e.g. live clips)."""
    spans = [(float(s), float(e)) for s, e in windows or ()]
    return [m for m in candidates if not any(s <= m['peak'] <= e for s, e in spans)]


def detect_moments(media_path, chat_path, count):
    """Convenience wrapper: real audio + optional chat.jsonl."""
    loud = audio_loudness(media_path)
    messages = load_chat(chat_path) if chat_path else None
    return detect_moments_from_signals(loud, messages, count), len(loud), bool(messages)
