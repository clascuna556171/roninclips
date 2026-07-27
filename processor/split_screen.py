"""
RoninClips — Split-Screen Module
Detects multiple speakers in podcast/interview content and generates
FFmpeg filter graphs that display each speaker in their own panel
using a vertical top/bottom split layout.

Standard TikTok/Shorts podcast layout: two 1080×960 panels stacked
vertically in a 1080×1920 frame.
"""

import os
import sys
import numpy as np

# Import sibling module for face detection
sys.path.insert(0, os.path.dirname(__file__))
from face_tracker import (
    analyze_video_faces, get_video_info,
    clamp_crop_x, clamp_crop_y, exponential_smooth
)


# ──────────────────────────────────────────────
# Speaker Zone Detection & Clustering
# ──────────────────────────────────────────────

def detect_speaker_zones(video_path, start_time, duration,
                         sample_every_n=10, min_separation_pct=0.15):
    """
    Detect distinct speaker positions in the video by clustering face detections.

    Speakers are identified by their horizontal position — faces consistently
    appearing in different horizontal regions of the frame are considered
    different speakers.

    Args:
        video_path: Path to the source video
        start_time: Start time in seconds
        duration: Clip duration in seconds
        sample_every_n: Frame sampling rate (higher = faster, less accurate)
        min_separation_pct: Minimum horizontal distance between speakers
                           as a percentage of frame width (0.15 = 15%)

    Returns:
        List of speaker zone dicts:
        [{'cx': float, 'cy': float, 'count': int, 'face_positions': list}]
        Sorted left-to-right. Returns empty list if < 2 speakers found.
        Also returns (input_width, input_height, fps).
    """
    detections, (width, height, fps) = analyze_video_faces(
        video_path, start_time, duration, sample_every_n
    )

    if not detections:
        print(f"  [split_screen] No face detections, cannot create split screen")
        return [], (width, height, fps)

    # Collect all face center positions
    all_faces = []
    for det in detections:
        for face in det['faces']:
            all_faces.append({
                'cx': face['cx'],
                'cy': face['cy'],
                'time': det['time'],
                'confidence': face.get('confidence', 0.5),
            })

    if len(all_faces) < 5:
        print(f"  [split_screen] Too few face detections ({len(all_faces)})")
        return [], (width, height, fps)

    # Simple 2-cluster algorithm based on horizontal position
    # Sort faces by X position and find the natural split
    min_sep = width * min_separation_pct
    cx_values = sorted([f['cx'] for f in all_faces])

    # Find the largest gap in X positions
    best_gap = 0
    best_gap_idx = -1
    for i in range(1, len(cx_values)):
        gap = cx_values[i] - cx_values[i - 1]
        if gap > best_gap:
            best_gap = gap
            best_gap_idx = i

    if best_gap < min_sep:
        print(f"  [split_screen] No clear speaker separation (best gap: {best_gap:.0f}px, need {min_sep:.0f}px)")
        return [], (width, height, fps)

    # Split into two clusters
    split_x = (cx_values[best_gap_idx - 1] + cx_values[best_gap_idx]) / 2

    left_faces = [f for f in all_faces if f['cx'] < split_x]
    right_faces = [f for f in all_faces if f['cx'] >= split_x]

    if len(left_faces) < 3 or len(right_faces) < 3:
        print(f"  [split_screen] Unbalanced clusters (left={len(left_faces)}, right={len(right_faces)})")
        return [], (width, height, fps)

    # Calculate cluster centers (median for robustness)
    zones = []
    for cluster_faces, label in [(left_faces, 'left'), (right_faces, 'right')]:
        cx = np.median([f['cx'] for f in cluster_faces])
        cy = np.median([f['cy'] for f in cluster_faces])
        zones.append({
            'cx': cx,
            'cy': cy,
            'count': len(cluster_faces),
            'label': label,
            'face_positions': cluster_faces,
        })

    # Sort left to right
    zones.sort(key=lambda z: z['cx'])

    print(f"  [split_screen] Detected {len(zones)} speakers:")
    for z in zones:
        print(f"    {z['label']}: center=({z['cx']:.0f}, {z['cy']:.0f}), detections={z['count']}")

    return zones, (width, height, fps)


# ──────────────────────────────────────────────
# Split-Screen FFmpeg Filter Generation
# ──────────────────────────────────────────────

