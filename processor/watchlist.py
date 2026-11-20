"""
RoninClips — Twitch watchlist watcher.

Runs in the background while RoninClips is open (the dashboard starts it). On start and then
every hour it lists each followed channel's VODs with yt-dlp (no API key), queues new ones, and
runs them one at a time through engine.py in sparse mode: audio + chat are scanned for the best
3 moments, only those windows are downloaded at 1080p, and the downloads are deleted afterwards.

Twitch keeps VODs for at least 7 days, so hours or days with the PC off are caught up, newest first.
A channel's back catalogue is not processed: when a channel is added, only its newest VOD is queued.

State the dashboard reads lives in storage/app/watchlist/:
  heartbeat.json  what the watcher is doing, refreshed every few seconds
  check_now       created by the page to ask for an immediate check
  watcher.lock    held while a watcher runs, so only one ever runs
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

if sys.platform == 'win32':
    os.environ['PYTHONUTF8'] = '1'
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_helper import get_db, DatabaseUnavailable  # noqa: E402
from vod_import import VodImportError, cleanup_sparse_files, download_live_section, vod_dir  # noqa: E402
import live_clips  # noqa: E402

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
STATE_DIR = os.path.join(ROOT_DIR, 'storage', 'app', 'watchlist')
HEARTBEAT_PATH = os.path.join(STATE_DIR, 'heartbeat.json')
CHECK_NOW_PATH = os.path.join(STATE_DIR, 'check_now')
LOCK_PATH = os.path.join(STATE_DIR, 'watcher.lock')
ENGINE_PATH = os.path.join(ROOT_DIR, 'processor', 'engine.py')

CHECK_INTERVAL_S = 3600     # check every channel hourly
IDLE_SLEEP_S = 10           # how often an idle watcher looks for work / a "check now" request
DB_RETRY_S = 60             # wait this long when the database is offline
CLIPS_PER_VOD = 3           # owner: "just 3 best is enough"
MIN_VOD_S = 300             # VODs under 5 minutes are usually a crashed or test stream
LIST_LIMIT = 10             # newest VODs looked at per channel per check

LOGIN_RE = re.compile(r'^[a-z0-9_]{3,25}$')

# Dashboard settings carried over from your latest Stream Moments job (captions, crop, layout...)
PREF_KEYS = (
    'output_format', 'caption_style', 'caption_font', 'caption_position', 'caption_layout',
    'transition_speed', 'whisper_model', 'language_mode', 'hardware_accel', 'smart_crop',
    'auto_captions', 'punch_in_zoom', 'ken_burns', 'emoji_overlays', 'whip_pan_transitions',
    'background_music', 'bgm_path', 'split_screen', 'gaming_layout', 'clean_captions', 'loudness_normalize',
)


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def utc_now_str():
    """Laravel's app timezone is UTC; timestamps written here must match."""
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def vod_url(vod_id):
    return f'https://www.twitch.tv/videos/{vod_id}'


# ─── Pure helpers (unit-tested) ────────────────────────────────────────────────

def parse_vod_list(output):
    """yt-dlp `--print "%(id)s|%(duration)s|%(title)s"` lines -> [{id, duration, title}], newest first."""
    vods = []
    for line in (output or '').splitlines():
        parts = line.strip().split('|', 2)
        if len(parts) < 2:
            continue
        vid = parts[0].strip().lstrip('v')
        if not vid.isdigit():
            continue
        try:
            duration = int(float(parts[1]))
        except ValueError:
            duration = None
        title = parts[2].strip() if len(parts) > 2 else ''
        vods.append({'id': vid, 'duration': duration, 'title': title if title not in ('NA', '') else None})
    return vods


