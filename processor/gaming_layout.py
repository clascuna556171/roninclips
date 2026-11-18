"""
RoninClips — Gaming Facecam Layout
Builds the vertical "facecam on top, whole gameplay below, blurred fill" layout
for stream clips.

Facecam detection: a streamer's webcam overlay shows up as a small face that
stays in the same spot across the whole clip. In-game faces (cutscenes, NPCs)
move around, so they are filtered out by a stability check.

Small facecam faces are too small for BlazeFace on a full 1080p frame, so each
sampled frame is scanned in overlapping square tiles.
"""

import os
import statistics

# Output canvas
OUT_W = 1080
OUT_H = 1920

# Layout constants (pixels on the 1080x1920 canvas)
GAME_BOTTOM = 1408      # Gameplay strip ends here; captions sit below it
GAME_MAX_H = 760        # Cap for taller-than-16:9 sources
CAM_MAX_H = 640         # Cam panel never taller than this (~1/3 of the frame)
CAM_MIN_TOP = 100       # Keep the cam clear of platform top UI
CAM_GAP = 20            # Space between cam panel and gameplay

# Detection tuning
SAMPLE_FRAMES = 12
MAX_FACE_FRACTION = 0.20   # Faces wider than 20% of frame width are not overlays
MIN_PRESENCE = 0.5         # Cam face must appear in at least half the sampled frames
MAX_DRIFT_FRACTION = 0.06  # Cam face centre may drift (std dev) at most 6% of frame width
MIN_CONFIDENCE = 0.7       # Low-confidence hits are mostly patterns in the gameplay


def _even(n):
    n = int(round(n))
    return max(2, n - (n % 2))


# ──────────────────────────────────────────────
# Pure logic (unit tested)
# ──────────────────────────────────────────────

def find_facecam_face(face_samples, frames_sampled, input_w, input_h):
    """
    Pick the face that behaves like a webcam overlay.

    Args:
        face_samples: list of {'frame': int, 'cx', 'cy', 'w', 'h', 'confidence'} in source pixels
        frames_sampled: how many frames were actually read
        input_w, input_h: source frame size

    Returns:
        {'cx', 'cy', 'w', 'h', 'frames'} for the stable face, or None.
    """
    if not face_samples or frames_sampled <= 0:
        return None

    max_face_w = input_w * MAX_FACE_FRACTION
    candidates = [
        f for f in face_samples
        if 0 < f['w'] <= max_face_w and f.get('confidence', 0.5) >= MIN_CONFIDENCE
    ]

    clusters = []
    for face in sorted(candidates, key=lambda f: -f.get('confidence', 0.5)):
        # Streamers lean and move inside their cam, so the cluster is the cam area, not one spot
        radius = max(face['w'] * 1.5, input_w * 0.05)
        home = None
        for cluster in clusters:
            if abs(cluster['cx'] - face['cx']) <= radius and abs(cluster['cy'] - face['cy']) <= radius:
                home = cluster
                break
        if home is None:
            home = {'faces': [], 'cx': face['cx'], 'cy': face['cy']}
            clusters.append(home)
        home['faces'].append(face)
        home['cx'] = statistics.fmean(f['cx'] for f in home['faces'])
        home['cy'] = statistics.fmean(f['cy'] for f in home['faces'])

    min_frames = max(3, int(frames_sampled * MIN_PRESENCE + 0.999))
    max_drift = input_w * MAX_DRIFT_FRACTION

    best = None
    for cluster in clusters:
        frames = {f['frame'] for f in cluster['faces']}
        if len(frames) < min_frames:
            continue
        xs = [f['cx'] for f in cluster['faces']]
        ys = [f['cy'] for f in cluster['faces']]
        if len(xs) > 1 and (statistics.pstdev(xs) > max_drift or statistics.pstdev(ys) > max_drift):
            continue
        score = (len(frames), statistics.fmean(f.get('confidence', 0.5) for f in cluster['faces']))
        if best is None or score > best[0]:
            best = (score, cluster, frames)

    if best is None:
        return None

    _, cluster, frames = best
    faces = cluster['faces']
    return {
        'cx': statistics.median(f['cx'] for f in faces),
        'cy': statistics.median(f['cy'] for f in faces),
        'w': statistics.median(f['w'] for f in faces),
        'h': statistics.median(f['h'] for f in faces),
        # Area the face moved around in, used to size the cam box
        'min_x': min(f['cx'] - f['w'] / 2 for f in faces),
        'max_x': max(f['cx'] + f['w'] / 2 for f in faces),
        'min_y': min(f['cy'] - f['h'] / 2 for f in faces),
        'max_y': max(f['cy'] + f['h'] / 2 for f in faces),
        'frames': len(frames),
    }


