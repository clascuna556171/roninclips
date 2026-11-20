import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'processor')))

from subtitles import generate_ass_subtitles, caption_xy, settings_caption_xy
from re_render_clip import resolve_caption

WORDS = [{'word': 'hey', 'start': 0.0, 'end': 0.3}, {'word': 'look', 'start': 0.3, 'end': 0.7}]


def ass_lines(**kwargs):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'c.ass')
        generate_ass_subtitles(WORDS, p, 1080, 1920, **kwargs)
        with open(p, encoding='utf-8-sig') as f:
            return f.read().splitlines()


class TestCaptionXY(unittest.TestCase):
    def test_pairs_are_clamped_and_bad_values_ignored(self):
        self.assertEqual(caption_xy((0.3, 0.4)), (0.3, 0.4))
        self.assertEqual(caption_xy(('0', '1.2')), (0.05, 0.95))
        for bad in (None, (None, 0.5), ('a', 0.5), (0.5,), (float('nan'), 0.5)):
            self.assertIsNone(caption_xy(bad), bad)

    def test_settings_need_both_coordinates(self):
        self.assertEqual(settings_caption_xy({'caption_x': 0.5, 'caption_y': 0.2}), (0.5, 0.2))
        self.assertIsNone(settings_caption_xy({'caption_x': 0.5, 'caption_y': None}))
        self.assertIsNone(settings_caption_xy({}))


class TestAssPosition(unittest.TestCase):
    def test_dragged_spot_places_every_event_with_centre_anchor(self):
        lines = ass_lines(pos_xy=(0.25, 0.5))
        style = next(l for l in lines if l.startswith('Style: Default'))
        self.assertEqual(style.split(',')[18], '5')  # Alignment: centre
        events = [l for l in lines if l.startswith('Dialogue:')]
        self.assertTrue(events)
        for e in events:
            self.assertIn(',,{\\pos(270,960)}', e)

    def test_presets_unchanged_without_a_spot(self):
        lines = ass_lines(position='top')
        style = next(l for l in lines if l.startswith('Style: Default'))
        self.assertEqual(style.split(',')[18], '8')
        self.assertFalse(any('\\pos(' in l for l in lines))


class TestResolveCaption(unittest.TestCase):
    JOB = {'caption_style': 'neon_cyan', 'caption_position': 'top', 'caption_x': 0.4, 'caption_y': 0.3}

    def test_clip_spot_wins(self):
        self.assertEqual(resolve_caption(self.JOB, {'x': 0.7, 'y': 0.2, 'style': 'fire_gold'}, gaming=True),
                         ('fire_gold', 'bottom', (0.7, 0.2)))

    def test_clip_preset_beats_job_spot(self):
        self.assertEqual(resolve_caption(self.JOB, {'position': 'center'}, gaming=False),
                         ('neon_cyan', 'center', None))

    def test_job_spot_used_when_clip_has_none(self):
        self.assertEqual(resolve_caption(self.JOB, None, gaming=False), ('neon_cyan', 'top', (0.4, 0.3)))

    def test_gaming_layout_keeps_bottom_unless_clip_chose(self):
        self.assertEqual(resolve_caption(self.JOB, {}, gaming=True), ('neon_cyan', 'bottom', None))
        self.assertEqual(resolve_caption(self.JOB, {}, gaming=True, cli_position='center'),
                         ('neon_cyan', 'center', None))

    def test_legacy_job_without_spot(self):
        self.assertEqual(resolve_caption({'caption_position': 'center'}, None, gaming=False),
                         ('yellow_pop', 'center', None))


if __name__ == '__main__':
    unittest.main()
