import json
import os
import sys
import tempfile
import unittest
from collections import namedtuple
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'processor')))

import vod_import
from vod_import import (
    VodImportError, check_disk_space, estimate_size_bytes, format_progress, friendly_error,
    normalize_twitch_chat, parse_progress_line, parse_source_url, write_chat_jsonl,
)

Usage = namedtuple('Usage', 'total used free')


class TestParseSourceUrl(unittest.TestCase):
    def test_twitch(self):
        self.assertEqual(parse_source_url('https://www.twitch.tv/videos/2612345678'), ('twitch', '2612345678'))
        self.assertEqual(parse_source_url(' https://m.twitch.tv/videos/42?t=1h '), ('twitch', '42'))

    def test_kick_channel_videos_form_only(self):
        uid = '1A2B3C4D-0000-1111-2222-333344445555'
        self.assertEqual(parse_source_url(f'https://kick.com/chan_1/videos/{uid}'), ('kick', uid.lower()))
        # yt-dlp (2026.10.26) only supports the channel/videos form
        self.assertIsNone(parse_source_url(f'https://kick.com/video/{uid}'))

    def test_rejects_others(self):
        for url in ('https://www.twitch.tv/somechannel', 'https://youtube.com/watch?v=x',
                    'C:\\videos\\a.mp4', '', None):
            self.assertIsNone(parse_source_url(url))


class TestFriendlyErrors(unittest.TestCase):
    def test_subscriber_only(self):
        msg = friendly_error('ERROR: [twitch:vod] 123: This video is only available to subscribers', 'twitch')
        self.assertIn('subscriber-only', msg)

    def test_deleted(self):
        msg = friendly_error('ERROR: [twitch:vod] 999: Video 999 does not exist', 'twitch')
        self.assertIn("wasn't found", msg)
        self.assertIn('deleted', msg)

    def test_region_locked(self):
        msg = friendly_error('ERROR: The uploader has not made this video available in your country', 'twitch')
        self.assertIn('region-locked', msg)
        self.assertIn('region-locked', friendly_error('ERROR: This video is geo restricted', 'kick'))

    def test_kick_403(self):
        msg = friendly_error('ERROR: [kick:vod] x: Unable to download JSON metadata: HTTP Error 403: Forbidden', 'kick')
        self.assertIn('Kick blocked the download', msg)

    def test_unknown_falls_back_to_last_error_line_without_traceback(self):
        out = 'Traceback (most recent call last):\n  File "x"\nERROR: something odd happened'
        msg = friendly_error(out, 'twitch')
        self.assertEqual(msg, 'Download failed: something odd happened')
        self.assertNotIn('Traceback', msg)


class TestProgress(unittest.TestCase):
    def test_parse_and_format(self):
        p = parse_progress_line('RC_PROGRESS  42.1%|3.20GiB|NA|5.10MiB/s|00:12:04')
        self.assertEqual(p['percent'], 42.1)
        self.assertEqual(format_progress(p), 'Downloading VOD: 42.1% of 3.20GiB at 5.10MiB/s, ETA 00:12:04')

    def test_uses_estimate_when_total_unknown(self):
        p = parse_progress_line('RC_PROGRESS 5.0%|NA|~1.50GiB|NA|NA')
        self.assertEqual(format_progress(p), 'Downloading VOD: 5.0% of ~1.50GiB')

    def test_real_ytdlp_unknown_marker_is_hidden(self):
        # Seen from yt-dlp 2026.10.26 on a live Twitch HLS VOD: total size printed as "N/A"
        p = parse_progress_line('RC_PROGRESS  74.6%|N/A|N/A|11.67MiB/s|00:07')
        self.assertEqual(format_progress(p), 'Downloading VOD: 74.6% at 11.67MiB/s, ETA 00:07')

    def test_ignores_other_lines(self):
        self.assertIsNone(parse_progress_line('[download] Destination: vod.mp4'))
        self.assertIsNone(parse_progress_line('RC_PROGRESS garbage'))


