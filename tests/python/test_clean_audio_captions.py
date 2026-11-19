import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'processor')))

from subtitles import generate_ass_subtitles, mask_word
from audio_mixer import loudnorm_second_pass_filter, parse_loudnorm_json


class TestCaptionMasking(unittest.TestCase):
    def test_slurs_are_always_masked(self):
        self.assertEqual(mask_word('nigga', mask_swears=False), 'n****')
        self.assertEqual(mask_word('Faggot,', mask_swears=False), 'F*****,')
        self.assertEqual(mask_word('retarded', mask_swears=False), 'r*******')

    def test_swears_masked_only_when_asked(self):
        self.assertEqual(mask_word('fucking', mask_swears=False), 'fucking')
        self.assertEqual(mask_word('fucking', mask_swears=True), 'f******')
        self.assertEqual(mask_word('motherfucker!', mask_swears=True), 'm***********!')
        self.assertEqual(mask_word('SHIT', mask_swears=True), 'S***')
        self.assertEqual(mask_word('bullshit', mask_swears=True), 'b*******')

    def test_clean_words_that_look_alike_are_left_alone(self):
        for w in ('spicy', 'spice', 'Dickens', 'retardant', 'scunthorpe', 'class', 'assess',
                  'Shiitake', 'cocktail', 'grass', 'chinks?'):
            # 'chinks' is ambiguous (chinks in the armor) and stays unmasked
            self.assertEqual(mask_word(w, mask_swears=True), w, w)

    def test_ass_file_uses_masked_text(self):
        words = [{'word': 'what', 'start': 0.0, 'end': 0.4}, {'word': 'the', 'start': 0.4, 'end': 0.6},
                 {'word': 'fuck', 'start': 0.6, 'end': 1.0}]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'c.ass')
            def read():
                with open(p, encoding='utf-8-sig') as f:
                    return f.read()
            generate_ass_subtitles(words, p, mask_swears=True)
            self.assertIn('F***', read())
            self.assertNotIn('FUCK', read())
            generate_ass_subtitles(words, p)  # default leaves swears
            self.assertIn('FUCK', read())


LOUDNORM_STDERR = """[Parsed_loudnorm_0 @ 000001]
{
	"input_i" : "-23.54",
	"input_tp" : "-4.12",
	"input_lra" : "6.30",
	"input_thresh" : "-33.91",
	"output_i" : "-14.20",
	"output_tp" : "-1.50",
	"output_lra" : "5.10",
	"output_thresh" : "-24.50",
	"normalization_type" : "dynamic",
	"target_offset" : "0.20"
}
"""


class TestLoudness(unittest.TestCase):
    def test_parse_measurement_from_ffmpeg_stderr(self):
        m = parse_loudnorm_json('frame=  100 fps=0.0\n' + LOUDNORM_STDERR)
        self.assertEqual(m['input_i'], '-23.54')
        self.assertEqual(m['target_offset'], '0.20')
        self.assertIsNone(parse_loudnorm_json('no json here'))
        self.assertIsNone(parse_loudnorm_json('{"input_i": "-20"}'))  # incomplete

    def test_second_pass_filter_uses_measured_values(self):
        f = loudnorm_second_pass_filter(parse_loudnorm_json(LOUDNORM_STDERR))
        self.assertEqual(
            f, 'loudnorm=I=-14:TP=-1.5:LRA=11:measured_I=-23.54:measured_TP=-4.12:'
               'measured_LRA=6.30:measured_thresh=-33.91:offset=0.20:linear=true')

    def test_silent_or_broken_audio_is_skipped(self):
        m = parse_loudnorm_json(LOUDNORM_STDERR)
        self.assertIsNone(loudnorm_second_pass_filter(dict(m, input_i='-inf')))
        self.assertIsNone(loudnorm_second_pass_filter(dict(m, input_i='-75.0')))
        self.assertIsNone(loudnorm_second_pass_filter(dict(m, input_i='abc')))
        self.assertIsNone(loudnorm_second_pass_filter(None))


if __name__ == '__main__':
    unittest.main()
