"""
RoninClips — live clipping from Twitch chat.

A background thread inside the watchlist watcher joins each followed channel's chat anonymously
(Twitch IRC as a "justinfan" guest: no account, no API key) and watches how fast chat moves.
When chat floods well above its own recent level, the moment is queued in
storage/app/watchlist/live_moments.json. The watcher's main loop then waits until the channel's
still-recording VOD has caught up past that moment, downloads just that window and renders it
as a one-clip job on the dashboard.

Everything except ChatListener's socket work is pure and unit-tested.
"""
import json
import os
import socket
import threading
import time
import uuid
from collections import defaultdict

import numpy as np

from moments import CHAT_FLOOR, rolling_zscore

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
QUEUE_PATH = os.path.join(ROOT_DIR, 'storage', 'app', 'watchlist', 'live_moments.json')

IRC_HOST, IRC_PORT = 'irc.chat.twitch.tv', 6667

# ── Spike tuning (first pass, see tests; re-check against real chats) ──
RATE_S = 5             # chat speed = messages per second over the last 5 s
HISTORY_S = 150        # seconds of chat kept for the baseline
WARMUP_S = 90          # no spikes until this much chat has been seen after joining
SPIKE_Z = 6.0          # robust z (median / MAD) the chat speed must reach
MIN_RATIO = 2.0        # ... and at least double the usual speed
MIN_RATE = 2.0         # ... and at least 2 msg/s, so a quiet chat's few extra messages don't count
COOLDOWN_S = 600       # one live clip per channel per 10 minutes at most

# ── Clip window around the moment chat reacted ──
PRE_S = 35             # the event happened before chat reacted
POST_S = 20
VOD_MARGIN_S = 10      # the VOD must be this far past the window end before it is cut
RETRY_S = 60           # how often to ask Twitch whether the VOD has caught up
DOWNLOAD_TRIES = 3     # live VOD downloads sometimes drop; try a window this many times
GIVE_UP_S = 1800       # stop waiting for a VOD after 30 minutes
QUEUE_KEEP = 200       # finished moments kept in the queue file for reference

_queue_lock = threading.Lock()


# ─── Pure helpers ────────────────────────────────────────────────────────────

def parse_irc_line(line):
    """('msg', channel) for a chat message, ('ping', None), ('reconnect', None), or None."""
    if not line:
        return None
    if line.startswith('PING'):
        return ('ping', None)
    body = line.split(' ', 1)[1] if line.startswith('@') and ' ' in line else line
    parts = body.split(' ', 3)
    if len(parts) >= 3 and parts[1] == 'PRIVMSG' and parts[2].startswith('#'):
        return ('msg', parts[2][1:].lower())
    if len(parts) >= 2 and parts[1] == 'RECONNECT':
        return ('reconnect', None)
    return None


class SpikeDetector:
    """Per-channel chat speed tracker. add() each message time, check() once a second."""

    def __init__(self, started_at):
        self.started_at = int(started_at)
        self.counts = defaultdict(int)
        self.last_spike = None

    def add(self, t):
        self.counts[int(t)] += 1

    def check(self, now):
        now = int(now)
        for s in [s for s in self.counts if s < now - HISTORY_S]:
            del self.counts[s]
        if now - self.started_at < WARMUP_S:
            return None
        if self.last_spike is not None and now - self.last_spike < COOLDOWN_S:
            return None
        first = max(self.started_at, now - HISTORY_S)
        x = np.array([self.counts.get(s, 0) for s in range(first, now)], dtype=float)
        rate = np.convolve(x, np.ones(RATE_S) / RATE_S)[:len(x)]  # trailing mean
        z = float(rolling_zscore(rate, CHAT_FLOOR, rel_floor=0.25)[-1])
        base_win = rate[:-RATE_S * 2] if len(rate) > RATE_S * 2 else rate
        baseline = float(np.median(base_win))
        current = float(rate[-1])
        if z >= SPIKE_Z and current >= MIN_RATE and current >= MIN_RATIO * baseline:
            self.last_spike = now
            return {'at': now, 'rate': round(current, 2), 'baseline': round(baseline, 2), 'z': round(z, 2)}
        return None


def moment_window(at):
    """Wall-clock [start, end] of the clip for a chat reaction at `at`."""
    return int(at) - PRE_S, int(at) + POST_S


def plan_moment(moment, vod_start, duration, now):
    """
    Where the moment sits in the channel's newest VOD.
    ('ready', start_s, end_s) | ('wait', None) | ('missing', reason)
    """
    offset = int(moment['at']) - int(vod_start)
    if offset < 0:
        return ('missing', 'The stream was not being saved as a VOD at that moment.')
    start_s = max(0, offset - PRE_S)
    end_s = offset + POST_S
    if duration is not None and duration >= end_s + VOD_MARGIN_S:
        return ('ready', start_s, end_s)
    if now - int(moment['at']) > GIVE_UP_S:
        return ('missing', 'The VOD never caught up to this moment (VODs may be hidden while live).')
    return ('wait', None)


