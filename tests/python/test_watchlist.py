import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'processor')))

import numpy as np

import live_clips
import vod_import
import watchlist
from vod_import import VodImportError, find_offset, section_bounds, cleanup_sparse_files
from watchlist import (
    build_settings, failure_reason, parse_vod_list, pick_base_settings, plan_new_vods,
)


def vod(i, duration=36000, title=None):
    return {'id': str(i), 'duration': duration, 'title': title or f'Stream {i}'}


# ─── Pure watchlist helpers ───────────────────────────────────────────────────

class TestParseVodList(unittest.TestCase):
    def test_real_ytdlp_lines(self):
        out = ("v2932305259|57825.0|PLAYING GTA 6 FOR THE FIRST TIME\n"
               "v2924282282|126420.0| PLAYING EVERY GTA UNTIL I BEAT IT: Grand Theft Auto 4\n")
        self.assertEqual(parse_vod_list(out), [
            {'id': '2932305259', 'duration': 57825, 'title': 'PLAYING GTA 6 FOR THE FIRST TIME'},
            {'id': '2924282282', 'duration': 126420, 'title': 'PLAYING EVERY GTA UNTIL I BEAT IT: Grand Theft Auto 4'},
        ])

    def test_title_with_pipes_and_missing_fields(self):
        out = "v1|NA|a | b | c\nv2|60\ngarbage\n|1|x\n"
        self.assertEqual(parse_vod_list(out), [
            {'id': '1', 'duration': None, 'title': 'a | b | c'},
            {'id': '2', 'duration': 60, 'title': None},
        ])


class TestPlanNewVods(unittest.TestCase):
    def test_first_check_queues_only_the_newest(self):
        plan = plan_new_vods([vod(3), vod(2), vod(1)], set(), first_check=True, live=False)
        self.assertEqual([(v['id'], s) for v, s, _ in plan], [('3', 'queued'), ('2', 'skipped'), ('1', 'skipped')])

    def test_later_checks_queue_every_new_vod(self):
        plan = plan_new_vods([vod(5), vod(4), vod(3)], {'3'}, first_check=False, live=False)
        self.assertEqual([(v['id'], s) for v, s, _ in plan], [('5', 'queued'), ('4', 'queued')])

    def test_live_channel_leaves_the_recording_vod_for_later(self):
        plan = plan_new_vods([vod(5), vod(4)], {'4'}, first_check=False, live=True)
        self.assertEqual(plan, [])
        # first check while live: the newest *finished* VOD is the one queued
        plan = plan_new_vods([vod(5), vod(4), vod(3)], set(), first_check=True, live=True)
        self.assertEqual([(v['id'], s) for v, s, _ in plan], [('4', 'queued'), ('3', 'skipped')])

    def test_short_vods_are_skipped_and_dont_use_up_the_first_pick(self):
        plan = plan_new_vods([vod(3, duration=120), vod(2), vod(1)], set(), first_check=True, live=False)
        self.assertEqual([(v['id'], s) for v, s, _ in plan], [('3', 'skipped'), ('2', 'queued'), ('1', 'skipped')])
        self.assertEqual(plan[0][2], 'Shorter than 5 minutes')


class TestSettings(unittest.TestCase):
    def test_base_is_latest_dashboard_stream_moments_job(self):
        rows = [json.dumps({'stream_moments': True, 'watchlist': True, 'caption_style': 'x'}),
                json.dumps({'stream_moments': False, 'caption_style': 'y'}),
                'not json',
                json.dumps({'stream_moments': True, 'caption_style': 'cyber_pink', 'gaming_layout': True})]
        self.assertEqual(pick_base_settings(rows)['caption_style'], 'cyber_pink')
        self.assertEqual(pick_base_settings([]), {})

    def test_build_settings_keeps_prefs_and_forces_watchlist_mode(self):
        base = {'caption_style': 'cyber_pink', 'gaming_layout': True, 'target_clip_count': 9,
                'full_video_mode': True, 'source_url': 'old', 'chat_path': '/x'}
        s = build_settings(base, 'kaicenat', '2932305259')
        self.assertEqual(s['caption_style'], 'cyber_pink')
        self.assertTrue(s['gaming_layout'])
        self.assertEqual(s['target_clip_count'], 3)
        self.assertFalse(s['full_video_mode'])
        self.assertTrue(s['stream_moments'] and s['sparse_download'] and s['watchlist'])
        self.assertEqual(s['source_url'], 'https://www.twitch.tv/videos/2932305259')
        self.assertNotIn('chat_path', s)

    def test_failure_reason(self):
        self.assertEqual(failure_reason('', {'import_error': 'gone'}), 'Import failed: gone')
        self.assertEqual(failure_reason('a\nPipeline failed: boom\nb', {}), 'boom')
        self.assertIn('without a clear error', failure_reason('', {}))


