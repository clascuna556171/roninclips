import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'processor')))

from gaming_layout import (
    GAME_BOTTOM, build_gaming_filter, clamp_box, compute_layout,
    estimate_cam_box, find_facecam_face,
)

W, H = 1920, 1080


def face(frame, cx, cy, size=90, conf=0.9):
    return {'frame': frame, 'cx': cx, 'cy': cy, 'w': size, 'h': size, 'confidence': conf}


class TestFacecamDetection(unittest.TestCase):
    def test_picks_stable_corner_face_over_moving_game_faces(self):
        samples = []
        for i in range(12):
            samples.append(face(i, 1700 + (i % 2) * 4, 180 + (i % 3) * 3))   # webcam, jitters a few px
            samples.append(face(i, 200 + i * 120, 600, size=120, conf=0.95))  # cutscene face sweeping across
        result = find_facecam_face(samples, 12, W, H)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result['cx'], 1702, delta=5)
        self.assertAlmostEqual(result['cy'], 183, delta=5)
        self.assertEqual(result['frames'], 12)

    def test_returns_none_when_face_only_appears_briefly(self):
        samples = [face(i, 1700, 180) for i in range(3)]
        self.assertIsNone(find_facecam_face(samples, 12, W, H))

    def test_ignores_fullscreen_camera_faces(self):
        samples = [face(i, 960, 500, size=500) for i in range(12)]
        self.assertIsNone(find_facecam_face(samples, 12, W, H))

    def test_handles_no_samples(self):
        self.assertIsNone(find_facecam_face([], 0, W, H))


class TestCamBoxAndLayout(unittest.TestCase):
    def test_cam_box_is_clamped_inside_frame_and_even(self):
        x, y, w, h = estimate_cam_box({'cx': 1880, 'cy': 40, 'w': 120, 'h': 120}, W, H)
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(x + w, W)
        self.assertLessEqual(y + h, H)
        self.assertEqual(w % 2, 0)
        self.assertEqual(h % 2, 0)

    def test_clamp_box_shrinks_oversized_box(self):
        self.assertEqual(clamp_box([-50, -50, 5000, 5000], W, H), [0, 0, 1920, 1080])

    def test_layout_with_cam_stacks_cam_above_full_width_gameplay(self):
        L = compute_layout(W, H, [1500, 40, 360, 270])
        self.assertEqual((L['game_w'], L['game_h']), (1080, 608))
        self.assertEqual(L['game_y'] + L['game_h'], GAME_BOTTOM)
        self.assertLessEqual(L['cam_y'] + L['cam_h'], L['game_y'])
        self.assertGreaterEqual(L['cam_y'], 100)
        self.assertLessEqual(L['cam_w'], 1080)
        self.assertAlmostEqual(L['cam_w'] / L['cam_h'], 360 / 270, delta=0.02)

    def test_layout_without_cam_centres_gameplay(self):
        L = compute_layout(W, H, None)
        self.assertNotIn('cam_w', L)
        self.assertEqual(L['game_y'], (1920 - 608) // 2)

    def test_tall_source_gameplay_is_capped(self):
        L = compute_layout(1440, 1080, [0, 0, 400, 300])
        self.assertLessEqual(L['game_h'], 760)
        self.assertEqual(L['game_x'], (1080 - L['game_w']) // 2)

    def test_filter_with_cam_crops_cam_and_ends_in_outv(self):
        fc = build_gaming_filter(W, H, [1500, 40, 360, 270])
        self.assertIn('split=3', fc)
        self.assertIn('crop=360:270:1500:40', fc)
        self.assertTrue(fc.endswith('[outv]'))
        self.assertEqual(fc.count('[outv]'), 1)

    def test_filter_without_cam_has_no_cam_crop(self):
        fc = build_gaming_filter(W, H, None)
        self.assertIn('split=2', fc)
        self.assertNotIn('[gcam]', fc)
        self.assertTrue(fc.endswith('[outv]'))


class TestBorderSnap(unittest.TestCase):
    def _edge_maps(self):
        import numpy as np
        # Half-resolution maps (scale=2) of a 1920x1080 frame
        ex = np.zeros((540, 960), dtype=np.float32)
        ey = np.zeros((540, 960), dtype=np.float32)
        # Cam border: x 740..940, y 15..165 (full res 1480..1880, 30..330)
        ex[15:166, 740] = ex[15:166, 940] = 100
        ey[15, 740:941] = ey[165, 740:941] = 100
        # Full-height static line further out (e.g. a HUD divider) must not win
        ex[:, 640] = 100
        # Partial line inside the cam (scoreboard text) must not win
        ey[60, 800:840] = 100
        return ex, ey

    def test_snaps_rough_box_to_cam_border(self):
        from gaming_layout import refine_cam_box
        ex, ey = self._edge_maps()
        x, y, w, h = refine_cam_box([1400, 90, 460, 330], ex, ey, 2, W, H)
        self.assertAlmostEqual(x, 1484, delta=8)
        self.assertAlmostEqual(y, 34, delta=8)
        self.assertAlmostEqual(x + w, 1876, delta=8)
        self.assertAlmostEqual(y + h, 326, delta=8)

    def test_keeps_rough_box_when_no_border(self):
        import numpy as np
        from gaming_layout import refine_cam_box
        flat = np.zeros((540, 960), dtype=np.float32)
        box = refine_cam_box([1400, 90, 460, 330], flat, flat, 2, W, H)
        self.assertAlmostEqual(box[0], 1404, delta=4)
        self.assertAlmostEqual(box[2], 452, delta=4)


if __name__ == '__main__':
    unittest.main()