def load_queue(path=None):
    path = path or QUEUE_PATH
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save_queue(moments, path=None):
    path = path or QUEUE_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(moments, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def add_moment(login, spike, path=None):
    moment = {'id': uuid.uuid4().hex[:12], 'login': login, 'status': 'waiting', 'next_try': 0,
              'error': None, 'long_video_id': None, **spike}
    with _queue_lock:
        moments = load_queue(path) + [moment]
        active = [m for m in moments if m['status'] in ('waiting', 'processing')]
        done = [m for m in moments if m['status'] not in ('waiting', 'processing')][-QUEUE_KEEP:]
        save_queue(sorted(active + done, key=lambda m: m['at']), path)
    return moment


def update_moment(moment_id, path=None, **changes):
    with _queue_lock:
        moments = load_queue(path)
        for m in moments:
            if m['id'] == moment_id:
                m.update(changes)
        save_queue(moments, path)


def next_due_moment(now, path=None):
    """Oldest waiting moment whose window has passed and whose retry time has come."""
    with _queue_lock:
        for m in load_queue(path):
            if m['status'] == 'waiting' and now >= m.get('next_try', 0) and now >= moment_window(m['at'])[1]:
                return m
    return None


def requeue_interrupted(path=None):
    """A moment left 'processing' means the watcher stopped mid-render: try it again."""
    with _queue_lock:
        moments = load_queue(path)
        changed = [m for m in moments if m['status'] == 'processing']
        for m in changed:
            m['status'] = 'waiting'
        if changed:
            save_queue(moments, path)
    return len(changed)


# ─── Chat listener thread ────────────────────────────────────────────────────

class ChatListener(threading.Thread):
    """Joins chats anonymously and calls on_spike(login, spike) when one floods."""

    def __init__(self, on_spike, log=print):
        super().__init__(daemon=True, name='live-chat')
        self.on_spike = on_spike
        self.log = log
        self._wanted = set()
        self._lock = threading.Lock()
        self.status = {'connected': False, 'channels': [], 'last_spike': None, 'error': None}

    def set_channels(self, logins):
        with self._lock:
            self._wanted = {l.lower() for l in logins}

    def run(self):
        backoff = 5
        while True:
            try:
                self._session()
                backoff = 5
            except (OSError, ConnectionError) as e:
                self.status.update(connected=False, error=str(e)[:200])
                self.log(f"Live chat: disconnected ({e}); reconnecting in {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 120)

    def _session(self):
        sock = socket.create_connection((IRC_HOST, IRC_PORT), timeout=10)
        sock.settimeout(1.0)
        nick = f'justinfan{uuid.uuid4().int % 90000 + 10000}'
        sock.sendall(f'PASS SCHMOOPIIE\r\nNICK {nick}\r\n'.encode())
        joined, detectors = set(), {}
        buf, last_data, last_check = b'', time.time(), 0
        self.status.update(connected=True, error=None)
        try:
            while True:
                with self._lock:
                    wanted = set(self._wanted)
                for login in sorted(wanted - joined):
                    sock.sendall(f'JOIN #{login}\r\n'.encode())
                    detectors[login] = SpikeDetector(started_at=time.time())
                    joined.add(login)
                for login in sorted(joined - wanted):
                    sock.sendall(f'PART #{login}\r\n'.encode())
                    detectors.pop(login, None)
                    joined.discard(login)
                self.status['channels'] = sorted(joined)

                try:
                    data = sock.recv(65536)
                    if not data:
                        raise ConnectionError('Twitch closed the chat connection')
                    buf += data
                    last_data = time.time()
                except socket.timeout:
                    if time.time() - last_data > 360:  # Twitch pings every ~5 min
                        raise ConnectionError('no data from Twitch chat for 6 minutes')
                *lines, buf = buf.split(b'\r\n')
                now = time.time()
                for raw in lines:
                    parsed = parse_irc_line(raw.decode('utf-8', 'replace'))
                    if parsed is None:
                        continue
                    kind, channel = parsed
                    if kind == 'ping':
                        sock.sendall(b'PONG :tmi.twitch.tv\r\n')
                    elif kind == 'reconnect':
                        raise ConnectionError('Twitch asked to reconnect')
                    elif channel in detectors:
                        detectors[channel].add(now)

                if int(now) != last_check:
                    last_check = int(now)
                    for login, det in detectors.items():
                        spike = det.check(now)
                        if spike:
                            self.status['last_spike'] = {'login': login, **spike}
                            self.log(f"Live chat: {login} flooded ({spike['rate']} msg/s vs usual "
                                     f"{spike['baseline']}, z {spike['z']}); clip queued")
                            try:
                                self.on_spike(login, spike)
                            except Exception as e:  # a bad write must not kill the listener
                                self.log(f"Live chat: could not queue the moment ({e})")
        finally:
            self.status['connected'] = False
            try:
                sock.close()
            except OSError:
                pass
