"""
RoninClips — VOD link import (Twitch / Kick).

Downloads a stream VOD with yt-dlp and, for Twitch, its chat log with
TwitchDownloaderCLI. Chat is saved next to the video as JSON Lines, one
message per line:  {"t": <seconds from VOD start>, "author": str, "message": str}

Kick chat is not fetched: Kick has no public chat-replay API and its
internal endpoints sit behind bot protection, so Kick imports are video only.

Every expected failure raises VodImportError with a plain-English message.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time

TWITCH_VOD_RE = re.compile(r'^https?://(?:www\.|m\.)?twitch\.tv/videos/(\d+)', re.I)
KICK_VOD_RE = re.compile(
    r'^https?://(?:www\.)?kick\.com/[\w-]+/videos/'
    r'([0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})', re.I)

# Cap downloads at 1080p: source-quality 10-hour VODs can run to tens of GB.
VIDEO_FORMAT = 'bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b'
# Sparse (watchlist) mode: scan an audio-only copy, then fetch only the clip windows.
AUDIO_FORMAT = 'ba/bestaudio'
# Clip windows must come from ONE playlist: Twitch's audio-only and video playlists can sit ~10 s apart,
# so merging them (bv+ba) would put the sound out of sync. Twitch video formats already carry audio.
SECTION_FORMAT = 'b[height<=1080]/b'
SECTION_PAD_S = 15          # Twitch cuts snap to ~10 s segments; pad so the window is always inside
ALIGN_RATE = 8000           # Hz used to match a section's sound against the scanned audio
ALIGN_MIN_MATCH = 0.5       # below this the sound match is not trusted
DISK_MARGIN = 1.2                       # need estimated size + 20%
FALLBACK_BITRATE_BPS = 8_000_000        # used when yt-dlp can't estimate size
PROGRESS_PREFIX = 'RC_PROGRESS'

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def _log(msg):
    """Print and flush: the engine's stdout is redirected to a log file the dashboard polls."""
    print(msg, flush=True)


class VodImportError(Exception):
    """An expected import failure with a message meant for the dashboard."""


def parse_source_url(url):
    """Return (platform, vod_id) for a supported VOD link, else None."""
    url = (url or '').strip()
    m = TWITCH_VOD_RE.match(url)
    if m:
        return 'twitch', m.group(1)
    m = KICK_VOD_RE.match(url)
    if m:
        return 'kick', m.group(1).lower()
    return None


def vod_dir(video_id, storage_app=None):
    storage_app = storage_app or os.path.join(ROOT_DIR, 'storage', 'app')
    return os.path.join(storage_app, 'vods', str(video_id))


# ─── Error mapping ───────────────────────────────────────────────────────────

def friendly_error(output, platform):
    """Turn yt-dlp / CLI output into one clear sentence."""
    text = (output or '').lower()
    name = 'Twitch' if platform == 'twitch' else 'Kick'
    if 'ffmpeg' in text and 'not found' in text:
        return "FFmpeg was not found on PATH; yt-dlp needs it to save the VOD."
    if any(k in text for k in ('subscriber', 'sub-only', 'subs only', 'requires a subscription',
                               'only available to subscribers')):
        return (f"This {name} VOD is subscriber-only. RoninClips can only import public VODs.")
    if any(k in text for k in ('geo restrict', 'geo-restrict', 'available in your country',
                               'not available from your location', 'region-locked',
                               'region locked', 'in your region')):
        return f"This {name} VOD is region-locked and can't be downloaded from your location."
    if any(k in text for k in ('does not exist', 'http error 404', 'not found', 'has been deleted',
                               'video is unavailable', 'no longer available', 'removed')):
        return (f"This {name} VOD wasn't found. It may have been deleted or expired, "
                f"or the link is wrong.")
    if 'http error 403' in text or 'forbidden' in text:
        if platform == 'kick':
            return ("Kick blocked the download (HTTP 403). Try again later, or update yt-dlp "
                    "(pip install -U \"yt-dlp[default,curl-cffi]\").")
        return f"{name} refused the download (HTTP 403). The VOD may be private or restricted."
    if any(k in text for k in ('timed out', 'connection', 'getaddrinfo', 'network', 'temporary failure')):
        return f"Network error while downloading from {name}. Check your connection and press Retry."
    # Fall back to the last ERROR line, without the traceback noise.
    for line in reversed((output or '').splitlines()):
        if 'ERROR' in line:
            return 'Download failed: ' + line.split('ERROR:', 1)[-1].strip()[:300]
    return f"Download from {name} failed for an unknown reason. Press Retry, or check the console log."


