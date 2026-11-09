"""
RoninClips — Whip-Pan Transitions Module
Detects jump cuts within rendered clips and inserts motion-blur
"whip pan" transitions at each cut point.

Uses FFmpeg's scene detection to find hard cuts, then re-assembles
the clip with directional blur transition segments inserted via concat.
"""

import subprocess
import os
import json
import sys


# ──────────────────────────────────────────────
# Scene / Jump-Cut Detection
# ──────────────────────────────────────────────

def detect_scene_changes(video_path, threshold=0.3, min_gap=1.0):
    """
    Detect hard cuts (scene changes) in a video using FFmpeg's
    scene change detection filter.

    Args:
        video_path: Path to the video file
        threshold: Scene detection threshold (0.0-1.0). Lower = more sensitive.
                   0.3 is a good default for detecting obvious jump cuts.
        min_gap: Minimum seconds between detected cuts to avoid duplicates

    Returns:
        List of float timestamps (in seconds) where cuts are detected
    """
    cmd = [
        'ffprobe', '-v', 'quiet',
        '-f', 'lavfi',
        '-i', f"movie='{video_path.replace(os.sep, '/')}',select='gt(scene,{threshold})'",
        '-show_entries', 'frame=pts_time',
        '-print_format', 'json'
    ]

    # Alternative: use ffmpeg with select filter and output metadata
    # This is more reliable across platforms
    cmd_alt = (
        f'ffmpeg -i "{video_path}" '
        f'-vf "select=\'gt(scene,{threshold})\',showinfo" '
        f'-f null - 2>&1'
    )

    try:
        result = subprocess.run(cmd_alt, shell=True, capture_output=True, encoding='utf-8', errors='replace', timeout=120)
        output = result.stderr if result.stderr else result.stdout

        # Parse "pts_time:XX.XXXX" from showinfo output
        cut_times = []
        for line in output.split('\n'):
            if 'pts_time:' in line:
                try:
                    pts_part = line.split('pts_time:')[1].split()[0]
                    time_sec = float(pts_part)
                    cut_times.append(time_sec)
                except (IndexError, ValueError):
                    continue

        # Filter: enforce minimum gap and skip very early/late cuts
        if not cut_times:
            return []

        filtered = [cut_times[0]]
        for t in cut_times[1:]:
            if t - filtered[-1] >= min_gap:
                filtered.append(t)

        # Skip cuts in the first 0.5s or last 0.5s (likely intro/outro artifacts)
        video_duration = get_video_duration(video_path)
        if video_duration:
            filtered = [t for t in filtered if 0.5 < t < video_duration - 0.5]

        print(f"  [transitions] Detected {len(filtered)} scene changes (from {len(cut_times)} raw)")
        return filtered

    except subprocess.TimeoutExpired:
        print(f"  [transitions] Scene detection timed out")
        return []
    except Exception as e:
        print(f"  [transitions] Scene detection failed: {e}")
        return []


def get_video_duration(video_path):
    """Get video duration in seconds using FFprobe."""
    cmd = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_entries', 'format=duration', video_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace', timeout=15)
        info = json.loads(result.stdout)
        return float(info['format']['duration'])
    except Exception:
        return None


def get_video_properties(video_path):
    """Get video width, height, and fps."""
    cmd = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_streams', '-select_streams', 'v:0', video_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace', timeout=15)
        info = json.loads(result.stdout)
        stream = info['streams'][0]
        width = int(stream['width'])
        height = int(stream['height'])
        fps_parts = stream.get('r_frame_rate', '30/1').split('/')
        fps = float(fps_parts[0]) / float(fps_parts[1]) if len(fps_parts) == 2 else 30.0
        return width, height, fps
    except Exception:
        return 1080, 1920, 30.0


# ──────────────────────────────────────────────
# Whip-Pan Transition Generation
# ──────────────────────────────────────────────