def plan_new_vods(listed, known_ids, first_check, live):
    """
    Decide what to do with each listed VOD we haven't seen.
    `listed` is newest first. While the channel is live its newest VOD is still recording, so it is
    left for a later check. Returns [(vod, status, reason)] with status 'queued' or 'skipped'.
    """
    candidates = listed[1:] if live and listed else list(listed)
    plan = []
    newest_taken = False
    for vod in candidates:
        if vod['id'] in known_ids:
            continue
        if first_check and newest_taken:
            plan.append((vod, 'skipped', 'Older than when the channel was added'))
            continue
        if vod.get('duration') is not None and vod['duration'] < MIN_VOD_S:
            plan.append((vod, 'skipped', 'Shorter than 5 minutes'))
            continue
        plan.append((vod, 'queued', None))
        newest_taken = True
    return plan


def pick_base_settings(rows):
    """Latest non-watchlist Stream Moments job's settings (rows newest first), else {}."""
    for raw in rows:
        try:
            s = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except (TypeError, ValueError):
            continue
        if isinstance(s, dict) and s.get('stream_moments') and not s.get('watchlist'):
            return s
    return {}


def build_settings(base, login, vod_id, skip_windows=()):
    """`skip_windows`: [start_s, end_s] VOD spans already clipped live, so the VOD pass skips them."""
    settings = {k: base[k] for k in PREF_KEYS if k in base}
    if skip_windows:
        settings['skip_windows'] = [[int(s), int(e)] for s, e in skip_windows]
    settings.update({
        'stream_moments': True,
        'full_video_mode': False,
        'target_clip_count': CLIPS_PER_VOD,
        'sparse_download': True,
        'watchlist': True,
        'watch_channel': login,
        'source_url': vod_url(vod_id),
        'source_platform': 'twitch',
        'source_vod_id': str(vod_id),
    })
    return settings


def live_settings(base, login, vod_id, offset_s, moment=None, at_label=None):
    """A live moment: one clip rendered from the already-downloaded window (no VOD import).
    The chat spike and time label give the clip a fallback title when the AI can't."""
    settings = {k: base[k] for k in PREF_KEYS if k in base}
    if moment:
        settings['live_chat'] = {k: moment[k] for k in ('rate', 'baseline', 'z') if k in moment}
    if at_label:
        settings['live_at_label'] = at_label
    settings.update({
        'full_video_mode': True,
        'stream_moments': False,
        'sparse_download': False,
        'watchlist': True,
        'live_clip': True,
        'watch_channel': login,
        'live_vod_url': vod_url(vod_id),
        'live_vod_offset_s': int(offset_s),
    })
    return settings


def failure_reason(log_text, settings):
    """One line for the watchlist page, from the engine's own messages."""
    if settings.get('import_error'):
        return 'Import failed: ' + settings['import_error']
    for pattern in (r'^DATABASE ERROR: (.+)$', r'^IMPORT ERROR: (.+)$', r'^Pipeline failed: (.+)$'):
        m = re.findall(pattern, log_text or '', re.M)
        if m:
            return m[-1].strip()[:500]
    return 'The pipeline stopped without a clear error. Open the log on the dashboard.'


# ─── yt-dlp ──────────────────────────────────────────────────────────────────

def _ytdlp(args, timeout=180):
    return subprocess.run([sys.executable, '-m', 'yt_dlp', '--no-warnings'] + args, capture_output=True,
                          text=True, encoding='utf-8', errors='replace', stdin=subprocess.DEVNULL, timeout=timeout)


def list_channel_vods(login):
    proc = _ytdlp(['--flat-playlist', '--playlist-end', str(LIST_LIMIT), '--print', '%(id)s|%(duration)s|%(title)s',
                   f'https://www.twitch.tv/{login}/videos?filter=archives&sort=time'])
    if proc.returncode != 0:
        err = [l for l in proc.stderr.splitlines() if 'ERROR' in l]
        raise RuntimeError((err[-1].split('ERROR:', 1)[-1].strip() if err else 'yt-dlp could not list VODs')[:300])
    return parse_vod_list(proc.stdout)