# ─── Size estimate & disk check ──────────────────────────────────────────────

def estimate_size_bytes(info):
    """Best-effort size estimate from yt-dlp's -J metadata."""
    for key in ('filesize', 'filesize_approx'):
        if info.get(key):
            return int(info[key])
    total = 0
    for fmt in info.get('requested_formats') or []:
        size = fmt.get('filesize') or fmt.get('filesize_approx')
        if size:
            total += int(size)
    if total:
        return total
    duration = info.get('duration') or 0
    tbr = info.get('tbr')  # kbit/s
    bps = tbr * 1000 if tbr else FALLBACK_BITRATE_BPS
    return int(duration * bps / 8)


def check_disk_space(target_dir, needed_bytes, disk_usage=shutil.disk_usage):
    """Raise VodImportError if the drive can't hold the download plus margin."""
    os.makedirs(target_dir, exist_ok=True)
    free = disk_usage(target_dir).free
    required = int(needed_bytes * DISK_MARGIN)
    if free < required:
        raise VodImportError(
            f"Not enough disk space: this VOD needs about {required / 1e9:.1f} GB "
            f"(estimate + 20%), but only {free / 1e9:.1f} GB is free on that drive.")
    return free, required


# ─── yt-dlp ──────────────────────────────────────────────────────────────────

def _ytdlp_base(fmt=VIDEO_FORMAT):
    return [sys.executable, '-m', 'yt_dlp', '--no-playlist', '--no-warnings', '-f', fmt]


def probe(url, platform, fmt=VIDEO_FORMAT):
    """Fetch metadata (title, duration, size) without downloading."""
    try:
        proc = subprocess.run(_ytdlp_base(fmt) + ['-J', url], capture_output=True, stdin=subprocess.DEVNULL, text=True,
                              encoding='utf-8', errors='replace', timeout=180)
    except FileNotFoundError:
        raise VodImportError("yt-dlp is not installed. Run: pip install \"yt-dlp[default,curl-cffi]\"")
    except subprocess.TimeoutExpired:
        raise VodImportError(f"Timed out reading the VOD info. Check your connection and press Retry.")
    if proc.returncode != 0:
        if 'No module named yt_dlp' in proc.stderr:
            raise VodImportError("yt-dlp is not installed. Run: pip install \"yt-dlp[default,curl-cffi]\"")
        raise VodImportError(friendly_error(proc.stderr, platform))
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise VodImportError("yt-dlp returned unreadable VOD info. Try updating yt-dlp.")


def parse_progress_line(line):
    """Parse our --progress-template line into a dict, or None."""
    if not line.startswith(PROGRESS_PREFIX):
        return None
    parts = [p.strip() for p in line[len(PROGRESS_PREFIX):].strip().split('|')]
    if len(parts) < 5:
        return None
    pct_text, total, total_est, speed, eta = parts[:5]
    try:
        pct = float(pct_text.rstrip('%'))
    except ValueError:
        return None
    unknown = ('', 'NA', 'N/A', 'Unknown')
    size = total if total not in unknown else total_est
    return {
        'percent': pct,
        'size': '' if size in unknown else size,
        'speed': '' if speed in unknown else speed,
        'eta': '' if eta in unknown else eta,
    }


def format_progress(p, label='VOD'):
    text = f"Downloading {label}: {p['percent']:.1f}%"
    if p['size']:
        text += f" of {p['size']}"
    if p['speed']:
        text += f" at {p['speed']}"
    if p['eta']:
        text += f", ETA {p['eta']}"
    return text


