import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'processor')))

import live_clips
from live_clips import (
    COOLDOWN_S, POST_S, PRE_S, WARMUP_S, SpikeDetector, load_queue, moment_window,
    parse_irc_line, plan_moment, save_queue,
)
from watchlist import live_settings

T0 = 1_795_000_000


def feed(det, start, seconds, per_second):
    """Feed `per_second` messages for each second in [start, start + seconds)."""
    for s in range(start, start + seconds):
        for i in range(per_second):
            det.add(s + i / max(per_second, 1) * 0.9)


class TestParseIrcLine(unittest.TestCase):
    def test_chat_message_gives_channel(self):
        line = ('@badge-info=;color=#FF0000;display-name=Fan :fan!fan@fan.tmi.twitch.tv '
                'PRIVMSG #kaicenat :W STREAM')
        self.assertEqual(parse_irc_line(line), ('msg', 'kaicenat'))

    def test_ping(self):
        self.assertEqual(parse_irc_line('PING :tmi.twitch.tv'), ('ping', None))

    def test_reconnect_request(self):
        self.assertEqual(parse_irc_line(':tmi.twitch.tv RECONNECT'), ('reconnect', None))

    def test_other_lines_ignored(self):
        self.assertIsNone(parse_irc_line(':tmi.twitch.tv 001 justinfan1 :Welcome, GLHF!'))
        self.assertIsNone(parse_irc_line(''))


class TestSpikeDetector(unittest.TestCase):
    def test_flood_after_steady_chat_is_a_spike(self):
        det = SpikeDetector(started_at=T0)
        feed(det, T0, 150, 2)
        self.assertIsNone(det.check(T0 + 150))
        feed(det, T0 + 150, 6, 20)
        spike = det.check(T0 + 156)
        self.assertIsNotNone(spike)
        self.assertGreater(spike['rate'], 10)

    def test_steady_chat_never_spikes(self):
        det = SpikeDetector(started_at=T0)
        for s in range(T0, T0 + 400):
            det.add(s)
            det.add(s + 0.5)
            self.assertIsNone(det.check(s + 1))

    def test_no_spike_during_warmup(self):
        det = SpikeDetector(started_at=T0)
        feed(det, T0, 20, 1)
        feed(det, T0 + 20, 6, 30)
        self.assertIsNone(det.check(T0 + 26))
        self.assertLess(26, WARMUP_S)

    def test_quiet_chat_extra_messages_are_not_a_spike(self):
        # 0 -> 1 msg/s in a near-silent chat is not a moment
        det = SpikeDetector(started_at=T0)
        feed(det, T0, 150, 0)
        feed(det, T0 + 150, 6, 1)
        self.assertIsNone(det.check(T0 + 156))

    def test_cooldown_blocks_a_second_spike(self):
        det = SpikeDetector(started_at=T0)
        feed(det, T0, 150, 2)
        feed(det, T0 + 150, 6, 20)
        self.assertIsNotNone(det.check(T0 + 156))
        feed(det, T0 + 156, 60, 2)
        feed(det, T0 + 216, 6, 25)
        self.assertIsNone(det.check(T0 + 222))
        self.assertLess(222 - 156, COOLDOWN_S)

    def test_spike_fires_once_per_flood(self):
        det = SpikeDetector(started_at=T0)
        feed(det, T0, 150, 2)
        feed(det, T0 + 150, 15, 20)
        hits = [det.check(T0 + s) for s in range(151, 166)]
        self.assertEqual(sum(h is not None for h in hits), 1)


class TestMomentPlanning(unittest.TestCase):
    def test_window_starts_before_the_chat_reaction(self):
        start, end = moment_window(T0)
        self.assertEqual((start, end), (T0 - PRE_S, T0 + POST_S))
        self.assertLessEqual(end - start, 60)

    def test_ready_when_vod_has_caught_up(self):
        vod_start = T0 - 3600
        m = {'at': T0}
        plan = plan_moment(m, vod_start, duration=3600 + POST_S + 30, now=T0 + 200)
        self.assertEqual(plan[0], 'ready')
        self.assertEqual(plan[1:], (3600 - PRE_S, 3600 + POST_S))

    def test_wait_while_vod_is_behind(self):
        plan = plan_moment({'at': T0}, T0 - 3600, duration=3600 + 5, now=T0 + 40)
        self.assertEqual(plan[0], 'wait')

    def test_moment_before_the_vod_started_is_missing(self):
        # The newest VOD started after the moment: the stream it came from was not saved
        plan = plan_moment({'at': T0}, T0 + 600, duration=100, now=T0 + 800)
        self.assertEqual(plan[0], 'missing')

    def test_gives_up_when_vod_never_catches_up(self):
        plan = plan_moment({'at': T0}, T0 - 3600, duration=3600, now=T0 + 3600)
        self.assertEqual(plan[0], 'missing')

    def test_window_clamped_to_vod_start(self):
        plan = plan_moment({'at': T0}, T0 - 10, duration=200, now=T0 + 200)
        self.assertEqual(plan, ('ready', 0, 10 + POST_S))


