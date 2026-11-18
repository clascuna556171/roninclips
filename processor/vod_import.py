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

def _ytdlp_base():
    return [sys.executable, '-m', 'yt_dlp', '--no-playlist', '--no-warnings', '-f', VIDEO_FORMAT]


def probe(url, platform):
    """Fetch metadata (title, duration, size) without downloading."""
    try:
        proc = subprocess.run(_ytdlp_base() + ['-J', url], capture_output=True, stdin=subprocess.DEVNULL, text=True,
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


def format_progress(p):
    text = f"Downloading VOD: {p['percent']:.1f}%"
    if p['size']:
        text += f" of {p['size']}"
    if p['speed']:
        text += f" at {p['speed']}"
    if p['eta']:
        text += f", ETA {p['eta']}"
    return text


def download_video(url, out_dir, platform, log=_log):
    """Download the VOD into out_dir/vod.mp4 with live progress lines. Resumes .part files."""
    template = (f"download:{PROGRESS_PREFIX} %(progress._percent_str)s|%(progress._total_bytes_str)s|"
                f"%(progress._total_bytes_estimate_str)s|%(progress._speed_str)s|%(progress._eta_str)s")
    cmd = _ytdlp_base() + [
        '--newline', '--progress-template', template,
        '--retries', '10', '--fragment-retries', '10', '--continue',
        '--concurrent-fragments', '4',
        '--merge-output-format', 'mp4', '--remux-video', 'mp4',
        '-o', os.path.join(out_dir, 'vod.%(ext)s'),
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
                log(format_progress(p))
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
    path = os.path.join(out_dir, 'vod.mp4')
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

    chat_path = os.path.join(out_dir, 'chat.jsonl')
    chat_status, chat_count = 'unavailable', None
    if platform == 'kick':
        log("Kick chat: not available (Kick has no reliable chat-replay source). Video only.")
    elif os.path.exists(chat_path):
        with open(chat_path, encoding='utf-8') as f:
            chat_count = sum(1 for _ in f)
        chat_status = 'saved'
        log(f"Downloading chat: already saved ({chat_count} messages), skipping.")
    else:
        log("Downloading chat log from Twitch...")
        try:
            chat_path, chat_count = download_twitch_chat(vod_id, out_dir, log)
            chat_status = 'saved'
            log(f"Chat saved: {chat_count} messages -> {chat_path}")
        except VodImportError as e:
            chat_status = 'failed'
            log(f"⚠️ CHAT WARNING: {e} Continuing with the video only.")
        except (OSError, ValueError) as e:
            chat_status = 'failed'
            log(f"⚠️ CHAT WARNING: chat log could not be saved ({e}). Continuing with the video only.")

    return {
        'path': video_path,
        'title': meta.get('title') or f'{platform}_{vod_id}',
        'platform': platform,
        'vod_id': vod_id,
        'chat_status': chat_status,
        'chat_path': chat_path if chat_status == 'saved' else None,
        'chat_count': chat_count,
    }