def estimate_cam_box(face, input_w, input_h):
    """
    Estimate the webcam overlay rectangle around a detected face.

    Covers everywhere the face moved, plus room for hair and shoulders, with a
    minimum size of a 4:3 box about three face-widths wide.

    Returns [x, y, w, h] in source pixels, clamped to the frame, even-sized.
    """
    fw, fh = face['w'], face['h']
    left = face.get('min_x', face['cx'] - fw / 2) - fw * 0.8
    right = face.get('max_x', face['cx'] + fw / 2) + fw * 0.8
    top = face.get('min_y', face['cy'] - fh / 2) - fh * 0.6
    bottom = face.get('max_y', face['cy'] + fh / 2) + fh * 1.0

    min_w = fw * 3.0
    if right - left < min_w:
        pad = (min_w - (right - left)) / 2
        left, right = left - pad, right + pad
    min_h = (right - left) * 0.75 * 0.75   # never flatter than ~16:9
    if bottom - top < min_h:
        pad = min_h - (bottom - top)
        top, bottom = top - pad * 0.45, bottom + pad * 0.55

    return clamp_box([left, top, right - left, bottom - top], input_w, input_h)


def clamp_box(box, input_w, input_h):
    """Clamp an [x, y, w, h] box inside the frame with even width/height."""
    x, y, w, h = (float(v) for v in box)
    w = _even(min(max(w, 16), input_w))
    h = _even(min(max(h, 16), input_h))
    x = int(max(0, min(x, input_w - w)))
    y = int(max(0, min(y, input_h - h)))
    return [x, y, w, h]


def compute_layout(input_w, input_h, cam_box=None):
    """
    Work out where everything goes on the 1080x1920 canvas.

    Returns dict with game_{x,y,w,h} and, when a cam box is given, cam_{x,y,w,h}.
    """
    game_w = OUT_W
    game_h = _even(OUT_W * input_h / input_w)
    if game_h > GAME_MAX_H:
        game_h = GAME_MAX_H
        game_w = _even(GAME_MAX_H * input_w / input_h)
    game_x = (OUT_W - game_w) // 2

    layout = {'game_x': game_x, 'game_w': game_w, 'game_h': game_h}

    if not cam_box:
        layout['game_y'] = (OUT_H - game_h) // 2
        return layout

    game_y = GAME_BOTTOM - game_h
    layout['game_y'] = game_y

    _, _, cw, ch = cam_box
    aspect = cw / ch
    max_h = min(CAM_MAX_H, game_y - CAM_GAP - CAM_MIN_TOP)
    cam_h = _even(max_h)
    cam_w = _even(cam_h * aspect)
    if cam_w > OUT_W:
        cam_w = OUT_W
        cam_h = _even(OUT_W / aspect)

    layout.update({
        'cam_x': (OUT_W - cam_w) // 2,
        'cam_y': game_y - CAM_GAP - cam_h,
        'cam_w': cam_w,
        'cam_h': cam_h,
    })
    return layout