def download_video(url, out_dir, platform, log=_log, fmt=VIDEO_FORMAT, name='vod', label='VOD'):
    """Download the VOD into out_dir/{name}.mp4 with live progress lines. Resumes .part files."""
    template = (f"download:{PROGRESS_PREFIX} %(progress._percent_str)s|%(progress._total_bytes_str)s|"
                f"%(progress._total_bytes_estimate_str)s|%(progress._speed_str)s|%(progress._eta_str)s")
    cmd = _ytdlp_base(fmt) + [
        '--newline', '--progress-template', template,
        '--retries', '10', '--fragment-retries', '10', '--continue',
        '--concurrent-fragments', '4',
        '--merge-output-format', 'mp4', '--remux-video', 'mp4',
        '-o', os.path.join(out_dir, f'{name}.%(ext)s'),
        url,
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            text=True, encoding='utf-8', errors='replace', bufsize=1)
    tail = []
    last_pct, last_time = -1.0, 0.0
    for raw in proc.stdout:
        line = raw.rstrip()
        p = parse_progress_line(line)
        if p:
            now = time.time()
            # Throttle: every whole percent or every 10 s, so 10-hour logs stay small.
            if p['percent'] >= 100 or p['percent'] - last_pct >= 1 or now - last_time >= 10:
                log(format_progress(p, label))
                last_pct, last_time = p['percent'], now
            continue
        if line:
            tail.append(line)
            tail = tail[-40:]
            if 'ERROR' in line or '[Merger]' in line or '[VideoRemuxer]' in line or 'Retrying' in line:
                log(f"  yt-dlp: {line}")
    proc.wait()
    if proc.returncode != 0:
        raise VodImportError(friendly_error('\n'.join(tail), platform))
    path = os.path.join(out_dir, f'{name}.mp4')
    if not os.path.exists(path):
        raise VodImportError("Download finished but the video file is missing. Press Retry.")
    return path


def probe_start_time(path):
    """Container start timestamp in seconds (Twitch HLS VODs often start well above 0)."""
    try:
        out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=start_time',
                              '-of', 'default=nw=1:nk=1', path], capture_output=True, text=True,
                             stdin=subprocess.DEVNULL, timeout=60).stdout.strip()
        return float(out)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0.0


def normalize_start(path, log=_log, disk_usage=shutil.disk_usage):
    """
    Losslessly remux so timestamps start at 0. Then chat `t` = seconds into vod.mp4 for every tool,
    and ffprobe reports the real duration. Returns the original start offset in seconds.
    Needs room for a second copy; if there isn't, keeps the file as is and warns.
    """
    offset = probe_start_time(path)
    if offset <= 0.5:
        return offset
    size = os.path.getsize(path)
    if disk_usage(os.path.dirname(path)).free < size * 1.05:
        log(f"⚠️ VOD starts at {offset:.1f}s (stream timestamps) and there isn't room to re-time it. "
            f"Keeping it as is: chat times are measured from the first frame.")
        return offset
    log(f"Re-timing VOD to start at 0s (was {offset:.1f}s, lossless copy)...")
    tmp = path + '.zero.mp4'
    proc = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', path, '-map', '0', '-c', 'copy',
                           '-avoid_negative_ts', 'make_zero', '-movflags', '+faststart', tmp],
                          capture_output=True, text=True, stdin=subprocess.DEVNULL,
                          encoding='utf-8', errors='replace')
    if proc.returncode != 0 or not os.path.exists(tmp):
        if os.path.exists(tmp):
            os.remove(tmp)
        log(f"⚠️ Could not re-time VOD ({proc.stderr.strip()[-200:]}). Keeping the original.")
        return offset
    os.replace(tmp, path)
    return offset


# ─── Twitch chat ─────────────────────────────────────────────────────────────