def generate_split_screen_filter(speaker_zones, input_w, input_h,
                                  output_w=1080, output_h=1920,
                                  divider_height=4):
    """
    Generate an FFmpeg filter graph that creates a vertical split-screen layout.

    Each speaker is cropped from the source, scaled to fill half the output frame,
    and stacked vertically with a thin divider line.

    Layout (1080×1920):
    ┌────────────────┐
    │   Speaker 1    │  960px
    │  (top panel)   │
    ├────────────────┤  4px divider
    │   Speaker 2    │  956px
    │ (bottom panel) │
    └────────────────┘

    Args:
        speaker_zones: List of 2 speaker zone dicts from detect_speaker_zones()
        input_w: Source video width
        input_h: Source video height
        output_w: Output video width (default 1080)
        output_h: Output video height (default 1920)
        divider_height: Height of the divider line in pixels

    Returns:
        FFmpeg filter_complex string, or None if invalid input
    """
    if len(speaker_zones) < 2:
        return None

    # Each panel height (accounting for divider)
    panel_h = (output_h - divider_height) // 2
    panel_w = output_w

    # Calculate crop dimensions for each speaker from the source
    # We want to crop a region around each speaker's face that will look good
    # when scaled to panel_w × panel_h (which is ~1080×958, roughly 16:9)

    # Target aspect ratio for each panel crop
    panel_aspect = panel_w / panel_h  # ~1.127 (slightly wider than 1:1)

    # Calculate crop size from source
    # Use a generous crop around each speaker
    crop_h = int(input_h * 0.85)  # Use 85% of source height
    crop_w = int(crop_h * panel_aspect)

    # Clamp to source dimensions
    if crop_w > input_w:
        crop_w = input_w
        crop_h = int(crop_w / panel_aspect)

    # Ensure even dimensions
    crop_w = crop_w - (crop_w % 2)
    crop_h = crop_h - (crop_h % 2)

    # Calculate crop positions for each speaker
    crops = []
    for zone in speaker_zones[:2]:
        cx = zone['cx']
        cy = zone['cy']

        # Center the crop on the speaker's face
        crop_x = int(cx - crop_w / 2)
        crop_y = int(cy - crop_h / 2)

        # Clamp to frame bounds
        crop_x = max(0, min(crop_x, input_w - crop_w))
        crop_y = max(0, min(crop_y, input_h - crop_h))

        crops.append((crop_x, crop_y, crop_w, crop_h))

    # Build the filter graph
    # [0:v] → split into two streams → crop each → scale each → pad → vstack

    filter_parts = []

    # Split input into two streams
    filter_parts.append(f"[0:v]split=2[src1][src2]")

    # Crop and scale speaker 1 (top panel)
    c1 = crops[0]
    filter_parts.append(
        f"[src1]crop={c1[2]}:{c1[3]}:{c1[0]}:{c1[1]},"
        f"scale={panel_w}:{panel_h}:force_original_aspect_ratio=decrease,"
        f"pad={panel_w}:{panel_h}:(ow-iw)/2:(oh-ih)/2:black"
        f"[top]"
    )

    # Crop and scale speaker 2 (bottom panel)
    c2 = crops[1]
    filter_parts.append(
        f"[src2]crop={c2[2]}:{c2[3]}:{c2[0]}:{c2[1]},"
        f"scale={panel_w}:{panel_h}:force_original_aspect_ratio=decrease,"
        f"pad={panel_w}:{panel_h}:(ow-iw)/2:(oh-ih)/2:black"
        f"[bottom]"
    )

    # Create divider line (thin dark bar)
    filter_parts.append(
        f"color=c=0x1a1a1a:s={panel_w}x{divider_height}:r=30[divider]"
    )

    # Stack: top + divider + bottom
    filter_parts.append(
        f"[top][divider][bottom]vstack=inputs=3[outv]"
    )

    filter_complex = ";".join(filter_parts)
    return filter_complex


def get_split_screen_filter(video_path, start_time, duration,
                             output_w=1080, output_h=1920):
    """
    High-level API: Detect speakers and return a ready-to-use split-screen
    FFmpeg filter_complex string.

    Args:
        video_path: Path to the source video
        start_time: Clip start in seconds
        duration: Clip duration in seconds
        output_w: Output width
        output_h: Output height

    Returns:
        (filter_complex_string, output_w, output_h) or (None, input_w, input_h)
        if split-screen cannot be created.
    """
    zones, (w, h, fps) = detect_speaker_zones(
        video_path, start_time, duration, sample_every_n=10
    )

    if len(zones) < 2:
        print(f"  [split_screen] Fewer than 2 speakers — falling back to normal crop")
        return None, w, h

    filter_complex = generate_split_screen_filter(
        zones, w, h, output_w, output_h
    )

    return filter_complex, output_w, output_h


# ──────────────────────────────────────────────
# CLI Test Mode
# ──────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python split_screen.py <video_path> [start_seconds] [duration_seconds]")
        print("  Tests speaker zone detection on the given video.")
        sys.exit(1)

    test_video = sys.argv[1]
    test_start = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    test_duration = float(sys.argv[3]) if len(sys.argv) > 3 else 15.0

    print(f"Testing split-screen detection on: {test_video}")
    print(f"  Start: {test_start}s, Duration: {test_duration}s")

    zones, (w, h, fps) = detect_speaker_zones(test_video, test_start, test_duration)

    if zones:
        print(f"\nSource: {w}x{h} @ {fps:.1f}fps")
        print(f"Found {len(zones)} speaker zone(s):")
        for z in zones:
            print(f"  {z['label']}: center=({z['cx']:.0f}, {z['cy']:.0f}), detections={z['count']}")

        if len(zones) >= 2:
            filter_str = generate_split_screen_filter(zones, w, h)
            if filter_str:
                preview = filter_str[:300] + "..." if len(filter_str) > 300 else filter_str
                print(f"\nFilter complex:\n{preview}")
    else:
        print("\nNo speaker zones detected — split-screen not available for this clip.")