def build_gaming_filter(input_w, input_h, cam_box=None):
    """
    FFmpeg filter_complex for the gaming layout. Output label is [outv] so the
    caller can append subtitles the same way it does for split-screen.
    """
    L = compute_layout(input_w, input_h, cam_box)

    background = (
        "scale=270:480:force_original_aspect_ratio=increase,crop=270:480,"
        "boxblur=8:2,scale=1080:1920,eq=brightness=-0.18,setsar=1[gbg]"
    )
    game = f"scale={L['game_w']}:{L['game_h']},setsar=1[ggame]"

    if not cam_box:
        return ";".join([
            "[0:v]split=2[gsrc_bg][gsrc_game]",
            f"[gsrc_bg]{background}",
            f"[gsrc_game]{game}",
            f"[gbg][ggame]overlay={L['game_x']}:{L['game_y']}[outv]",
        ])

    cx, cy, cw, ch = cam_box
    return ";".join([
        "[0:v]split=3[gsrc_bg][gsrc_game][gsrc_cam]",
        f"[gsrc_bg]{background}",
        f"[gsrc_game]{game}",
        f"[gsrc_cam]crop={cw}:{ch}:{cx}:{cy},scale={L['cam_w']}:{L['cam_h']},setsar=1[gcam]",
        f"[gbg][ggame]overlay={L['game_x']}:{L['game_y']}[gmid]",
        f"[gmid][gcam]overlay={L['cam_x']}:{L['cam_y']}[outv]",
    ])


def _snap_edge(band, axis, origin, expected, nearest_high):
    """
    Find a border line in a 2-D slice of an edge map.

    axis=0: candidate lines are columns (vertical border); axis=1: rows.
    A real webcam border runs along the whole side, so each candidate is scored
    by coverage: the share of pixels along it that are strong edges. Partial
    lines (scoreboards, HUD text) score low. Going outward from the face, the
    first full line is the cam border, so among qualifying lines the one nearest
    the face wins (nearest_high=True: the face is on the high-index side).
    Returns the snapped position, or `expected` when no line covers 60% of the side.
    """
    import numpy as np
    if band.size == 0 or min(band.shape) < 3:
        return expected
    threshold = max(20.0, 4.0 * float(np.median(band)))
    coverage = (band > threshold).mean(axis=axis)
    lines = np.flatnonzero(coverage >= 0.6)
    if lines.size == 0:
        return expected
    return origin + int(lines.max() if nearest_high else lines.min())


def refine_cam_box(box, edges_x, edges_y, scale, input_w, input_h):
    """
    Snap a rough cam box to the webcam overlay's border.

    edges_x / edges_y are time-averaged |d/dx| and |d/dy| edge maps of the
    sampled frames at 1/scale resolution. A webcam border stays still while
    gameplay moves, so after averaging it is one of the strongest straight edges
    near the face. Each side moves only when there is a clear peak.
    """
    H, W = edges_x.shape
    x, y, w, h = [v / scale for v in box]

    for _ in range(2):
        r0, r1 = int(max(0, y + h * 0.15)), int(min(H, y + h * 0.85))
        if r1 - r0 >= 4:
            lo, hi = int(max(0, x - w * 0.4)), int(min(W, x + w * 0.3))
            left = _snap_edge(edges_x[r0:r1, lo:hi], 0, lo, x, True)
            lo, hi = int(max(0, x + w * 0.7)), int(min(W, x + w * 1.4))
            right = _snap_edge(edges_x[r0:r1, lo:hi], 0, lo, x + w, False)
            if right - left > w * 0.4:
                x, w = left, right - left

        c0, c1 = int(max(0, x + w * 0.15)), int(min(W, x + w * 0.85))
        if c1 - c0 >= 4:
            lo, hi = int(max(0, y - h * 0.4)), int(min(H, y + h * 0.3))
            top = _snap_edge(edges_y[lo:hi, c0:c1], 1, lo, y, True)
            lo, hi = int(max(0, y + h * 0.7)), int(min(H, y + h * 1.4))
            bottom = _snap_edge(edges_y[lo:hi, c0:c1], 1, lo, y + h, False)
            if bottom - top > h * 0.4:
                y, h = top, bottom - top

    # Step just inside the border line so it is not part of the panel
    inset = 2
    return clamp_box(
        [(x + inset) * scale, (y + inset) * scale, (w - inset * 2) * scale, (h - inset * 2) * scale],
        input_w, input_h,
    )


# ──────────────────────────────────────────────
# Detection (needs OpenCV + MediaPipe)
# ──────────────────────────────────────────────

def _tile_origins(length, tile, stride):
    if length <= tile:
        return [0]
    origins = list(range(0, length - tile + 1, stride))
    if origins[-1] != length - tile:
        origins.append(length - tile)
    return origins