def find_twitch_cli():
    exe = 'TwitchDownloaderCLI.exe' if os.name == 'nt' else 'TwitchDownloaderCLI'
    local = os.path.join(ROOT_DIR, 'bin', 'TwitchDownloaderCLI', exe)
    if os.path.exists(local):
        return local
    return shutil.which('TwitchDownloaderCLI')


def normalize_twitch_chat(raw):
    """TwitchDownloader chat JSON -> sorted list of {t, author, message}."""
    out = []
    for c in raw.get('comments') or []:
        commenter = c.get('commenter') or {}
        author = commenter.get('display_name') or commenter.get('name') or ''
        msg = c.get('message') or {}
        body = msg.get('body')
        if body is None:
            body = ''.join((f.get('text') or '') for f in msg.get('fragments') or [])
        try:
            t = round(float(c.get('content_offset_seconds', 0)), 3)
        except (TypeError, ValueError):
            continue
        out.append({'t': t, 'author': author, 'message': body})
    out.sort(key=lambda m: m['t'])
    return out


def write_chat_jsonl(messages, path):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        for m in messages:
            f.write(json.dumps(m, ensure_ascii=False) + '\n')
    os.replace(tmp, path)


def download_twitch_chat(vod_id, out_dir, log=_log):
    """Download and normalize Twitch chat. Returns (path, count). Raises VodImportError."""
    cli = find_twitch_cli()
    if not cli:
        raise VodImportError("TwitchDownloaderCLI was not found in bin/TwitchDownloaderCLI/, "
                             "so chat was skipped.")
    raw_path = os.path.join(out_dir, 'chat_raw.json')
    cmd = [cli, 'chatdownload', '--id', str(vod_id), '-o', raw_path,
           '--collision', 'Overwrite', '--banner', 'false']
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            text=True, encoding='utf-8', errors='replace', bufsize=1)
    tail, last_time = [], 0.0
    for raw in proc.stdout:
        line = raw.strip()
        if not line:
            continue
        tail = (tail + [line])[-20:]
        now = time.time()
        if now - last_time >= 10:
            log(f"  chat: {line}")
            last_time = now
    proc.wait()
    if proc.returncode != 0 or not os.path.exists(raw_path):
        raise VodImportError(friendly_error('\n'.join(tail), 'twitch').replace('Download failed', 'Chat download failed'))
    with open(raw_path, encoding='utf-8') as f:
        raw = json.load(f)
    messages = normalize_twitch_chat(raw)
    path = os.path.join(out_dir, 'chat.jsonl')
    write_chat_jsonl(messages, path)
    os.remove(raw_path)
    return path, len(messages)


# ─── Orchestration ───────────────────────────────────────────────────────────

def fetch_chat(platform, vod_id, out_dir, log=_log, without='the video'):
    """Download (or reuse) the chat log. Returns (status, path, count); status is saved/failed/unavailable."""
    chat_path = os.path.join(out_dir, 'chat.jsonl')
    if platform == 'kick':
        log("Kick chat: not available (Kick has no reliable chat-replay source). Video only.")
        return 'unavailable', chat_path, None
    if os.path.exists(chat_path):
        with open(chat_path, encoding='utf-8') as f:
            chat_count = sum(1 for _ in f)
        log(f"Downloading chat: already saved ({chat_count} messages), skipping.")
        return 'saved', chat_path, chat_count
    log("Downloading chat log from Twitch...")
    try:
        chat_path, chat_count = download_twitch_chat(vod_id, out_dir, log)
        log(f"Chat saved: {chat_count} messages -> {chat_path}")
        return 'saved', chat_path, chat_count
    except VodImportError as e:
        log(f"⚠️ CHAT WARNING: {e} Continuing with {without} only.")
    except (OSError, ValueError) as e:
        log(f"⚠️ CHAT WARNING: chat log could not be saved ({e}). Continuing with {without} only.")
    return 'failed', chat_path, None