class TestVodIsRecording(unittest.TestCase):
    def run_with(self, returncode, stdout):
        done = subprocess.CompletedProcess([], returncode, stdout=stdout, stderr='')
        with mock.patch.object(watchlist, '_ytdlp', return_value=done):
            return watchlist.vod_is_recording('2932305259')

    def test_reads_twitch_live_status(self):
        self.assertTrue(self.run_with(0, 'is_live\n'))
        self.assertFalse(self.run_with(0, 'was_live\n'))
        self.assertIsNone(self.run_with(1, ''))
        self.assertIsNone(self.run_with(0, 'NA\n'))

    def test_timeout_is_unknown(self):
        with mock.patch.object(watchlist, '_ytdlp', side_effect=subprocess.TimeoutExpired('yt-dlp', 90)):
            self.assertIsNone(watchlist.vod_is_recording('1'))


class TestLockAndHeartbeat(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_only_one_watcher_holds_the_lock(self):
        path = os.path.join(self.dir, 'watcher.lock')
        first = watchlist.acquire_lock(path)
        self.assertIsNotNone(first)
        try:
            self.assertIsNone(watchlist.acquire_lock(path))
        finally:
            first.close()
        again = watchlist.acquire_lock(path)
        self.assertIsNotNone(again)
        again.close()

    def test_heartbeat_writes_json(self):
        hb = watchlist.Heartbeat(os.path.join(self.dir, 'heartbeat.json'))
        hb.beat(state='idle')
        with open(hb.path, encoding='utf-8') as f:
            data = json.load(f)
        self.assertEqual(data['state'], 'idle')
        self.assertIn('updated_at', data)


# ─── Watchlist against a real SQLite schema ───────────────────────────────────

SCHEMA = """
CREATE TABLE long_videos (id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT, storage_path TEXT, status TEXT,
  transcript TEXT, processing_settings TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE video_clips (id INTEGER PRIMARY KEY AUTOINCREMENT, long_video_id INTEGER, start_time TEXT, end_time TEXT,
  hook_explanation TEXT, crop_coordinates_json TEXT, output_path TEXT, status TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE watch_channels (id INTEGER PRIMARY KEY AUTOINCREMENT, login TEXT UNIQUE, enabled INTEGER DEFAULT 1,
  last_checked_at TEXT, last_error TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE watch_vods (id INTEGER PRIMARY KEY AUTOINCREMENT, watch_channel_id INTEGER, vod_id TEXT UNIQUE, title TEXT,
  duration_s INTEGER, status TEXT DEFAULT 'queued', long_video_id INTEGER, error TEXT, created_at TEXT, updated_at TEXT);
"""


class TestWatchlistDb(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.dir, 'test.sqlite')
        con = sqlite3.connect(self.db_path)
        con.executescript(SCHEMA)
        con.execute("INSERT INTO watch_channels (login) VALUES ('kaicenat')")
        con.execute("INSERT INTO watch_channels (login, enabled) VALUES ('paused_one', 0)")
        con.commit()
        con.close()
        self.env = mock.patch.dict(os.environ, {'DB_CONNECTION': 'sqlite', 'DB_DATABASE': self.db_path})
        self.env.start()
        self.db = watchlist.get_db()

    def tearDown(self):
        self.db.close()
        self.env.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def rows(self, sql, params=()):
        cur = self.db.cursor()
        cur.execute(sql, params)
        return cur.fetchall()

    def test_check_queues_newest_then_new_ones_and_skips_paused_channels(self):
        listings = {'kaicenat': [vod(300), vod(200), vod(100)]}
        with mock.patch.object(watchlist, 'list_channel_vods', side_effect=lambda l: listings[l]) as lister, \
                mock.patch.object(watchlist, 'vod_is_recording', return_value=False):
            self.assertEqual(watchlist.check_all(self.db), 1)
            lister.assert_called_once_with('kaicenat')
            listings['kaicenat'] = [vod(500), vod(400), vod(300)]
            self.assertEqual(watchlist.check_all(self.db), 2)
        status = {r['vod_id']: r['status'] for r in self.rows("SELECT vod_id, status FROM watch_vods")}
        self.assertEqual(status, {'300': 'queued', '200': 'skipped', '100': 'skipped', '400': 'queued', '500': 'queued'})
        # newest first across the queue
        self.assertEqual(watchlist.next_queued(self.db)['vod_id'], '500')
        ch = self.rows("SELECT * FROM watch_channels WHERE login = 'kaicenat'")[0]
        self.assertIsNotNone(ch['last_checked_at'])
        self.assertIsNone(ch['last_error'])

    def test_recording_vod_waits_and_is_only_asked_about_when_new(self):
        listings = {'kaicenat': [vod(300), vod(200)]}
        with mock.patch.object(watchlist, 'list_channel_vods', side_effect=lambda l: listings[l]), \
                mock.patch.object(watchlist, 'vod_is_recording', return_value=True) as rec:
            watchlist.check_all(self.db)
            rec.assert_called_once_with('300')
        self.assertEqual({r['vod_id']: r['status'] for r in self.rows("SELECT vod_id, status FROM watch_vods")},
                         {'200': 'queued'})
        # Stream ended: 300 is now finished and gets queued
        with mock.patch.object(watchlist, 'list_channel_vods', side_effect=lambda l: listings[l]), \
                mock.patch.object(watchlist, 'vod_is_recording', return_value=False):
            self.assertEqual(watchlist.check_all(self.db), 1)
        # Newest already known: no extra request
        with mock.patch.object(watchlist, 'list_channel_vods', side_effect=lambda l: listings[l]), \
                mock.patch.object(watchlist, 'vod_is_recording') as rec:
            watchlist.check_all(self.db)
            rec.assert_not_called()

    def test_listing_error_is_recorded_not_raised(self):
        with mock.patch.object(watchlist, 'list_channel_vods', side_effect=RuntimeError('channel does not exist')), \
                mock.patch.object(watchlist, 'vod_is_recording', return_value=False):
            self.assertEqual(watchlist.check_all(self.db), 0)
        ch = self.rows("SELECT * FROM watch_channels WHERE login = 'kaicenat'")[0]
        self.assertIn('channel does not exist', ch['last_error'])

    def test_prepare_creates_job_with_dashboard_prefs_then_resets_on_rerun(self):
        cur = self.db.cursor()
        cur.execute("INSERT INTO long_videos (filename, storage_path, status, processing_settings) VALUES ('a', 'x', 'completed', %s)",
                    (json.dumps({'stream_moments': True, 'caption_style': 'cyber_pink'}),))
        cur.execute("INSERT INTO watch_vods (watch_channel_id, vod_id, title, status) VALUES (1, '777', 'Big Stream', 'queued')")
        self.db.commit()
        wv = watchlist.next_queued(self.db)
        vid = watchlist.prepare_long_video(self.db, wv)
        job = self.rows("SELECT * FROM long_videos WHERE id = %s", (vid,))[0]
        settings = json.loads(job['processing_settings'])
        self.assertEqual(job['filename'], 'kaicenat · Big Stream')
        self.assertEqual(job['status'], 'pending')
        self.assertEqual(settings['caption_style'], 'cyber_pink')
        self.assertTrue(settings['sparse_download'])
        self.assertEqual(settings['target_clip_count'], 3)

        # Interrupted run: clips from the first attempt are removed and the same job is reused
        cur.execute("INSERT INTO video_clips (long_video_id, start_time, end_time, hook_explanation, status) "
                    "VALUES (%s, '00:00:01', '00:00:31', '{}', 'ready')", (vid,))
        cur.execute("UPDATE watch_vods SET status = 'processing', long_video_id = %s", (vid,))
        self.db.commit()
        watchlist.recover_interrupted(self.db)
        wv = watchlist.next_queued(self.db)
        self.assertEqual(wv['vod_id'], '777')
        self.assertEqual(watchlist.prepare_long_video(self.db, wv), vid)
        self.assertEqual(self.rows("SELECT COUNT(*) AS n FROM video_clips")[0]['n'], 0)

    def test_process_vod_marks_done_or_failed_from_the_job(self):
        cur = self.db.cursor()
        cur.execute("INSERT INTO watch_vods (watch_channel_id, vod_id, status) VALUES (1, '888', 'queued')")
        self.db.commit()
        hb = mock.MagicMock()

        def finish(status, settings=None):
            def run(video_id, heartbeat):
                c = watchlist.get_db()
                cc = c.cursor()
                cc.execute("UPDATE long_videos SET status = %s, processing_settings = %s WHERE id = %s",
                           (status, json.dumps(settings or {}), video_id))
                c.commit()
                c.close()
                return 'Pipeline process finished.'
            return run

        with mock.patch.object(watchlist, 'run_engine', side_effect=finish('completed')):
            watchlist.process_vod(self.db, watchlist.next_queued(self.db), hb)
        row = self.rows("SELECT * FROM watch_vods WHERE vod_id = '888'")[0]
        self.assertEqual((row['status'], row['error']), ('done', None))

        cur.execute("UPDATE watch_vods SET status = 'queued'")
        self.db.commit()
        with mock.patch.object(watchlist, 'run_engine', side_effect=finish('failed', {'import_error': 'VOD deleted'})), \
                mock.patch.object(watchlist, 'cleanup_sparse_files') as cleanup:
            watchlist.process_vod(self.db, watchlist.next_queued(self.db), hb)
        row = self.rows("SELECT * FROM watch_vods WHERE vod_id = '888'")[0]
        self.assertEqual((row['status'], row['error']), ('failed', 'Import failed: VOD deleted'))
        cleanup.assert_called_once()


class TestLiveMoments(TestWatchlistDb.__base__):
    """process_live_moment: chat flood -> wait for the live VOD -> download window -> one-clip job."""
    AT = 1_795_000_000

    setUp = TestWatchlistDb.setUp
    rows = TestWatchlistDb.rows

    def tearDown(self):
        self.queue_patch.stop()
        TestWatchlistDb.tearDown(self)

    def queue(self, **moment):
        self.queue_patch = mock.patch.object(live_clips, 'QUEUE_PATH', os.path.join(self.dir, 'live_moments.json'))
        self.queue_patch.start()
        m = live_clips.add_moment('kaicenat', {'at': self.AT, 'rate': 12.0, 'baseline': 3.0, 'z': 8.0})
        if moment:
            live_clips.update_moment(m['id'], **moment)
            m.update(moment)
        return m

    def stored(self):
        return live_clips.load_queue()[0]

    def run_moment(self, m, timing, now, download=None, engine_status='completed'):
        def engine(video_id, heartbeat):
            c = watchlist.get_db()
            c.cursor().execute("UPDATE long_videos SET status = %s WHERE id = %s", (engine_status, video_id))
            c.commit()
            c.close()
            return ''
        with mock.patch.object(watchlist, 'list_channel_vods', return_value=[vod(900)]), \
                mock.patch.object(watchlist, 'vod_timing', return_value=timing), \
                mock.patch.object(watchlist, 'download_live_section', **(download or {'return_value': 'D:/x/live.mp4'})) as dl, \
                mock.patch.object(watchlist, 'run_engine', side_effect=engine), \
                mock.patch.object(watchlist, 'vod_dir', return_value=self.dir), \
                mock.patch.object(watchlist.time, 'time', return_value=now):
            worked = watchlist.process_live_moment(self.db, m, mock.MagicMock())
        return worked, dl

    def test_waits_while_the_vod_is_behind(self):
        m = self.queue()
        worked, dl = self.run_moment(m, (self.AT - 3600, 3605), now=self.AT + 40)
        self.assertFalse(worked)
        dl.assert_not_called()
        self.assertEqual(self.stored()['status'], 'waiting')
        self.assertEqual(self.stored()['next_try'], self.AT + 40 + live_clips.RETRY_S)
        self.assertEqual(self.rows("SELECT COUNT(*) AS n FROM long_videos")[0]['n'], 0)

    def test_ready_moment_becomes_a_one_clip_job_with_dashboard_prefs(self):
        cur = self.db.cursor()
        cur.execute("INSERT INTO long_videos (filename, storage_path, status, processing_settings) VALUES ('a', 'x', 'completed', %s)",
                    (json.dumps({'stream_moments': True, 'caption_style': 'cyber_pink'}),))
        self.db.commit()
        m = self.queue()
        worked, dl = self.run_moment(m, (self.AT - 3600, 3700), now=self.AT + 120)
        self.assertTrue(worked)
        self.assertEqual(dl.call_args[0][3:5], (3600 - live_clips.PRE_S, 3600 + live_clips.POST_S))
        job = self.rows("SELECT * FROM long_videos ORDER BY id DESC LIMIT 1")[0]
        settings = json.loads(job['processing_settings'])
        self.assertEqual(job['storage_path'], 'D:/x/live.mp4')
        self.assertTrue(job['filename'].startswith('kaicenat · LIVE chat spike'))
        self.assertTrue(settings['full_video_mode'])
        self.assertEqual(settings['caption_style'], 'cyber_pink')
        self.assertEqual((self.stored()['status'], self.stored()['long_video_id']), ('done', job['id']))

    def test_download_failure_retries_then_fails_without_empty_jobs(self):
        m = self.queue()
        broken = {'side_effect': watchlist.VodImportError('Download failed: ffmpeg exited')}
        for i in range(live_clips.DOWNLOAD_TRIES):
            self.run_moment(self.stored(), (self.AT - 3600, 3700), now=self.AT + 120 + i * 60, download=broken)
        self.assertEqual(self.stored()['status'], 'failed')
        self.assertIn('ffmpeg', self.stored()['error'])
        self.assertEqual(self.rows("SELECT COUNT(*) AS n FROM long_videos")[0]['n'], 0)

    def test_moment_outside_the_saved_vod_is_dropped(self):
        m = self.queue()
        worked, dl = self.run_moment(m, (self.AT + 600, 100), now=self.AT + 800)
        self.assertFalse(worked)
        self.assertEqual(self.stored()['status'], 'failed')

    def test_engine_failure_is_recorded(self):
        m = self.queue()
        self.run_moment(m, (self.AT - 3600, 3700), now=self.AT + 120, engine_status='failed')
        self.assertEqual(self.stored()['status'], 'failed')


# ─── Sparse download helpers ──────────────────────────────────────────────────

class TestFindOffset(unittest.TestCase):
    def test_recovers_exact_offset_in_noise(self):
        rng = np.random.default_rng(7)
        rate = 8000
        ref = rng.normal(size=rate * 60)
        probe = ref[int(23.5 * rate):int(43.5 * rate)] * 0.3 + rng.normal(scale=0.05, size=rate * 20)
        lag, match = find_offset(probe, ref, rate)
        self.assertAlmostEqual(lag, 23.5, places=3)
        self.assertGreater(match, 0.9)

    def test_unrelated_sound_scores_low(self):
        rng = np.random.default_rng(1)
        _, match = find_offset(rng.normal(size=8000 * 5), rng.normal(size=8000 * 30))
        self.assertLess(match, vod_import.ALIGN_MIN_MATCH)

    def test_degenerate_inputs(self):
        self.assertEqual(find_offset([], [1.0, 2.0]), (0.0, 0.0))
        self.assertEqual(find_offset(np.zeros(10), np.ones(100)), (0.0, 0.0))
        self.assertEqual(find_offset(np.ones(100), np.ones(10)), (0.0, 0.0))


class TestSectionBounds(unittest.TestCase):
    def test_pads_and_clamps(self):
        self.assertEqual(section_bounds(7215.4, 7260.2), (7200, 7276))
        self.assertEqual(section_bounds(5.0, 40.0), (0, 55))
        self.assertEqual(section_bounds(990.0, 1000.0, duration=1002.5), (975, 1003))


class TestFetchClipSource(unittest.TestCase):
    def test_uses_sound_alignment(self):
        with mock.patch.object(vod_import, 'download_section', return_value='s.mp4'), \
                mock.patch.object(vod_import, 'align_section', return_value=(7190.0, 0.97)), \
                mock.patch.object(vod_import, 'probe_duration', return_value=76.0), \
                mock.patch('os.path.exists', return_value=True):
            path, offset = vod_import.fetch_clip_source('u', 'twitch', 'd', 1, 7205.0, 7250.0, audio_path='a.mp4',
                                                        log=lambda m: None)
        self.assertEqual((path, offset), ('s.mp4', 7190.0))

    def test_rejects_window_that_misses_the_clip(self):
        with mock.patch.object(vod_import, 'download_section', return_value='s.mp4'), \
                mock.patch.object(vod_import, 'align_section', return_value=(7230.0, 0.97)), \
                mock.patch.object(vod_import, 'probe_duration', return_value=76.0), \
                mock.patch('os.path.exists', return_value=True):
            with self.assertRaises(VodImportError):
                vod_import.fetch_clip_source('u', 'twitch', 'd', 1, 7205.0, 7250.0, audio_path='a.mp4',
                                             log=lambda m: None)

    def test_without_audio_trusts_the_requested_start(self):
        with mock.patch.object(vod_import, 'download_section', return_value='s.mp4') as dl:
            path, offset = vod_import.fetch_clip_source('u', 'twitch', 'd', 1, 7205.0, 7250.0, audio_path=None,
                                                        log=lambda m: None)
        self.assertEqual(offset, 7190.0)
        self.assertEqual(dl.call_args[0][3:5], (7190, 7265))


class TestImportVodSparse(unittest.TestCase):
    def setUp(self):
        self.storage = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.storage, ignore_errors=True)

    def fake_download(self, url, out_dir, platform, log, fmt, name, label):
        path = os.path.join(out_dir, f'{name}.mp4')
        with open(path, 'wb') as f:
            f.write(b'x' * 10)
        return path

    def fake_chat(self, platform, vod_id, out_dir, log, without):
        return 'saved', os.path.join(out_dir, 'chat.jsonl'), 42

    def test_downloads_audio_and_chat_not_video(self):
        info = {'title': 'Big Stream', 'duration': 36000, 'filesize_approx': 1_000_000}
        with mock.patch.object(vod_import, 'probe', return_value=info) as probe, \
                mock.patch.object(vod_import, 'download_video', side_effect=self.fake_download) as dl, \
                mock.patch.object(vod_import, 'normalize_start', return_value=0.0), \
                mock.patch.object(vod_import, 'fetch_chat', side_effect=self.fake_chat):
            out = vod_import.import_vod_sparse(5, 'https://www.twitch.tv/videos/123', self.storage, log=lambda m: None)
        self.assertEqual(probe.call_args[0][2], vod_import.AUDIO_FORMAT)
        self.assertEqual(dl.call_args.kwargs['fmt'], vod_import.AUDIO_FORMAT)
        self.assertTrue(out['path'].endswith('audio.mp4'))
        self.assertEqual((out['audio_status'], out['chat_status'], out['duration']), ('saved', 'saved', 36000))

    def test_audio_failure_falls_back_to_chat_only(self):
        def probe(url, platform, fmt=vod_import.VIDEO_FORMAT):
            if fmt == vod_import.AUDIO_FORMAT:
                raise VodImportError('Requested format is not available')
            return {'title': 'Big Stream', 'duration': 36000}
        with mock.patch.object(vod_import, 'probe', side_effect=probe), \
                mock.patch.object(vod_import, 'fetch_chat', side_effect=self.fake_chat):
            out = vod_import.import_vod_sparse(5, 'https://www.twitch.tv/videos/123', self.storage, log=lambda m: None)
        self.assertIsNone(out['path'])
        self.assertEqual((out['audio_status'], out['duration']), ('failed', 36000))

    def test_no_audio_and_no_chat_is_an_error(self):
        with mock.patch.object(vod_import, 'probe', side_effect=[VodImportError('nope'), {'duration': 100}]), \
                mock.patch.object(vod_import, 'fetch_chat', return_value=('failed', 'x', None)):
            with self.assertRaises(VodImportError):
                vod_import.import_vod_sparse(5, 'https://www.twitch.tv/videos/123', self.storage, log=lambda m: None)

    def test_cleanup_keeps_chat_and_meta(self):
        d = vod_import.vod_dir(9, self.storage)
        os.makedirs(d)
        for name in ('audio.mp4', 'section_1.mp4', 'section_2.mp4.part', 'chat.jsonl'):
            with open(os.path.join(d, name), 'wb') as f:
                f.write(b'1234')
        with open(os.path.join(d, 'meta.json'), 'w') as f:
            json.dump({'audio_complete': True}, f)
        self.assertEqual(cleanup_sparse_files(9, self.storage), 12)
        self.assertEqual(sorted(os.listdir(d)), ['chat.jsonl', 'meta.json'])
        with open(os.path.join(d, 'meta.json')) as f:
            self.assertFalse(json.load(f)['audio_complete'])


if __name__ == '__main__':
    unittest.main()