def vod_is_recording(vod_id):
    """
    True while a VOD is still being recorded (its stream is live), False once finished, None if unknown.
    Twitch reports this per VOD (live_status 'is_live' vs 'was_live'), which is exact even when a
    streamer is live without saving a VOD. Unknown is treated as recording, so a half VOD is never grabbed.
    """
    try:
        proc = _ytdlp(['--skip-download', '-f', 'ba/b', '--print', 'live_status', vod_url(vod_id)], timeout=90)
    except subprocess.TimeoutExpired:
        return None
    status = proc.stdout.strip().splitlines()[-1].strip() if proc.returncode == 0 and proc.stdout.strip() else ''
    if status == 'is_live':
        return True
    if status in ('was_live', 'not_live', 'post_live'):
        return False
    return None


def vod_timing(vod_id):
    """(start epoch, seconds recorded so far) for a VOD, or None if Twitch didn't say."""
    try:
        proc = _ytdlp(['--skip-download', '-f', 'ba/b', '--print', '%(timestamp)s|%(duration)s', vod_url(vod_id)],
                      timeout=90)
    except subprocess.TimeoutExpired:
        return None
    lines = proc.stdout.strip().splitlines() if proc.returncode == 0 else []
    try:
        ts, dur = lines[-1].split('|')
        return int(float(ts)), int(float(dur))
    except (IndexError, ValueError):
        return None


# ─── Heartbeat & single instance ─────────────────────────────────────────────

class Heartbeat:
    def __init__(self, path=HEARTBEAT_PATH):
        self.path = path
        self.data = {'pid': os.getpid(), 'state': 'starting', 'current': None,
                     'last_check_at': None, 'next_check_at': None, 'message': None}

    def beat(self, **changes):
        self.data.update(changes)
        self.data['updated_at'] = int(time.time())
        tmp = self.path + '.tmp'
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError:
            pass


def acquire_lock(path=LOCK_PATH):
    """Hold an OS lock for the process lifetime. Returns the open file, or None if another watcher has it."""
    f = open(path, 'a+')
    try:
        if os.name == 'nt':
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


# ─── Database work ───────────────────────────────────────────────────────────