def import_vod(video_id, url, storage_app=None, log=_log):
    """
    Download a VOD (and Twitch chat) for long_videos.id = video_id.
    Safe to re-run: a finished video or chat file is reused, a partial download resumes.
    Returns dict(path, title, platform, vod_id, chat_status, chat_path, chat_count).
    """
    parsed = parse_source_url(url)
    if not parsed:
        raise VodImportError("Unsupported link. Paste a Twitch VOD (twitch.tv/videos/…) or Kick VOD link.")
    platform, vod_id = parsed
    out_dir = vod_dir(video_id, storage_app)
    os.makedirs(out_dir, exist_ok=True)
    meta_path = os.path.join(out_dir, 'meta.json')
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path, encoding='utf-8') as f:
            meta = json.load(f)

    video_path = os.path.join(out_dir, 'vod.mp4')
    if meta.get('video_complete') and os.path.exists(video_path):
        log(f"Downloading VOD: already downloaded ({os.path.getsize(video_path) / 1e9:.2f} GB), skipping.")
    else:
        log(f"Importing {platform.title()} VOD {vod_id}: reading info...")
        info = probe(url, platform)
        meta.update({'title': info.get('title') or f'{platform}_{vod_id}',
                     'duration': info.get('duration'), 'uploader': info.get('uploader')})
        est = estimate_size_bytes(info)
        free, required = check_disk_space(out_dir, est)
        log(f"Title: {meta['title']} | duration {int(meta['duration'] or 0) // 60} min | "
            f"estimated {est / 1e9:.1f} GB, {free / 1e9:.0f} GB free")
        log("Downloading VOD: 0.0%")
        video_path = download_video(url, out_dir, platform, log)
        meta['source_start_offset'] = normalize_start(video_path, log)
        meta['video_complete'] = True
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        log(f"Downloading VOD: 100.0% done ({os.path.getsize(video_path) / 1e9:.2f} GB)")

    chat_status, chat_path, chat_count = fetch_chat(platform, vod_id, out_dir, log)

    return {
        'path': video_path,
        'title': meta.get('title') or f'{platform}_{vod_id}',
        'platform': platform,
        'vod_id': vod_id,
        'chat_status': chat_status,
        'chat_path': chat_path if chat_status == 'saved' else None,
        'chat_count': chat_count,
    }


# ─── Sparse import (watchlist): scan audio + chat, then fetch only the clip windows ──────────

def _save_meta(meta_path, meta):
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def import_vod_sparse(video_id, url, storage_app=None, log=_log):
    """
    Download what moment detection needs, not the video: the audio-only stream (~1.5 GB for 16 h
    instead of ~47 GB at 1080p60) and the Twitch chat log. If the audio-only stream can't be had,
    fall back to chat alone. Safe to re-run: finished files are reused.
    Returns dict(path (audio file or None), title, duration, platform, vod_id, audio_status,
    chat_status, chat_path, chat_count).
    """
    parsed = parse_source_url(url)
    if not parsed:
        raise VodImportError("Unsupported link. Paste a Twitch VOD (twitch.tv/videos/…) or Kick VOD link.")
    platform, vod_id = parsed
    out_dir = vod_dir(video_id, storage_app)
    os.makedirs(out_dir, exist_ok=True)
    meta_path = os.path.join(out_dir, 'meta.json')
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path, encoding='utf-8') as f:
            meta = json.load(f)

    audio_path = os.path.join(out_dir, 'audio.mp4')
    audio_status = 'saved'
    if meta.get('audio_complete') and os.path.exists(audio_path):
        log(f"Downloading audio: already downloaded ({os.path.getsize(audio_path) / 1e9:.2f} GB), skipping.")
    else:
        log(f"Importing {platform.title()} VOD {vod_id}: reading info (sparse: audio + chat first)...")
        try:
            info = probe(url, platform, AUDIO_FORMAT)
            meta.update({'title': info.get('title') or f'{platform}_{vod_id}',
                         'duration': info.get('duration'), 'uploader': info.get('uploader')})
            est = estimate_size_bytes(info)
            free, _ = check_disk_space(out_dir, est)
            log(f"Title: {meta['title']} | duration {int(meta['duration'] or 0) // 60} min | "
                f"audio-only scan copy ~{est / 1e9:.1f} GB, {free / 1e9:.0f} GB free")
            log("Downloading audio: 0.0%")
            download_video(url, out_dir, platform, log, fmt=AUDIO_FORMAT, name='audio', label='audio')
            meta['source_start_offset'] = normalize_start(audio_path, log)
            meta['audio_complete'] = True
            _save_meta(meta_path, meta)
            log(f"Downloading audio: 100.0% done ({os.path.getsize(audio_path) / 1e9:.2f} GB)")
        except VodImportError as e:
            audio_status = 'failed'
            audio_path = None
            log(f"⚠️ AUDIO WARNING: {e} Falling back to chat-only detection.")
            if not meta.get('duration'):
                info = probe(url, platform)  # raises if the VOD itself is gone
                meta.update({'title': info.get('title') or f'{platform}_{vod_id}',
                             'duration': info.get('duration'), 'uploader': info.get('uploader')})
                _save_meta(meta_path, meta)

    chat_status, chat_path, chat_count = fetch_chat(platform, vod_id, out_dir, log, without='the audio')
    if not audio_path and chat_status != 'saved':
        raise VodImportError("Neither the audio nor the chat of this VOD could be downloaded, "
                             "so there is nothing to scan for moments.")

    return {
        'path': audio_path,
        'title': meta.get('title') or f'{platform}_{vod_id}',
        'duration': meta.get('duration'),
        'platform': platform,
        'vod_id': vod_id,
        'audio_status': audio_status,
        'chat_status': chat_status,
        'chat_path': chat_path if chat_status == 'saved' else None,
        'chat_count': chat_count,
    }


