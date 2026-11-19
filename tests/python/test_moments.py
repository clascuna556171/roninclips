import io
import json
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'processor')))

import moments
from moments import (
    CHAT_LAG_S, chat_series, clip_window, combine_scores, describe, detect_moments_from_signals,
    load_chat, loudness_from_pcm, normalize_message, pick_peaks, rolling_zscore,
)
from engine import build_moment_prompt, merge_moment_picks, moment_fallback_meta


def synthetic_loudness(duration, base=-30.0, seed=1):
    rng = np.random.default_rng(seed)
    return base + rng.normal(0, 0.5, duration)


def steady_chat(duration, per_second, text='hello chat'):
    return [(s + 0.5, f"{text} {s}") for s in range(duration) for _ in range(per_second)]


class TestChatParsing(unittest.TestCase):
    def test_normalize_message_collapses_spam(self):
        self.assertEqual(normalize_message('KEKW KEKW kekw!!!'), 'kekw')
        self.assertEqual(normalize_message('  W  '), 'w')
        self.assertEqual(normalize_message(None), '')

    def test_load_chat_skips_bad_lines(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'chat.jsonl')
            with open(p, 'w', encoding='utf-8') as f:
                f.write(json.dumps({'t': 1.5, 'author': 'a', 'message': 'hi'}) + '\n')
                f.write('not json\n\n')
                f.write(json.dumps({'author': 'no time'}) + '\n')
                f.write(json.dumps({'t': '3', 'author': 'b', 'message': 'yo'}) + '\n')
            self.assertEqual(load_chat(p), [(1.5, 'hi'), (3.0, 'yo')])

    def test_chat_series_counts_duplicates_double(self):
        msgs = [(0.1, 'KEKW'), (0.5, 'kekw kekw'), (0.9, 'lol'), (2.2, 'one'), (2.4, 'two'), (99, 'out of range')]
        activity, raw = chat_series(msgs, 3)
        self.assertEqual(raw.tolist(), [3, 0, 2])
        self.assertEqual(activity.tolist(), [5, 0, 2])  # 3 msgs + 2 identical 'kekw'