def check_channel(db, ch):
    cur = db.cursor()
    login = ch['login']
    try:
        listed = list_channel_vods(login)
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        cur.execute("UPDATE watch_channels SET last_checked_at = %s, last_error = %s, updated_at = %s WHERE id = %s",
                    (utc_now_str(), f'Could not check: {e}', utc_now_str(), ch['id']))
        db.commit()
        log(f"  {login}: check failed ({e})")
        return 0
    cur.execute("SELECT vod_id FROM watch_vods WHERE watch_channel_id = %s", (ch['id'],))
    known = {r['vod_id'] for r in cur.fetchall()}
    # Only the newest VOD can still be recording, and only a new one needs asking about
    live = False
    if listed and listed[0]['id'] not in known:
        live = vod_is_recording(listed[0]['id'])
    plan = plan_new_vods(listed, known, first_check=not known, live=live is not False)
    queued = 0
    for vod, status, reason in plan:
        now = utc_now_str()
        cur.execute("INSERT INTO watch_vods (watch_channel_id, vod_id, title, duration_s, status, error, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (ch['id'], vod['id'], (vod['title'] or '')[:250] or None, vod['duration'], status, reason, now, now))
        queued += status == 'queued'
    note = None if listed else 'No public VODs found (VODs may be off for this channel).'
    cur.execute("UPDATE watch_channels SET last_checked_at = %s, last_error = %s, updated_at = %s WHERE id = %s",
                (utc_now_str(), note, utc_now_str(), ch['id']))
    db.commit()
    live_txt = ('newest VOD still recording, left until the stream ends' if live
                else ('could not tell if the newest VOD is finished, left for next check' if live is None else 'all finished'))
    log(f"  {login}: {len(listed)} VODs listed, {queued} new queued ({live_txt})")
    return queued


def check_all(db):
    cur = db.cursor()
    cur.execute("SELECT * FROM watch_channels WHERE enabled = 1 ORDER BY id")
    channels = cur.fetchall()
    log(f"Checking {len(channels)} channel(s) for new VODs...")
    return sum(check_channel(db, ch) for ch in channels)


def next_queued(db):
    cur = db.cursor()
    # Twitch VOD ids grow over time, so the longest/highest id is the newest VOD
    cur.execute("SELECT v.*, c.login FROM watch_vods v JOIN watch_channels c ON c.id = v.watch_channel_id "
                "WHERE v.status = 'queued' AND c.enabled = 1 "
                "ORDER BY LENGTH(v.vod_id) DESC, v.vod_id DESC LIMIT 1")
    return cur.fetchone()


def recover_interrupted(db):
    """A VOD left 'processing' means the PC or app shut down mid-run: run it again."""
    cur = db.cursor()
    cur.execute("UPDATE watch_vods SET status = 'queued', updated_at = %s WHERE status = 'processing'", (utc_now_str(),))
    if cur.rowcount:
        log(f"Re-queued {cur.rowcount} VOD(s) interrupted last time.")
    db.commit()


def _delete_clip_files(clip):
    paths = [os.path.join(ROOT_DIR, clip['output_path']) if clip.get('output_path') else None]
    for rel in (f"intermediate_{clip['id']}.mp4", f"clip_{clip['id']}_words.json", f"clip_{clip['id']}.ass",
                f"public/clip_{clip['id']}_frame.jpg", f"public/clip_{clip['id']}_preview.jpg"):
        paths.append(os.path.join(ROOT_DIR, 'storage', 'app', rel))
    paths.append(os.path.join(ROOT_DIR, 'storage', 'logs', f"re_render_{clip['id']}.log"))
    for p in paths:
        if p and os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


def prepare_long_video(db, wv):
    """Create the dashboard job for this VOD, or reset the one from an earlier attempt. Returns its id."""
    cur = db.cursor()
    now = utc_now_str()
    if wv.get('long_video_id'):
        cur.execute("SELECT id FROM long_videos WHERE id = %s", (wv['long_video_id'],))
        if cur.fetchone():
            cur.execute("SELECT * FROM video_clips WHERE long_video_id = %s", (wv['long_video_id'],))
            for clip in cur.fetchall():
                _delete_clip_files(clip)
            cur.execute("DELETE FROM video_clips WHERE long_video_id = %s", (wv['long_video_id'],))
            cur.execute("UPDATE long_videos SET status = 'pending', updated_at = %s WHERE id = %s",
                        (now, wv['long_video_id']))
            db.commit()
            return wv['long_video_id']

    cur.execute("SELECT processing_settings FROM long_videos ORDER BY id DESC LIMIT 50")
    base = pick_base_settings([r['processing_settings'] for r in cur.fetchall()])
    settings = build_settings(base, wv['login'], wv['vod_id'], live_clips.clipped_windows(wv['vod_id']))
    name = f"{wv['login']} · {wv.get('title') or 'Twitch VOD ' + wv['vod_id']}"[:180]
    cur.execute("INSERT INTO long_videos (filename, storage_path, status, processing_settings, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)", (name, '', 'pending', json.dumps(settings), now, now))
    db.commit()
    return cur.lastrowid


def run_engine(video_id, heartbeat):
    log_path = os.path.join(ROOT_DIR, 'storage', 'logs', f'engine_{video_id}.log')
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, 'w', encoding='utf-8') as logf:
        proc = subprocess.Popen([sys.executable, ENGINE_PATH, str(video_id)], stdout=logf, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, cwd=ROOT_DIR)
        while proc.poll() is None:
            heartbeat.beat()
            time.sleep(5)
    try:
        with open(log_path, encoding='utf-8', errors='replace') as f:
            return f.read()
    except OSError:
        return ''