def section_bounds(start, end, duration=None, pad=SECTION_PAD_S):
    """Whole-second window to request: the clip plus `pad` each side, clamped to the VOD."""
    lo = max(0, int(start) - pad)
    hi = int(end + 0.999) + pad
    if duration:
        hi = min(hi, int(duration + 0.999))
    return lo, max(hi, lo + 1)


def download_section(url, out_dir, name, start, end, platform, log=_log):
    """Download [start, end] seconds of the VOD at up to 1080p into out_dir/{name}.mp4."""
    path = os.path.join(out_dir, f'{name}.mp4')
    cmd = _ytdlp_base(SECTION_FORMAT) + [
        '--download-sections', f'*{int(start)}-{int(end)}', '--force-overwrites',
        '--retries', '10', '--fragment-retries', '10',
        '--merge-output-format', 'mp4', '--remux-video', 'mp4',
        '-o', os.path.join(out_dir, f'{name}.%(ext)s'), url,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL, text=True,
                              encoding='utf-8', errors='replace', timeout=1800)
    except subprocess.TimeoutExpired:
        raise VodImportError("Timed out downloading the clip window. Check your connection and press Retry.")
    if proc.returncode != 0 or not os.path.exists(path):
        raise VodImportError(friendly_error((proc.stderr or '') + '\n' + (proc.stdout or ''), platform))
    return path


# ─── Window from a VOD that is still recording ───────────────────────────────
# While a stream is live its VOD playlist has no end marker, so ffmpeg (and yt-dlp's
# --download-sections) treat it as a live stream: they start at the live edge and can't
# seek back. Instead read the playlist, fetch only the segments covering the window, and trim.

def parse_hls_playlist(text):
    """([{uri, start, duration}], ended) from a media playlist; start is seconds into the VOD."""
    segments, offset, duration = [], 0.0, None
    for line in (text or '').splitlines():
        line = line.strip()
        if line.startswith('#EXTINF:'):
            try:
                duration = float(line[8:].split(',', 1)[0])
            except ValueError:
                duration = None
        elif line and not line.startswith('#') and duration is not None:
            segments.append({'uri': line, 'start': offset, 'duration': duration})
            offset += duration
            duration = None
    return segments, '#EXT-X-ENDLIST' in (text or '')