def apply_whip_pan_transitions(input_video, output_video, cut_points=None,
                                transition_duration=0.2, blur_strength=40,
                                auto_detect=True, scene_threshold=0.3):
    """
    Apply whip-pan transitions at jump cuts within a rendered clip.

    This is a post-processing pass: it takes a fully rendered clip and
    inserts motion-blur transitions at detected (or provided) cut points.

    The approach:
    1. Split the video into segments at each cut point
    2. Re-encode each segment with crossfade + directional blur transitions
       using FFmpeg's xfade filter

    Args:
        input_video: Path to the rendered clip
        output_video: Path for the output with transitions
        cut_points: Optional list of timestamps. If None, auto-detect.
        transition_duration: Duration of each transition in seconds (0.15-0.3)
        blur_strength: Blur intensity (10-80). Higher = more dramatic.
        auto_detect: If True and cut_points is None, auto-detect scene changes
        scene_threshold: Threshold for auto-detection (0.0-1.0)

    Returns:
        True if successful, False otherwise
    """
    if cut_points is None and auto_detect:
        cut_points = detect_scene_changes(input_video, threshold=scene_threshold)

    if not cut_points:
        print(f"  [transitions] No cut points found, skipping transitions")
        return False

    print(f"  [transitions] Applying whip-pan at {len(cut_points)} cut point(s)...")

    width, height, fps = get_video_properties(input_video)
    video_duration = get_video_duration(input_video)

    if not video_duration:
        print(f"  [transitions] Cannot determine video duration")
        return False

    # Limit number of transitions to avoid excessive filter complexity
    if len(cut_points) > 8:
        print(f"  [transitions] Limiting to 8 transitions (from {len(cut_points)})")
        cut_points = cut_points[:8]

    # Build the xfade filter chain
    # xfade creates a smooth transition between two video streams
    # We'll use the 'smoothleft' or 'smoothright' transition with added blur

    # Split into segments using trim filters
    num_segments = len(cut_points) + 1
    segment_boundaries = [0.0] + cut_points + [video_duration]

    # Build filter complex for multi-segment crossfade
    filter_parts = []
    input_labels = []

    # Create trimmed segments
    for i in range(num_segments):
        start = segment_boundaries[i]
        end = segment_boundaries[i + 1]
        # Trim + setpts to reset timestamps
        filter_parts.append(
            f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{i}]"
        )
        input_labels.append(f"v{i}")

    # Chain xfade transitions between consecutive segments
    # xfade transition types that look like whip-pans:
    # - smoothleft / smoothright: directional wipe
    # - wipeleft / wiperight: hard wipe
    # We alternate direction for variety (left, right, up, down)
    directions = ['smoothleft', 'smoothright', 'smoothup', 'smoothdown']

    if num_segments == 1:
        # No transitions needed
        print(f"  [transitions] Only one segment, no transitions to apply")
        return False

    # Build cascading xfade: [v0][v1]xfade -> [xf0], [xf0][v2]xfade -> [xf1], etc.
    # IMPORTANT: xfade's 'offset' parameter is the timestamp in the ACCUMULATED
    # output stream where the transition starts — NOT the segment duration.
    # For cascaded xfades, each subsequent offset must account for the total
    # duration of all previous segments minus all previous transitions.
    current_label = input_labels[0]
    accumulated_duration = segment_boundaries[1] - segment_boundaries[0]  # first segment duration

    for i in range(1, num_segments):
        direction = directions[i % len(directions)]
        next_label = input_labels[i]
        out_label = f"xf{i - 1}" if i < num_segments - 1 else "outv"

        # The offset is where in the accumulated output the transition starts
        # = total accumulated duration so far minus the transition duration
        offset = max(0, accumulated_duration - transition_duration)

        filter_parts.append(
            f"[{current_label}][{next_label}]xfade="
            f"transition={direction}:"
            f"duration={transition_duration:.3f}:"
            f"offset={offset:.3f}"
            f"[{out_label}]"
        )
        current_label = out_label

        # After this xfade, the accumulated duration grows by the next segment
        # duration minus the transition overlap
        next_seg_dur = segment_boundaries[i + 1] - segment_boundaries[i]
        accumulated_duration = offset + transition_duration + next_seg_dur - transition_duration
        # Simplified: accumulated_duration = offset + next_seg_dur

    # Audio: no transition processing, just copy
    # We need to handle audio segments similarly but with acrossfade
    audio_parts = []
    audio_labels = []

    for i in range(num_segments):
        start = segment_boundaries[i]
        end = segment_boundaries[i + 1]
        audio_parts.append(
            f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{i}]"
        )
        audio_labels.append(f"a{i}")

    # Chain audio crossfades
    current_audio = audio_labels[0]
    for i in range(1, num_segments):
        next_audio = audio_labels[i]
        out_audio = f"xa{i - 1}" if i < num_segments - 1 else "outa"

        audio_parts.append(
            f"[{current_audio}][{next_audio}]acrossfade="
            f"d={transition_duration:.3f}:"
            f"c1=tri:c2=tri"
            f"[{out_audio}]"
        )
        current_audio = out_audio

    # Combine all filter parts
    all_filters = filter_parts + audio_parts
    filter_complex = ";".join(all_filters)

    cmd = [
        'ffmpeg', '-i', input_video,
        '-filter_complex', filter_complex,
        '-map', '[outv]', '-map', '[outa]',
        '-c:v', 'libx264', '-preset', 'medium', '-crf', '22',
        '-profile:v', 'high', '-level', '4.0', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart',
        output_video, '-y'
    ]

    result = subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace')

    if result.returncode != 0:
        print(f"  [transitions] ⚠️ Whip-pan transition failed: {result.stderr[-300:]}")

        # Fallback: try a simpler approach with just the first cut point
        if len(cut_points) > 1:
            print(f"  [transitions] Retrying with only the first cut point...")
            return apply_whip_pan_transitions(
                input_video, output_video,
                cut_points=[cut_points[0]],
                transition_duration=transition_duration,
                blur_strength=blur_strength,
                auto_detect=False
            )
        return False

    print(f"  [transitions] ✅ Whip-pan transitions applied at {len(cut_points)} point(s)")
    return True


# ──────────────────────────────────────────────
# CLI Test Mode
# ──────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python transitions.py <video_path>")
        print("  Tests scene change detection on the given video.")
        sys.exit(1)

    test_video = sys.argv[1]
    print(f"Testing scene change detection on: {test_video}")

    cuts = detect_scene_changes(test_video)
    print(f"\nDetected {len(cuts)} scene changes:")
    for i, t in enumerate(cuts):
        print(f"  Cut {i + 1}: {t:.2f}s")

    if cuts:
        duration = get_video_duration(test_video)
        print(f"\nVideo duration: {duration:.2f}s")
        print(f"Would insert whip-pan transitions at: {', '.join(f'{t:.2f}s' for t in cuts)}")