def process_vod(db, wv, heartbeat):
    cur = db.cursor()
    video_id = prepare_long_video(db, wv)
    cur.execute("UPDATE watch_vods SET status = 'processing', long_video_id = %s, error = NULL, updated_at = %s WHERE id = %s",
                (video_id, utc_now_str(), wv['id']))
    db.commit()
    log(f"Processing {wv['login']} VOD {wv['vod_id']} ({wv.get('title') or 'untitled'}) as job #{video_id}...")
    heartbeat.beat(state='processing', current={'vod_id': wv['vod_id'], 'channel': wv['login'],
                                                'title': wv.get('title'), 'long_video_id': video_id})
    log_text = run_engine(video_id, heartbeat)

    db_after = get_db()  # the engine ran for a long time; use a fresh connection
    try:
        c2 = db_after.cursor()
        c2.execute("SELECT status, processing_settings FROM long_videos WHERE id = %s", (video_id,))
        row = c2.fetchone()
        if row is None:
            status, error = 'failed', 'The dashboard job was deleted while it ran.'
        elif row['status'] == 'completed':
            status, error = 'done', None
        else:
            try:
                settings = json.loads(row['processing_settings'] or '{}')
            except (TypeError, ValueError):
                settings = {}
            status, error = 'failed', failure_reason(log_text, settings)
            cleanup_sparse_files(video_id)  # don't leave a 1-2 GB audio copy behind; Retry re-downloads it
        c2.execute("UPDATE watch_vods SET status = %s, error = %s, long_video_id = %s, updated_at = %s WHERE id = %s",
                   (status, error, video_id if row else None, utc_now_str(), wv['id']))
        db_after.commit()
    finally:
        db_after.close()
    log(f"  -> {status}{': ' + error if error else ''}")


def process_live_moment(db, m, heartbeat):
    """Turn one queued chat flood into a dashboard clip, or push it back until the VOD catches up."""
    now = time.time()
    login = m['login']
    try:
        listed = list_channel_vods(login)
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        listed, list_err = [], str(e)
    else:
        list_err = None
    timing = vod_timing(listed[0]['id']) if listed else None
    if timing is None:
        if now - m['at'] > live_clips.GIVE_UP_S:
            live_clips.update_moment(m['id'], status='failed',
                                     error=f"No VOD found for this stream{': ' + list_err if list_err else ''}.")
        else:
            live_clips.update_moment(m['id'], next_try=now + live_clips.RETRY_S)
        return False
    vod_id = listed[0]['id']
    plan = live_clips.plan_moment(m, timing[0], timing[1], now)
    if plan[0] == 'wait':
        live_clips.update_moment(m['id'], next_try=now + live_clips.RETRY_S)
        return False
    if plan[0] == 'missing':
        live_clips.update_moment(m['id'], status='failed', error=plan[1])
        log(f"Live moment {login} @ {datetime.fromtimestamp(m['at']).strftime('%H:%M:%S')} dropped: {plan[1]}")
        return False

    _, start_s, end_s = plan
    stamp = datetime.fromtimestamp(m['at']).strftime('%b %d %H:%M')
    heartbeat.beat(state='processing', current={'vod_id': vod_id, 'channel': login,
                                                'title': f'Live chat spike {stamp}', 'long_video_id': None})
    log(f"Live moment {login} @ {stamp}: cutting {start_s}-{end_s}s of VOD {vod_id}...")
    # Download before creating the dashboard job, so a failed try leaves no empty job behind.
    # Twitch sometimes drops a live VOD download mid-way; a later try usually works.
    out_dir = vod_dir(f"live_{m['id']}")
    os.makedirs(out_dir, exist_ok=True)
    try:
        path = download_live_section(vod_url(vod_id), out_dir, "live", start_s, end_s, "twitch", log=log)
    except VodImportError as e:
        tries = m.get('download_tries', 0) + 1
        if tries < live_clips.DOWNLOAD_TRIES:
            live_clips.update_moment(m['id'], download_tries=tries, next_try=time.time() + live_clips.RETRY_S)
            log(f"  -> download failed ({e}); trying again in {live_clips.RETRY_S}s")
        else:
            live_clips.update_moment(m['id'], status='failed', error=f'Download failed: {e}'[:300])
            log(f"  -> failed: {e}")
        return True

    cur = db.cursor()
    cur.execute("SELECT processing_settings FROM long_videos ORDER BY id DESC LIMIT 50")
    base = pick_base_settings([r['processing_settings'] for r in cur.fetchall()])
    settings = live_settings(base, login, vod_id, start_s, m, stamp)
    name = f"{login} · LIVE chat spike {stamp}"[:180]
    ts = utc_now_str()
    cur.execute("INSERT INTO long_videos (filename, storage_path, status, processing_settings, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)", (name, path, 'pending', json.dumps(settings), ts, ts))
    db.commit()
    video_id = cur.lastrowid
    live_clips.update_moment(m['id'], status='processing', long_video_id=video_id, vod_id=vod_id,
                             start_s=start_s, end_s=end_s)
    heartbeat.beat(current={'vod_id': vod_id, 'channel': login,
                            'title': f'Live chat spike {stamp}', 'long_video_id': video_id})
    log(f"  rendering as job #{video_id}...")

    log_text = run_engine(video_id, heartbeat)
    db_after = get_db()
    try:
        c2 = db_after.cursor()
        c2.execute("SELECT status FROM long_videos WHERE id = %s", (video_id,))
        row = c2.fetchone()
    finally:
        db_after.close()
    if row and row['status'] == 'completed':
        live_clips.update_moment(m['id'], status='done', error=None)
        log("  -> done")
    else:
        err = failure_reason(log_text, {}) if row else 'The dashboard job was deleted while it ran.'
        live_clips.update_moment(m['id'], status='failed', error=err)
        log(f"  -> failed: {err}")
    return True