def pick_segments(segments, start, end):
    """Segments overlapping [start, end] and how far into the first one the window begins.
    Nothing when the playlist doesn't reach `end` yet."""
    if not segments or segments[-1]['start'] + segments[-1]['duration'] < end:
        return [], 0.0
    picked = [s for s in segments if s['start'] + s['duration'] > start and s['start'] < end]
    return picked, (start - picked[0]['start']) if picked else 0.0


def _http_get(url, timeout=30):
    import urllib.request
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def download_live_section(url, out_dir, name, start, end, platform='twitch', log=_log, fetch=_http_get):
    """Download [start, end] seconds of a VOD that may still be recording into out_dir/{name}.mp4."""
    try:
        proc = subprocess.run(_ytdlp_base(SECTION_FORMAT) + ['-g', url], capture_output=True, stdin=subprocess.DEVNULL,
                              text=True, encoding='utf-8', errors='replace', timeout=120)
    except subprocess.TimeoutExpired:
        raise VodImportError("Timed out reading the VOD's stream address.")
    playlist_url = proc.stdout.strip().splitlines()[-1] if proc.returncode == 0 and proc.stdout.strip() else ''
    if not playlist_url.startswith('http'):
        raise VodImportError(friendly_error(proc.stderr or '', platform))

    import urllib.error
    import urllib.parse
    try:
        segments, _ = parse_hls_playlist(fetch(playlist_url).decode('utf-8', 'replace'))
        picked, trim = pick_segments(segments, start, end)
        if not picked:
            raise VodImportError("The VOD hasn't recorded this part yet.")
        joined = os.path.join(out_dir, f'{name}.ts.part')
        with open(joined, 'wb') as f:
            for seg in picked:
                f.write(fetch(urllib.parse.urljoin(playlist_url, seg['uri'])))
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise VodImportError(f"Download failed: {e}")

    path = os.path.join(out_dir, f'{name}.mp4')
    result = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{trim:.3f}', '-i', joined, '-t', f'{end - start:.3f}',
                             '-c', 'copy', '-bsf:a', 'aac_adtstoasc', '-movflags', '+faststart', path],
                            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=300)
    try:
        os.remove(joined)
    except OSError:
        pass
    if result.returncode != 0 or not os.path.exists(path):
        raise VodImportError(f"Could not cut the clip window: {result.stderr.strip()[-300:]}")
    return path


def decode_pcm(path, start=None, duration=None, rate=ALIGN_RATE):
    """Mono float PCM of a media file (or part of it). Input seeking is sample-accurate when decoding."""
    import numpy as np
    cmd = ['ffmpeg', '-v', 'error']
    if start is not None:
        cmd += ['-ss', f'{max(0.0, start):.3f}']
    cmd += ['-i', path]
    if duration is not None:
        cmd += ['-t', f'{duration:.3f}']
    cmd += ['-vn', '-ac', '1', '-ar', str(rate), '-f', 's16le', '-']
    out =subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL, timeout=900).stdout
    return np.frombuffer(out[:len(out) - len(out) % 2], dtype='<i2').astype(np.float64)


def find_offset(probe, ref, rate=ALIGN_RATE):
    """
    Where `probe` (a short sound snippet) best matches inside `ref`.
    Returns (offset_seconds, match) with match in [-1, 1] (normalized cross-correlation).
    """
    import numpy as np
    probe = np.asarray(probe, dtype=np.float64)
    ref = np.asarray(ref, dtype=np.float64)
    n, m = len(probe), len(ref)
    if n == 0 or m < n:
        return 0.0, 0.0
    probe = probe - probe.mean()
    p_norm = np.linalg.norm(probe)
    if p_norm == 0:
        return 0.0, 0.0
    size = 1 << int(np.ceil(np.log2(n + m)))
    corr = np.fft.irfft(np.fft.rfft(ref, size) * np.conj(np.fft.rfft(probe, size)), size)[:m - n + 1]
    # Per-lag norm of the ref window (mean-removed), from running sums
    c1 = np.concatenate(([0.0], np.cumsum(ref)))
    c2 = np.concatenate(([0.0], np.cumsum(ref * ref)))
    win_sum = c1[n:] - c1[:-n]
    win_sq = c2[n:] - c2[:-n]
    win_var = np.maximum(win_sq - win_sum * win_sum / n, 0.0)
    # corr against a mean-removed probe equals corr against the mean-removed window
    norm = np.sqrt(win_var) * p_norm
    with np.errstate(divide='ignore', invalid='ignore'):
        score = np.where(norm > 1e-9, corr / norm, 0.0)
    lag = int(np.argmax(score))
    return lag / rate, float(score[lag])


