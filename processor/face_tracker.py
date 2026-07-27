"""
RoninClips — Face Tracker & Smart Crop Module
Uses MediaPipe Face Detection (Tasks API) to track subjects and generate smooth
9:16 crop trajectories for vertical video output.

Compatible with MediaPipe >= 0.10.x (new Tasks API).
"""

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
import subprocess
import json
import os
import urllib.request


# ──────────────────────────────────────────────
# Model Management
# ──────────────────────────────────────────────

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"
MODEL_DIR = os.path.join(os.path.dirname(__file__), 'models')
MODEL_PATH = os.path.join(MODEL_DIR, 'blaze_face_short_range.tflite')


def ensure_model_downloaded():
    """Download the face detection model if not already present."""
    if os.path.exists(MODEL_PATH):
        return MODEL_PATH

    os.makedirs(MODEL_DIR, exist_ok=True)
    print(f"  [face_tracker] Downloading face detection model...")
    try:
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        print(f"  [face_tracker] Model downloaded: {os.path.getsize(MODEL_PATH) / 1024:.0f} KB")
    except Exception as e:
        print(f"  [face_tracker] Failed to download model: {e}")
        return None

    return MODEL_PATH


# ──────────────────────────────────────────────
# Face Detection
# ──────────────────────────────────────────────

def get_video_info(video_path):
    """Get video dimensions and FPS using FFprobe."""
    cmd = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_streams', '-select_streams', 'v:0', video_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace', timeout=30)
        info = json.loads(result.stdout)
        stream = info['streams'][0]
        width = int(stream['width'])
        height = int(stream['height'])
        # Parse FPS from r_frame_rate (e.g., "30/1" or "30000/1001")
        fps_parts = stream.get('r_frame_rate', '30/1').split('/')
        fps = float(fps_parts[0]) / float(fps_parts[1]) if len(fps_parts) == 2 else 30.0
        return width, height, fps
    except Exception as e:
        print(f"  [face_tracker] FFprobe failed: {e}, using defaults")
        return 1920, 1080, 30.0