def sync_live_channels(db, listener):
    cur = db.cursor()
    cur.execute("SELECT login FROM watch_channels WHERE enabled = 1")
    listener.set_channels([r['login'] for r in cur.fetchall()])


# ─── Main loop ───────────────────────────────────────────────────────────────

def main():
    os.makedirs(STATE_DIR, exist_ok=True)
    lock = acquire_lock()
    if lock is None:
        log("Another watcher is already running. Exiting.")
        return 0
    heartbeat = Heartbeat()
    heartbeat.beat(state='starting')
    log(f"Watchlist watcher started (pid {os.getpid()}). Checking hourly; {CLIPS_PER_VOD} clips per VOD.")
    if live_clips.requeue_interrupted():
        log("Re-queued live moment(s) interrupted last time.")
    listener = live_clips.ChatListener(on_spike=live_clips.add_moment, log=log)
    listener.start()
    last_check = 0.0
    recovered = False
    while True:
        try:
            db = get_db()
            try:
                if not recovered:
                    recover_interrupted(db)
                    recovered = True
                sync_live_channels(db, listener)
                heartbeat.beat(live_chat=dict(listener.status))
                due = live_clips.next_due_moment(time.time())
                if due and process_live_moment(db, due, heartbeat):
                    continue
                forced = os.path.exists(CHECK_NOW_PATH)
                if forced or time.time() - last_check >= CHECK_INTERVAL_S:
                    if forced:
                        try:
                            os.remove(CHECK_NOW_PATH)
                        except OSError:
                            pass
                    heartbeat.beat(state='checking', current=None, message=None)
                    check_all(db)
                    last_check = time.time()
                    heartbeat.beat(last_check_at=int(last_check), next_check_at=int(last_check + CHECK_INTERVAL_S))
                wv = next_queued(db)
                if wv:
                    process_vod(db, wv, heartbeat)
                    continue
            finally:
                db.close()
            heartbeat.beat(state='idle', current=None, message=None)
            time.sleep(IDLE_SLEEP_S)
        except DatabaseUnavailable as e:
            log(f"DATABASE ERROR: {e}")
            heartbeat.beat(state='db_offline', current=None, message=str(e)[:300])
            time.sleep(DB_RETRY_S)
        except KeyboardInterrupt:
            log("Stopped.")
            return 0
        except Exception as e:  # keep the watcher alive; one bad check must not stop the next
            log(f"⚠️ Watcher error: {e}")
            heartbeat.beat(state='idle', message=f'Last error: {e}'[:300])
            time.sleep(DB_RETRY_S)


if __name__ == '__main__':
    sys.exit(main())