class TestDiskSpace(unittest.TestCase):
    def test_size_estimate_prefers_filesize_then_bitrate(self):
        self.assertEqual(estimate_size_bytes({'filesize': 1000}), 1000)
        self.assertEqual(estimate_size_bytes({'requested_formats': [{'filesize_approx': 10}, {'filesize': 5}]}), 15)
        self.assertEqual(estimate_size_bytes({'duration': 3600, 'tbr': 6000}), 3600 * 6_000_000 // 8)
        self.assertEqual(estimate_size_bytes({'duration': 10}), 10 * vod_import.FALLBACK_BITRATE_BPS // 8)

    def test_refuses_when_not_enough_room(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(VodImportError) as ctx:
                check_disk_space(d, 10_000_000_000, disk_usage=lambda _: Usage(0, 0, 11_000_000_000))
            self.assertIn('Not enough disk space', str(ctx.exception))
            self.assertIn('12.0 GB', str(ctx.exception))

    def test_accepts_with_margin(self):
        with tempfile.TemporaryDirectory() as d:
            free, required = check_disk_space(d, 10_000_000_000, disk_usage=lambda _: Usage(0, 0, 12_500_000_000))
            self.assertEqual(required, 12_000_000_000)


class TestChatNormalization(unittest.TestCase):
    RAW = {
        'video': {'id': '1'},
        'comments': [
            {'content_offset_seconds': 12.5, 'commenter': {'display_name': 'Bob', 'name': 'bob'},
             'message': {'body': 'KEKW', 'fragments': [{'text': 'KEKW'}]}},
            {'content_offset_seconds': 3, 'commenter': {'name': 'alice'},
             'message': {'fragments': [{'text': 'hi '}, {'text': 'chat'}]}},
            {'content_offset_seconds': 'bad', 'commenter': {}, 'message': {'body': 'skip me'}},
        ],
    }

    def test_normalizes_sorts_and_skips_bad_rows(self):
        msgs = normalize_twitch_chat(self.RAW)
        self.assertEqual(msgs, [
            {'t': 3.0, 'author': 'alice', 'message': 'hi chat'},
            {'t': 12.5, 'author': 'Bob', 'message': 'KEKW'},
        ])

    def test_jsonl_round_trip_keeps_unicode(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'chat.jsonl')
            write_chat_jsonl([{'t': 1.0, 'author': 'é', 'message': '🔥 W'}], path)
            with open(path, encoding='utf-8') as f:
                lines = f.read().splitlines()
            self.assertEqual(json.loads(lines[0]), {'t': 1.0, 'author': 'é', 'message': '🔥 W'})


@unittest.skipUnless(vod_import.shutil.which('ffmpeg') and vod_import.shutil.which('ffprobe'), 'needs ffmpeg')
class TestNormalizeStart(unittest.TestCase):
    """Twitch HLS VODs keep stream timestamps (seen: start_time=62s), which breaks chat alignment."""

    def _offset_clip(self, d):
        path = os.path.join(d, 'vod.mp4')
        import subprocess
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc=d=2:s=160x90',
                        '-f', 'lavfi', '-i', 'sine=d=2', '-shortest', '-output_ts_offset', '30',
                        '-c:v', 'libx264', '-c:a', 'aac', path], check=True)
        return path

    def test_retimes_offset_vod_to_zero(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._offset_clip(d)
            self.assertGreater(vod_import.probe_start_time(path), 29)
            offset = vod_import.normalize_start(path, log=lambda m: None)
            self.assertGreater(offset, 29)
            self.assertLess(vod_import.probe_start_time(path), 0.1)
            self.assertFalse(os.path.exists(path + '.zero.mp4'))

    def test_keeps_file_and_warns_without_room_for_a_copy(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._offset_clip(d)
            logs = []
            vod_import.normalize_start(path, log=logs.append, disk_usage=lambda _: Usage(0, 0, 10))
            self.assertGreater(vod_import.probe_start_time(path), 29)
            self.assertTrue(any("isn't room" in m for m in logs))


class TestImportOrchestration(unittest.TestCase):
    def test_kick_is_video_only(self):
        with tempfile.TemporaryDirectory() as d:
            def fake_download(url, out_dir, platform, log):
                open(os.path.join(out_dir, 'vod.mp4'), 'wb').close()
                return os.path.join(out_dir, 'vod.mp4')
            with mock.patch.object(vod_import, 'probe', return_value={'title': 'K', 'duration': 60, 'filesize': 10}), \
                 mock.patch.object(vod_import, 'download_video', side_effect=fake_download), \
                 mock.patch.object(vod_import, 'download_twitch_chat') as chat:
                r = vod_import.import_vod(7, 'https://kick.com/a/videos/1a2b3c4d-0000-1111-2222-333344445555',
                                          storage_app=d, log=lambda m: None)
            chat.assert_not_called()
            self.assertEqual(r['chat_status'], 'unavailable')
            self.assertEqual(r['title'], 'K')

    def test_chat_failure_does_not_fail_the_import_and_rerun_skips_download(self):
        with tempfile.TemporaryDirectory() as d:
            def fake_download(url, out_dir, platform, log):
                open(os.path.join(out_dir, 'vod.mp4'), 'wb').close()
                return os.path.join(out_dir, 'vod.mp4')
            logs = []
            with mock.patch.object(vod_import, 'probe', return_value={'title': 'T', 'duration': 60, 'filesize': 10}), \
                 mock.patch.object(vod_import, 'download_video', side_effect=fake_download) as dl, \
                 mock.patch.object(vod_import, 'download_twitch_chat', side_effect=VodImportError('boom')):
                r = vod_import.import_vod(8, 'https://www.twitch.tv/videos/1', storage_app=d, log=logs.append)
                self.assertEqual(r['chat_status'], 'failed')
                self.assertTrue(any('CHAT WARNING' in m for m in logs))
                vod_import.import_vod(8, 'https://www.twitch.tv/videos/1', storage_app=d, log=logs.append)
                self.assertEqual(dl.call_count, 1)  # second run reused the finished file

    def test_video_error_propagates_as_vod_import_error(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(vod_import, 'probe', side_effect=VodImportError('This Twitch VOD is subscriber-only.')):
                with self.assertRaises(VodImportError):
                    vod_import.import_vod(9, 'https://www.twitch.tv/videos/1', storage_app=d, log=lambda m: None)


if __name__ == '__main__':
    unittest.main()