class TestLiveSettings(unittest.TestCase):
    def test_one_clip_from_a_local_section_keeping_owner_prefs(self):
        base = {'caption_style': 'bold', 'gaming_layout': True, 'stream_moments': True, 'sparse_download': True}
        s = live_settings(base, 'kaicenat', '2932305259', 4100)
        self.assertTrue(s['full_video_mode'])
        self.assertTrue(s['live_clip'])
        self.assertTrue(s['watchlist'])  # never used as the base for other jobs
        self.assertNotIn('source_url', s)  # the engine must not re-import the VOD
        self.assertFalse(s.get('sparse_download'))
        self.assertFalse(s.get('stream_moments'))
        self.assertEqual(s['caption_style'], 'bold')
        self.assertEqual(s['live_vod_url'], 'https://www.twitch.tv/videos/2932305259')
        self.assertEqual(s['live_vod_offset_s'], 4100)


class TestQueueFile(unittest.TestCase):
    def test_round_trip_and_missing_or_broken_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'live_moments.json')
            self.assertEqual(load_queue(path), [])
            save_queue([{'id': 'a', 'login': 'kai', 'at': T0, 'status': 'waiting'}], path)
            self.assertEqual(load_queue(path)[0]['login'], 'kai')
            with open(path, 'w') as f:
                f.write('{not json')
            self.assertEqual(load_queue(path), [])

    def test_clipped_windows_only_counts_finished_moments_of_that_vod(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'live_moments.json')
            save_queue([
                {'id': 'a', 'at': T0, 'status': 'done', 'vod_id': '900', 'start_s': 100, 'end_s': 155},
                {'id': 'b', 'at': T0, 'status': 'failed', 'vod_id': '900', 'start_s': 300, 'end_s': 355},
                {'id': 'c', 'at': T0, 'status': 'done', 'vod_id': '901', 'start_s': 500, 'end_s': 555},
                {'id': 'd', 'at': T0, 'status': 'done', 'vod_id': 900},  # older entry without a span
            ], path)
            self.assertEqual(live_clips.clipped_windows(900, path), [(100, 155)])


if __name__ == '__main__':
    unittest.main()


# ─── Live VOD window download (segment picking) ───────────────────────────────

from vod_import import parse_hls_playlist, pick_segments  # noqa: E402

PLAYLIST = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:10
#EXT-X-PLAYLIST-TYPE:EVENT
#EXT-X-MEDIA-SEQUENCE:0
#EXT-X-PROGRAM-DATE-TIME:2026-11-18T12:59:53.334Z
#EXTINF:10.000,
0.ts
#EXTINF:10.000,
1-muted.ts
#EXTINF:10.000,
2.ts
#EXTINF:10.000,
3.ts
#EXTINF:4.500,
4.ts
"""


class TestLivePlaylist(unittest.TestCase):
    def test_parses_segments_with_running_offsets(self):
        segs, ended = parse_hls_playlist(PLAYLIST)
        self.assertFalse(ended)
        self.assertEqual([s['uri'] for s in segs], ['0.ts', '1-muted.ts', '2.ts', '3.ts', '4.ts'])
        self.assertEqual([s['start'] for s in segs], [0.0, 10.0, 20.0, 30.0, 40.0])
        self.assertEqual(segs[-1]['duration'], 4.5)

    def test_finished_playlist_is_marked_ended(self):
        self.assertTrue(parse_hls_playlist(PLAYLIST + '#EXT-X-ENDLIST\n')[1])

    def test_picks_only_the_segments_covering_the_window(self):
        segs, _ = parse_hls_playlist(PLAYLIST)
        picked, trim = pick_segments(segs, 12, 33)
        self.assertEqual([s['uri'] for s in picked], ['1-muted.ts', '2.ts', '3.ts'])
        self.assertEqual(trim, 2.0)  # the window starts 2 s into the first picked segment

    def test_window_past_the_recorded_end_picks_nothing(self):
        segs, _ = parse_hls_playlist(PLAYLIST)
        self.assertEqual(pick_segments(segs, 40, 60), ([], 0.0))