class TestScoring(unittest.TestCase):
    def test_flat_signal_scores_zero_and_spike_is_capped(self):
        x = np.full(300, 2.0)
        self.assertEqual(rolling_zscore(x, floor=0.5).max(), 0.0)
        x[200] = 1000.0
        z = rolling_zscore(x, floor=0.5)
        self.assertEqual(z[200], moments.Z_CAP)
        self.assertEqual(z[199], 0.0)

    def test_smoothing_edges_do_not_fake_a_spike(self):
        x = np.full(50, -30.0)
        s = moments.smooth(x, 5)
        self.assertEqual(len(s), 50)
        self.assertTrue(np.allclose(s, -30.0))  # zero padding would push the edges toward 0 dB

    def test_downward_dips_do_not_count(self):
        x = np.full(300, -30.0)
        x[150] = -60.0
        self.assertEqual(rolling_zscore(x, floor=1.0).max(), 0.0)

    def test_loudness_from_pcm(self):
        rate = 8000
        silence = np.zeros(rate, dtype='<i2')
        t = np.arange(rate) / rate
        tone = (0.5 * 32767 * np.sin(2 * np.pi * 440 * t)).astype('<i2')
        half = tone[: rate // 2]
        loud = loudness_from_pcm(io.BytesIO(silence.tobytes() + tone.tobytes() + half.tobytes()), rate, chunk_seconds=1)
        self.assertEqual(len(loud), 3)          # 2 full seconds + a trailing half second
        self.assertLess(loud[0], -100)          # silence
        self.assertAlmostEqual(loud[1], -9.0, delta=0.3)  # 0.5 amplitude sine -> ~-9 dBFS

    def test_chat_is_shifted_earlier_by_lag(self):
        audio = np.zeros(200)
        chat = np.zeros(200 + CHAT_LAG_S)
        chat[100 + CHAT_LAG_S] = 5.0
        score = combine_scores(audio, chat)
        self.assertEqual(int(np.argmax(score)), 100)
        self.assertAlmostEqual(score[100], moments.CHAT_WEIGHT * 5.0)

    def test_audio_only_score(self):
        audio = np.array([0.0, 2.0, 1.0])
        self.assertEqual(combine_scores(audio, None).tolist(), [0.0, 2.0, 1.0])

    def test_pick_peaks_respects_gap_and_positive_scores(self):
        score = np.zeros(400)
        score[100], score[130], score[250], score[390] = 9, 8, 7, -1
        self.assertEqual(pick_peaks(score, 5, min_gap_s=90), [100, 250])
        self.assertEqual(pick_peaks(score, 1, min_gap_s=90), [100])

    def test_short_burst_gets_minimum_window(self):
        s = np.zeros(600)
        s[100:103] = 5.0
        self.assertEqual(clip_window(s, 101, 600), (86.0, 116.0))  # 15s before, 30s total

    def test_sustained_activity_extends_window(self):
        s = np.zeros(600)
        s[100] = 5.0
        s[101:140] = 2.0       # stays above 35% of the peak for ~40s
        start, end = clip_window(s, 100, 600)
        self.assertEqual(start, 85.0)
        self.assertEqual(end, 144.0)  # last active second 139 + 5s tail
        s[101:200] = 2.0       # activity for 100s: capped at 60s total
        self.assertEqual(clip_window(s, 100, 600), (85.0, 145.0))
        s[101:125] = 2.0
        s[125:140] = 1.0       # drops below 1.75 at 125
        self.assertEqual(clip_window(s, 100, 600), (85.0, 129.0))

    def test_window_edges(self):
        s = np.zeros(600)
        self.assertEqual(clip_window(s, 5, 600), (0.0, 30.0))
        self.assertEqual(clip_window(s, 595, 600), (570.0, 600.0))  # shifted back, not shrunk
        self.assertEqual(clip_window(np.zeros(20), 10, 20), (0.0, 20.0))  # VOD shorter than a window


class TestDetector(unittest.TestCase):
    def test_chat_flood_and_audio_spike_found_at_event(self):
        duration = 900
        loud = synthetic_loudness(duration)
        loud[300:304] += 14            # streamer screams at 300s
        loud[600:603] += 6             # smaller audio-only bump later
        chat = steady_chat(duration, 1)
        for s in range(303, 311):      # chat floods ~3s later
            chat += [(s + 0.1 * i, 'KEKW') for i in range(10)]
        found = detect_moments_from_signals(loud, chat, 3)
        self.assertTrue(found)
        top = found[0]
        self.assertLessEqual(abs(top['peak'] - 301), 4)
        self.assertIn('Chat spiked', top['summary'])
        self.assertIn('audio peak', top['summary'])
        self.assertGreater(top['chat_msgs_10s'], 50)
        self.assertTrue(30.0 <= top['end'] - top['start'] <= 60.0)
        self.assertLessEqual(top['start'], 300)   # covers the scream
        self.assertGreaterEqual(top["end"], 311)  # and the chat flood after it
        peaks = [m['peak'] for m in found]
        self.assertTrue(any(abs(p - 601) <= 4 for p in peaks))
        for a in peaks:
            for b in peaks:
                if a != b:
                    self.assertGreaterEqual(abs(a - b), moments.MIN_GAP_S)

    def test_constantly_busy_chat_is_not_a_spike(self):
        duration = 600
        loud = synthetic_loudness(duration)
        loud[400:403] += 12
        found = detect_moments_from_signals(loud, steady_chat(duration, 20), 1)
        self.assertLessEqual(abs(found[0]['peak'] - 401), 4)
        self.assertLess(found[0]['chat_z'], 1.0)
        self.assertNotIn('Chat spiked', found[0]['summary'])

    def test_audio_only_when_no_chat(self):
        loud = synthetic_loudness(600)
        loud[200:203] += 12
        found = detect_moments_from_signals(loud, None, 2)
        self.assertLessEqual(abs(found[0]['peak'] - 201), 4)
        self.assertIsNone(found[0]['chat_msgs_10s'])
        self.assertTrue(found[0]['summary'].startswith('Audio peak'))

    def test_talk_after_silent_intro_is_not_a_spike(self):
        # "Starting soon" screen with no audio, then normal talking, then a real scream
        loud = synthetic_loudness(1200)
        loud[:300] = -120.0            # digital silence
        loud[900:903] += 12
        found = detect_moments_from_signals(loud, None, 1)
        self.assertLessEqual(abs(found[0]['peak'] - 901), 4)
        self.assertLess(found[0]['audio_db_above'], 20)

    def test_silence_is_left_out_of_the_baseline(self):
        x = np.full(400, -30.0)
        x[:200] = -120.0
        z = rolling_zscore(x, floor=1.0, ignore_below=moments.SILENCE_DB)
        self.assertEqual(z[200:].max(), 0.0)              # talking resumes: no spike
        self.assertEqual(rolling_zscore(x, floor=1.0)[200], moments.Z_CAP)  # old behaviour
        x[300] = -10.0
        z = rolling_zscore(x, floor=1.0, ignore_below=moments.SILENCE_DB)
        self.assertEqual(z[300], moments.Z_CAP)           # a real spike still counts

    def test_all_silent_audio_does_not_crash(self):
        z = rolling_zscore(np.full(100, -120.0), floor=1.0, ignore_below=moments.SILENCE_DB)
        self.assertEqual(z.max(), 0.0)

    def test_empty_inputs(self):
        self.assertEqual(detect_moments_from_signals([], None, 3), [])
        self.assertEqual(detect_moments_from_signals(synthetic_loudness(100), None, 0), [])

    def test_describe_fallback_text(self):
        self.assertIn('Strongest', describe({'chat_z': 0, 'audio_z': 0, 'chat_msgs_10s': None}))


def make_candidate(i, start, score=5.0):
    m = {'peak': start + 25.0, 'start': float(start), 'end': float(start + 40), 'score': score,
         'audio_z': 3.0, 'audio_db_above': 9.0, 'chat_z': 4.0, 'chat_msgs_10s': 120, 'chat_ratio': 8.0,
         'excerpt': f'excerpt {i}'}
    m['summary'] = describe(m)
    return m


class TestEngineMomentHelpers(unittest.TestCase):
    def test_fallback_meta(self):
        meta = moment_fallback_meta(make_candidate(0, 100))
        self.assertEqual(meta['source'], 'stream_moments')
        self.assertEqual(meta['title'], 'Stream moment at 00:02:05')
        self.assertEqual(meta['reason'], 'Chat spiked 8x (120 msgs in 10s) + audio peak (+9 dB)')
        self.assertEqual(meta['signals']['chat_msgs_10s'], 120)
        self.assertTrue(50 <= meta['virality_score'] <= 99)

    def test_merge_prefers_groq_picks_then_fills_by_detector_rank(self):
        cands = [make_candidate(0, 500), make_candidate(1, 100), make_candidate(2, 300)]
        picks = [
            {'id': 2, 'title': 'Insane clutch', 'virality_score': 150},
            {'id': 2, 'title': 'dup'},
            {'id': 9, 'title': 'out of range'},
            {'id': 'x'},
            'not a dict',
        ]
        chosen = merge_moment_picks(cands, picks, 2)
        self.assertEqual([m['start'] for m, _ in chosen], [300.0, 500.0])  # sorted by time
        metas = {m['start']: meta for m, meta in chosen}
        self.assertEqual(metas[300.0]['title'], 'Insane clutch')
        self.assertEqual(metas[300.0]['virality_score'], 100)               # clamped
        self.assertEqual(metas[300.0]['signal_summary'], cands[2]['summary'])  # signals kept
        self.assertEqual(metas[500.0]['title'], 'Stream moment at 00:08:45')  # filled from rank 0

    def test_merge_without_groq(self):
        cands = [make_candidate(0, 500), make_candidate(1, 100)]
        self.assertEqual(len(merge_moment_picks(cands, None, 5)), 2)

    def test_prompt_lists_ids_and_marks_silence(self):
        cands = [make_candidate(0, 100), make_candidate(1, 300)]
        cands[1]['excerpt'] = ''
        prompt = build_moment_prompt(cands, 1)
        self.assertIn('Moment 0: 00:01:40-00:02:20', prompt)
        self.assertIn('Moment 1:', prompt)
        self.assertIn('(no clear speech)', prompt)
        self.assertIn('Pick the best 1', prompt)


if __name__ == '__main__':
    unittest.main()