def analyze_video_faces(video_path, start_time, duration, sample_every_n=5):
    """
    Detect faces in the video clip by sampling every N-th frame.
    Uses MediaPipe Tasks API (0.10.x+) with VIDEO running mode.

    Args:
        video_path: Path to the source video file
        start_time: Start time in seconds
        duration: Duration of clip in seconds
        sample_every_n: Sample every N-th frame (lower = more accurate but slower)

    Returns:
        List of dicts: [{'frame': int, 'time': float, 'faces': [{'cx': float, 'cy': float, 'w': float, 'h': float}]}]
        Also returns (input_width, input_height, fps)
    """
    width, height, fps = get_video_info(video_path)
    total_frames = int(duration * fps)

    print(f"  [face_tracker] Video: {width}x{height} @ {fps:.1f}fps, analyzing {total_frames} frames (sampling every {sample_every_n})")

    # Ensure the face detection model is available
    model_path = ensure_model_downloaded()
    if model_path is None:
        print(f"  [face_tracker] No model available, returning empty detections")
        return [], (width, height, fps)

    # Initialize MediaPipe Face Detection with Tasks API
    base_options = mp_python.BaseOptions(model_asset_path=model_path)
    options = mp_vision.FaceDetectorOptions(
        base_options=base_options,
        running_mode=mp_vision.RunningMode.VIDEO,
        min_detection_confidence=0.5
    )

    # Open video at the correct start position
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"  [face_tracker] ERROR: Cannot open video: {video_path}")
        return [], (width, height, fps)

    # Seek to start_time
    start_frame = int(start_time * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    detections = []
    frame_idx = 0

    with mp_vision.FaceDetector.create_from_options(options) as detector:
        while frame_idx < total_frames:
            if frame_idx % sample_every_n == 0:
                # Only decode frames we actually need to analyze
                ret, frame = cap.read()
                if not ret:
                    break

                # Convert BGR to RGB for MediaPipe
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

                # Timestamp must be monotonically increasing (in milliseconds)
                timestamp_ms = int((start_time + frame_idx / fps) * 1000)
                results = detector.detect_for_video(mp_image, timestamp_ms)

                faces = []
                if results.detections:
                    for detection in results.detections:
                        bbox = detection.bounding_box
                        # bbox has: origin_x, origin_y, width, height (in pixels)
                        face_cx = bbox.origin_x + bbox.width / 2
                        face_cy = bbox.origin_y + bbox.height / 2
                        face_w = bbox.width
                        face_h = bbox.height
                        # Get confidence score
                        confidence = detection.categories[0].score if detection.categories else 0.5
                        faces.append({
                            'cx': face_cx,
                            'cy': face_cy,
                            'w': face_w,
                            'h': face_h,
                            'confidence': confidence
                        })
                    # Sort by confidence (highest first)
                    faces.sort(key=lambda f: f['confidence'], reverse=True)

                detections.append({
                    'frame': frame_idx,
                    'time': frame_idx / fps,
                    'faces': faces
                })

                if len(detections) % 50 == 0:
                    print(f"  [face_tracker]   ...processed {len(detections)} sample frames ({frame_idx}/{total_frames} total)")
            else:
                # Skip this frame — grab() advances without decoding (much faster)
                if not cap.grab():
                    break

            frame_idx += 1

    cap.release()

    faces_found = sum(1 for d in detections if len(d['faces']) > 0)
    print(f"  [face_tracker] Analyzed {len(detections)} sample frames, faces detected in {faces_found}")

    return detections, (width, height, fps)


# ──────────────────────────────────────────────
# Crop Trajectory Calculation
# ──────────────────────────────────────────────

def calculate_crop_trajectory(detections, input_width, input_height, fps,
                               total_duration, sample_every_n=5, output_ratio=(9, 16)):
    """
    Calculate the crop window position for every frame, centering on detected faces.

    The crop window is sized to maximize quality:
    - Uses full input height and calculates width from the aspect ratio
    - If the input is wider than needed, we pan horizontally
    - If the input is taller than needed, we pan vertically

    Args:
        detections: Output from analyze_video_faces()
        input_width, input_height: Source video dimensions
        fps: Source video FPS
        total_duration: Total clip duration in seconds
        sample_every_n: Must match what was used in analyze_video_faces
        output_ratio: Target aspect ratio as (w, h) tuple

    Returns:
        List of (frame_idx, crop_x, crop_y, crop_w, crop_h) for every frame
    """
    total_frames = int(total_duration * fps)
    ratio_w, ratio_h = output_ratio

    # Calculate crop dimensions to maximize resolution
    # Try fitting by height first (use full height, calculate width)
    crop_h = input_height
    crop_w = int(input_height * ratio_w / ratio_h)

    if crop_w > input_width:
        # Input is too narrow — fit by width instead
        crop_w = input_width
        crop_h = int(input_width * ratio_h / ratio_w)

    # Ensure even dimensions (required by many codecs)
    crop_w = crop_w - (crop_w % 2)
    crop_h = crop_h - (crop_h % 2)

    print(f"  [face_tracker] Crop window: {crop_w}x{crop_h} from {input_width}x{input_height}")

    # Build raw crop center positions from face detections
    # For frames without detections, we'll interpolate later
    raw_positions = {}  # frame_idx -> (center_x, center_y)

    for det in detections:
        frame = det['frame']
        if det['faces']:
            # Strategy: If multiple faces, find the bounding box that contains
            # the most prominent faces (up to 2) and center on that
            if len(det['faces']) == 1:
                cx = det['faces'][0]['cx']
                cy = det['faces'][0]['cy']
            else:
                # Multi-face: center between the top 2 most confident faces
                top_faces = det['faces'][:2]
                cx = sum(f['cx'] for f in top_faces) / len(top_faces)
                cy = sum(f['cy'] for f in top_faces) / len(top_faces)
            raw_positions[frame] = (cx, cy)

    if not raw_positions:
        # No faces detected at all — center crop on the frame
        print(f"  [face_tracker] No faces detected, using center crop")
        center_x = input_width / 2
        center_y = input_height / 2
        return [(i, clamp_crop_x(center_x, crop_w, input_width),
                 clamp_crop_y(center_y, crop_h, input_height),
                 crop_w, crop_h) for i in range(total_frames)]

    # Interpolate positions for all frames
    sampled_frames = sorted(raw_positions.keys())
    all_cx = np.zeros(total_frames)
    all_cy = np.zeros(total_frames)

    # Create interpolation arrays
    sample_indices = np.array(sampled_frames)
    sample_cx = np.array([raw_positions[f][0] for f in sampled_frames])
    sample_cy = np.array([raw_positions[f][1] for f in sampled_frames])

    # Linear interpolation for all frames
    frame_indices = np.arange(total_frames)
    all_cx = np.interp(frame_indices, sample_indices, sample_cx)
    all_cy = np.interp(frame_indices, sample_indices, sample_cy)

    # Apply exponential smoothing
    all_cx = exponential_smooth(all_cx, alpha=0.08)
    all_cy = exponential_smooth(all_cy, alpha=0.08)

    # Build final trajectory with clamping
    trajectory = []
    for i in range(total_frames):
        cx = all_cx[i]
        cy = all_cy[i]
        crop_x = clamp_crop_x(cx, crop_w, input_width)
        crop_y = clamp_crop_y(cy, crop_h, input_height)
        trajectory.append((i, int(crop_x), int(crop_y), crop_w, crop_h))

    return trajectory


def clamp_crop_x(center_x, crop_w, input_width):
    """Clamp crop X so it doesn't go out of bounds."""
    x = center_x - crop_w / 2
    x = max(0, min(x, input_width - crop_w))
    return int(x)


def clamp_crop_y(center_y, crop_h, input_height):
    """Clamp crop Y so it doesn't go out of bounds."""
    y = center_y - crop_h / 2
    y = max(0, min(y, input_height - crop_h))
    return int(y)


def exponential_smooth(data, alpha=0.08):
    """
    Apply exponential smoothing to an array of values.
    Lower alpha = smoother (more lag), higher alpha = more responsive (more jitter).
    """
    smoothed = np.zeros_like(data)
    smoothed[0] = data[0]
    for i in range(1, len(data)):
        smoothed[i] = alpha * data[i] + (1 - alpha) * smoothed[i - 1]
    return smoothed


# ──────────────────────────────────────────────
# FFmpeg Filter Generation
# ──────────────────────────────────────────────

def generate_crop_filter_simple(trajectory):
    """
    Generate a simple FFmpeg crop filter using the median crop position.
    This is a fast fallback — single static crop, no panning.
    """
    if not trajectory:
        return None

    xs = [t[1] for t in trajectory]
    ys = [t[2] for t in trajectory]
    crop_w = trajectory[0][3]
    crop_h = trajectory[0][4]

    median_x = int(np.median(xs))
    median_y = int(np.median(ys))

    return f"crop={crop_w}:{crop_h}:{median_x}:{median_y}"


def generate_crop_filter_dynamic(trajectory, fps):
    """
    Generate a dynamic FFmpeg crop filter that pans frame-by-frame
    using the sendcmd / crop approach via a pre-built expression.

    Uses FFmpeg's expression-based crop with timeline keyframes.
    We split the trajectory into segments of ~1 second and interpolate
    with FFmpeg's built-in linear interpolation via 'if(between(t,...))'.

    Returns the crop filter string.
    """
    if not trajectory:
        return None

    crop_w = trajectory[0][3]
    crop_h = trajectory[0][4]

    # Downsample trajectory to ~2 keypoints per second for manageable expression size
    keypoints_per_sec = 2
    frame_step = max(1, int(fps / keypoints_per_sec))

    keyframes = []
    for i in range(0, len(trajectory), frame_step):
        frame_idx, cx, cy, cw, ch = trajectory[i]
        t = frame_idx / fps
        keyframes.append((t, cx, cy))

    # Add the last frame if not already included
    last = trajectory[-1]
    last_t = last[0] / fps
    if not keyframes or abs(keyframes[-1][0] - last_t) > 0.01:
        keyframes.append((last_t, last[1], last[2]))

    if len(keyframes) == 1:
        # Only one keyframe — static crop
        return f"crop={crop_w}:{crop_h}:{keyframes[0][1]}:{keyframes[0][2]}"

    # Build FFmpeg expression for X position using linear interpolation between keyframes
    x_expr = build_interp_expression(keyframes, component='x')
    y_expr = build_interp_expression(keyframes, component='y')

    return f"crop={crop_w}:{crop_h}:{x_expr}:{y_expr}"


def build_interp_expression(keyframes, component='x'):
    """
    Build an FFmpeg expression that linearly interpolates between keyframes.
    Uses nested if(lt(t, ...)) expressions.

    component: 'x' uses index 1, 'y' uses index 2
    """
    idx = 1 if component == 'x' else 2

    if len(keyframes) <= 1:
        return str(keyframes[0][idx])

    # Build from last segment backwards (nested if/else)
    # Last value is the fallback
    expr = str(int(keyframes[-1][idx]))

    for i in range(len(keyframes) - 2, -1, -1):
        t0 = keyframes[i][0]
        v0 = keyframes[i][idx]
        t1 = keyframes[i + 1][0]
        v1 = keyframes[i + 1][idx]

        dt = t1 - t0
        if dt < 0.001:
            dt = 0.001

        # Linear interpolation: v0 + (v1 - v0) * (t - t0) / (t1 - t0)
        # Simplified for FFmpeg expression syntax
        lerp = f"{int(v0)}+({int(v1)}-{int(v0)})*(t-{t0:.3f})/{dt:.3f}"
        expr = f"if(lt(t\\,{t1:.3f})\\,{lerp}\\,{expr})"

    return expr


# ──────────────────────────────────────────────
# Public API: One-Call Smart Crop
# ──────────────────────────────────────────────

def get_smart_crop_filter(video_path, start_time, duration, sample_every_n=5,
                           output_ratio=(9, 16), dynamic=False):
    """
    High-level API: Analyze faces and return ready-to-use FFmpeg crop filter.

    Args:
        video_path: Path to the source video
        start_time: Clip start in seconds
        duration: Clip duration in seconds
        sample_every_n: Frame sampling rate
        output_ratio: Target aspect ratio
        dynamic: If True, returns a panning crop (complex FFmpeg expression).
                 If False (default), returns a static median-position crop (simple, reliable).

    Returns:
        (crop_filter_string, crop_w, crop_h) or (None, input_w, input_h) if no crop needed
    """
    detections, (w, h, fps) = analyze_video_faces(video_path, start_time, duration, sample_every_n)
    trajectory = calculate_crop_trajectory(detections, w, h, fps, duration, sample_every_n, output_ratio)

    # Use simple (static median) crop by default — it's far more reliable across
    # OS/FFmpeg versions and avoids deeply nested expression parsing issues on Windows.
    # Dynamic panning can be enabled explicitly once tested on the user's setup.
    if dynamic:
        crop_filter = generate_crop_filter_dynamic(trajectory, fps)
    else:
        crop_filter = generate_crop_filter_simple(trajectory)

    crop_w = trajectory[0][3] if trajectory else w
    crop_h = trajectory[0][4] if trajectory else h

    return crop_filter, crop_w, crop_h


# ──────────────────────────────────────────────
# CLI Test Mode
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python face_tracker.py <video_path> [start_seconds] [duration_seconds]")
        sys.exit(1)

    test_video = sys.argv[1]
    test_start = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    test_duration = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0

    print(f"Testing face tracker on: {test_video}")
    print(f"  Start: {test_start}s, Duration: {test_duration}s")

    crop_filter, cw, ch = get_smart_crop_filter(test_video, test_start, test_duration)
    print(f"\nCrop dimensions: {cw}x{ch}")
    print(f"FFmpeg filter: {crop_filter[:200]}..." if len(str(crop_filter)) > 200 else f"FFmpeg filter: {crop_filter}")
