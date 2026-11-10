import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'processor')))

from subtitles import PALETTES, ffmpeg_escape_path, format_ass_time, generate_ass_subtitles
from effects import generate_kenburns_filter, generate_punchin_filter
from engine import parse_groq_json_response, parse_time_to_seconds, split_transcript_into_chunks


class TestProcessorPipeline(unittest.TestCase):
    def test_format_ass_time(self):
        self.assertEqual(format_ass_time(0), "0:00:00.00")
        self.assertEqual(format_ass_time(65.5), "0:01:05.50")
        self.assertEqual(format_ass_time(-3), "0:00:00.00")

    def test_ffmpeg_escape_path(self):
        escaped = ffmpeg_escape_path(r"D:\Tech\Projects\clip_1.ass")
        self.assertEqual(escaped, "D\\:/Tech/Projects/clip_1.ass")

    def test_generate_ass_subtitles_sanitizes_tags_and_commas(self):
        words = [
            {"word": "Hello {world}\\test", "start": 0.0, "end": 0.8},
            {"word": "second", "start": 0.8, "end": 1.5},
        ]
        with tempfile.NamedTemporaryFile(suffix=".ass", delete=False, mode="r", encoding="utf-8") as tmp:
            ass_path = tmp.name

        try:
            count = generate_ass_subtitles(
                words,
                ass_path,
                output_w=1080,
                output_h=1920,
                style_preset="hormozi_box",
                font_family="Impact,Injected",
                position="bottom",
                layout_mode="two_line",
            )
            self.assertEqual(count, 2)
            with open(ass_path, "r", encoding="utf-8-sig") as f:
                content = f.read()
            self.assertIn("Style: Default,ImpactInjected,", content)
            self.assertIn("HELLO WORLDTEST", content)
            self.assertNotIn("{WORLD}", content)
        finally:
            if os.path.exists(ass_path):
                os.remove(ass_path)

    def test_generate_punchin_filter_sorts_by_intensity(self):
        spikes = [
            {"start": float(i), "end": float(i) + 0.5, "intensity": float(i) / 10.0}
            for i in range(1, 16)
        ]
        expr = generate_punchin_filter(spikes, total_duration=25.0, input_w=1080, input_h=1920, zoom_factor=1.15)
        self.assertIsNotNone(expr)
        # Highest intensity spikes (e.g. start=15.0, end=15.5) must be kept in top 12, lowest (start=1.0, 2.0, 3.0) dropped
        self.assertIn("between(t,15.000,15.500)", expr)
        self.assertNotIn("between(t,1.000,1.500)", expr)

    def test_generate_kenburns_filter(self):
        expr = generate_kenburns_filter(15.0, 1080, 1920, start_zoom=1.0, end_zoom=1.08)
        self.assertIsNotNone(expr)
        self.assertIn("1.0000+0.0800*t/15.000", expr)
        self.assertIn("crop=1080:1920", expr)

    def test_parse_groq_json_response(self):
        raw_wrapped = '```json\n[{"start": "00:00:10", "end": "00:00:45", "virality_score": 92}]\n```'
        parsed = parse_groq_json_response(raw_wrapped)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["virality_score"], 92)

        raw_chatty = 'Here are the best clips:\n[ {"start": "00:00:05", "end": "00:00:35"} ]\nEnjoy!'
        parsed_list = parse_groq_json_response(raw_chatty)
        self.assertEqual(len(parsed_list), 1)
        self.assertEqual(parsed_list[0]["start"], "00:00:05")

    def test_split_transcript_into_chunks(self):
        short_text = "[00:00:00 - 00:00:10] Short transcript line"
        self.assertEqual(split_transcript_into_chunks(short_text, max_chars=100), [short_text])

        lines = [f"[00:00:{i:02d} - 00:00:{i+1:02d}] Segment number {i} with some words" for i in range(20)]
        full_text = "\n".join(lines)
        chunks = split_transcript_into_chunks(full_text, max_chars=250)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 250)

    def test_parse_time_to_seconds(self):
        self.assertEqual(parse_time_to_seconds(42.5), 42.5)
        self.assertEqual(parse_time_to_seconds("01:30"), 90.0)
        self.assertEqual(parse_time_to_seconds("01:02:03"), 3723.0)
        self.assertEqual(parse_time_to_seconds("15.5s"), 15.5)

    def test_re_render_clip_run_ffmpeg_defaults(self):
        from re_render_clip import run_ffmpeg
        res = run_ffmpeg([sys.executable, '-c', 'print("roninclips_test")'])
        self.assertEqual(res.returncode, 0)
        self.assertIn('roninclips_test', res.stdout.strip())


if __name__ == "__main__":
    unittest.main()