def align_section(section_path, audio_path, requested_start, search_s=25.0, probe_skip=2.0, probe_len=20.0,
                  rate=ALIGN_RATE):
    """
    Find where a downloaded section really starts in VOD time by matching its sound against the
    audio-only copy that moment detection used. Twitch cuts snap to segment boundaries and its
    playlists can sit ~10 s apart, so `requested_start` is only a guess.
    Returns (start_seconds, match). When the match is weak (silence, muted parts) the guess is returned.
    """
    probe = decode_pcm(section_path, probe_skip, probe_len, rate)
    ref_start = max(0.0, requested_start - search_s)
    ref = decode_pcm(audio_path, ref_start, (requested_start - ref_start) + search_s + probe_skip + probe_len, rate)
    lag, match = find_offset(probe, ref, rate)
    if match < ALIGN_MIN_MATCH:
        return float(requested_start), match
    return ref_start + lag - probe_skip, match


def fetch_clip_source(url, platform, out_dir, key, clip_start, clip_end, audio_path=None, duration=None, log=_log):
    """
    Download one clip window (padded) and work out its true VOD start.
    Returns (path, source_offset): VOD time t sits at (t - source_offset) inside the file.
    """
    lo, hi = section_bounds(clip_start, clip_end, duration)
    path = download_section(url, out_dir, f'section_{key}', lo, hi, platform, log)
    if not audio_path or not os.path.exists(audio_path):
        log(f"  ⚠️ No audio copy to line the window up with; trusting the requested start "
            f"(may be off by up to ~10 s).")
        return path, float(lo)
    start, match = align_section(path, audio_path, lo)
    if match < ALIGN_MIN_MATCH:
        log(f"  ⚠️ Could not line up the clip window by sound (match {match:.2f}); trusting the requested start.")
    else:
        log(f"  🎯 Clip window lined up by sound: starts at {start:.2f}s (asked {lo}s, match {match:.2f})")
    # The window must still cover the clip; if alignment says it doesn't, that's a real problem
    real_end = start + probe_duration(path)
    if start > clip_start + 0.5 or real_end < clip_end - 0.5:
        raise VodImportError(f"The downloaded clip window ({start:.1f}-{real_end:.1f}s) doesn't cover "
                             f"the moment ({clip_start:.1f}-{clip_end:.1f}s).")
    return path, start


def probe_duration(path):
    try:
        out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                              '-of', 'default=nw=1:nk=1', path], capture_output=True, text=True,
                             stdin=subprocess.DEVNULL, timeout=60).stdout.strip()
        return float(out)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0.0


def cleanup_sparse_files(video_id, storage_app=None):
    """Delete the audio copy and clip windows once clips are rendered. Chat and meta stay (tiny, re-scannable)."""
    out_dir = vod_dir(video_id, storage_app)
    if not os.path.isdir(out_dir):
        return 0
    freed = 0
    for name in os.listdir(out_dir):
        if name.startswith(('audio.', 'section_')) or name.endswith('.part'):
            p = os.path.join(out_dir, name)
            try:
                freed += os.path.getsize(p)
                os.remove(p)
            except OSError:
                pass
    meta_path = os.path.join(out_dir, 'meta.json')
    if os.path.exists(meta_path):
        try:
            with open(meta_path, encoding='utf-8') as f:
                meta = json.load(f)
            meta['audio_complete'] = False
            _save_meta(meta_path, meta)
        except (OSError, ValueError):
            pass
    return freed