def sample_faces(video_path, duration, sample_frames=SAMPLE_FRAMES):
    """
    Detect faces in evenly spaced frames, scanning each frame in overlapping tiles.

    Returns (face_samples, frames_read, (width, height), edges) where edges is
    (edges_x, edges_y, scale): time-averaged edge maps at 1/scale resolution.
    """
    import cv2
    import numpy as np
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    from face_tracker import ensure_model_downloaded

    model_path = ensure_model_downloaded()
    cap = cv2.VideoCapture(video_path)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if model_path is None or not cap.isOpened() or width <= 0 or height <= 0:
        cap.release()
        return [], 0, (width, height), None

    tile = max(128, int(height / 3))
    stride = max(64, int(tile * 0.75))
    xs = _tile_origins(width, tile, stride)
    ys = _tile_origins(height, tile, stride)

    options = mp_vision.FaceDetectorOptions(
        base_options=mp_python.BaseOptions(model_asset_path=model_path),
        running_mode=mp_vision.RunningMode.IMAGE,
        min_detection_confidence=0.5,
    )

    samples = []
    frames_read = 0
    edge_scale = 2
    edges_x = edges_y = None
    duration = max(0.5, float(duration))
    with mp_vision.FaceDetector.create_from_options(options) as detector:
        for i in range(sample_frames):
            t = duration * (i + 0.5) / sample_frames
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            if not ok:
                continue
            frames_read += 1
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, (width // edge_scale, height // edge_scale)).astype(np.float32)
            gx = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
            gy = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
            edges_x = gx if edges_x is None else edges_x + gx
            edges_y = gy if edges_y is None else edges_y + gy
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            for oy in ys:
                for ox in xs:
                    crop = rgb[oy:oy + tile, ox:ox + tile].copy()
                    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=crop)
                    result = detector.detect(image)
                    for det in result.detections or []:
                        bb = det.bounding_box
                        samples.append({
                            'frame': i,
                            'cx': ox + bb.origin_x + bb.width / 2,
                            'cy': oy + bb.origin_y + bb.height / 2,
                            'w': float(bb.width),
                            'h': float(bb.height),
                            'confidence': det.categories[0].score if det.categories else 0.5,
                        })
    cap.release()
    edges = None
    if frames_read:
        edges = (edges_x / frames_read, edges_y / frames_read, edge_scale)
    return samples, frames_read, (width, height), edges


def get_gaming_layout(video_path, duration):
    """
    High-level API used by engine.py.

    Returns dict:
        {'filter_complex', 'cam_box' ([x,y,w,h] or None), 'input_w', 'input_h', 'auto_detected'}
    or None when the source is not landscape (layout does not apply).
    """
    from face_tracker import get_video_info

    input_w, input_h, _ = get_video_info(video_path)
    if input_w <= input_h:
        print(f"  [gaming_layout] Source is {input_w}x{input_h} (not landscape), skipping gaming layout")
        return None

    cam_box = None
    try:
        samples, frames_read, _, edges = sample_faces(video_path, duration)
        face = find_facecam_face(samples, frames_read, input_w, input_h)
        if face:
            cam_box = estimate_cam_box(face, input_w, input_h)
            if edges is not None:
                rough = cam_box
                cam_box = refine_cam_box(rough, edges[0], edges[1], edges[2], input_w, input_h)
                print(f"  [gaming_layout] Cam box snapped to border: {rough} -> {cam_box}")
            print(f"  [gaming_layout] Facecam found in {face['frames']}/{frames_read} frames, box={cam_box}")
        else:
            print(f"  [gaming_layout] No stable facecam found ({len(samples)} face hits in {frames_read} frames), using gameplay only")
    except Exception as det_err:
        print(f"  [gaming_layout] Facecam detection failed ({det_err}), using gameplay only")

    return {
        'filter_complex': build_gaming_filter(input_w, input_h, cam_box),
        'cam_box': cam_box,
        'input_w': input_w,
        'input_h': input_h,
        'auto_detected': cam_box is not None,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python gaming_layout.py <video_path> [duration_seconds]")
        sys.exit(1)
    sys.path.insert(0, os.path.dirname(__file__))
    info = get_gaming_layout(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 20.0)
    print(info)
