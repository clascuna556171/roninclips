"""
RoninClips — Visual Effects Module
Handles punch-in zoom, Ken Burns slow zoom, and volume spike detection.
All effects output FFmpeg filter strings that can be chained in the render pipeline.
"""

import subprocess
import json
import struct
import wave
import os
import numpy as np


# ──────────────────────────────────────────────
# Volume Spike Detection (for Punch-In Zoom)
# ──────────────────────────────────────────────

def extract_wav_for_analysis(input_audio_path, output_wav_path):
    """
    Convert any audio to a 16-bit mono WAV for volume analysis.
    """
    cmd = [
        'ffmpeg', '-i', input_audio_path,
        '-ac', '1', '-ar', '16000', '-sample_fmt', 's16',
        output_wav_path, '-y'
    ]
    result = subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace')
    return result.returncode == 0


def analyze_audio_rms(wav_path, window_size_ms=200):
    """
    Compute RMS energy over sliding windows of the audio.

    Args:
        wav_path: Path to a 16-bit mono WAV file
        window_size_ms: Size of analysis window in milliseconds

    Returns:
        List of (time_seconds, rms_value) tuples
    """
    try:
        with wave.open(wav_path, 'rb') as wf:
            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            sample_rate = wf.getframerate()
            n_frames = wf.getnframes()

            raw_data = wf.readframes(n_frames)
    except Exception as e:
        print(f"  [effects] Cannot read WAV: {e}")
        return []

    # Convert to numpy array
    if sample_width == 2:
        samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float64)
    elif sample_width == 4:
        samples = np.frombuffer(raw_data, dtype=np.int32).astype(np.float64)
    else:
        print(f"  [effects] Unsupported sample width: {sample_width}")
        return []

    if n_channels > 1:
        samples = samples[::n_channels]  # Take first channel

    # Normalize to [-1, 1]
    max_val = 2 ** (sample_width * 8 - 1)
    samples = samples / max_val

    # Calculate RMS per window
    window_samples = int(sample_rate * window_size_ms / 1000)
    rms_values = []

    for start in range(0, len(samples) - window_samples, window_samples):
        window = samples[start:start + window_samples]
        rms = np.sqrt(np.mean(window ** 2))
        time_sec = start / sample_rate
        rms_values.append((time_sec, rms))

    return rms_values


def detect_volume_spikes(audio_path, threshold_multiplier=1.5, min_spike_duration=0.5,
                          merge_gap=1.0, temp_dir=None):
    """
    Detect moments where audio volume spikes above the average.

    Args:
        audio_path: Path to the audio file (any format)
        threshold_multiplier: How many times above average RMS counts as a spike (1.5 = 50% louder)
        min_spike_duration: Minimum duration of a spike in seconds
        merge_gap: Merge spikes that are within this many seconds of each other
        temp_dir: Directory for temp files, defaults to same dir as audio

    Returns:
        List of {'start': float, 'end': float, 'intensity': float} dicts
    """
    if temp_dir is None:
        temp_dir = os.path.dirname(audio_path)

    wav_path = os.path.join(temp_dir, '_temp_analysis.wav')

    try:
        if not extract_wav_for_analysis(audio_path, wav_path):
            print("  [effects] Failed to convert audio for analysis")
            return []

        rms_values = analyze_audio_rms(wav_path)
        if not rms_values:
            return []

        # Calculate average RMS (excluding silence)
        rms_only = [r for _, r in rms_values if r > 0.01]  # Ignore near-silence
        if not rms_only:
            return []

        avg_rms = np.mean(rms_only)
        threshold = avg_rms * threshold_multiplier

        print(f"  [effects] Audio analysis: avg RMS={avg_rms:.4f}, spike threshold={threshold:.4f}")

        # Find spike regions
        spikes = []
        current_spike_start = None
        current_spike_max = 0

        for time_sec, rms in rms_values:
            if rms >= threshold:
                if current_spike_start is None:
                    current_spike_start = time_sec
                current_spike_max = max(current_spike_max, rms)
            else:
                if current_spike_start is not None:
                    duration = time_sec - current_spike_start
                    if duration >= min_spike_duration:
                        spikes.append({
                            'start': current_spike_start,
                            'end': time_sec,
                            'intensity': current_spike_max / avg_rms
                        })
                    current_spike_start = None
                    current_spike_max = 0

        # Handle spike at the end
        if current_spike_start is not None:
            end_time = rms_values[-1][0]
            duration = end_time - current_spike_start
            if duration >= min_spike_duration:
                spikes.append({
                    'start': current_spike_start,
                    'end': end_time,
                    'intensity': current_spike_max / avg_rms
                })

        # Merge nearby spikes
        if spikes and merge_gap > 0:
            merged = [spikes[0]]
            for spike in spikes[1:]:
                if spike['start'] - merged[-1]['end'] <= merge_gap:
                    merged[-1]['end'] = spike['end']
                    merged[-1]['intensity'] = max(merged[-1]['intensity'], spike['intensity'])
                else:
                    merged.append(spike)
            spikes = merged

        print(f"  [effects] Detected {len(spikes)} volume spikes")
        return spikes

    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)


# ──────────────────────────────────────────────
# Punch-In Zoom Filter
# ──────────────────────────────────────────────

def generate_punchin_filter(spikes, total_duration, input_w, input_h,
                             zoom_factor=1.15, ease_duration=0.3):
    """
    Generate an FFmpeg scale+crop filter that zooms in during volume spikes.

    Uses scale with expression-based dimensions + crop to center:
    - During spike: scale up by zoom_factor, then crop back to original size
    - During normal: no zoom (1.0x)
    - Smooth ease-in/out over ease_duration seconds

    This replaces the old zoompan approach which destroyed framerate by
    treating video frames like a slideshow (d=1 = 1 output per input frame).

    Returns an FFmpeg filter string (scale + crop chain).
    """
    if not spikes:
        return None

    # For longer videos/clips, cap to the top 12 most prominent spikes
    # to prevent FFmpeg filter expression parsing failure and stack overflow.
    if len(spikes) > 12:
        spikes = sorted(spikes, key=lambda s: s.get('peak', 0), reverse=True)[:12]
        spikes = sorted(spikes, key=lambda s: s['start'])

    # Build a zoom expression using FFmpeg's expression syntax
    # z = 1.0 normally, z = zoom_factor during spikes, with easing
    zoom_expr_parts = []

    for spike in spikes:
        s = spike['start']
        e = spike['end']
        # Ease in: from s-ease to s
        ease_in_start = max(0, s - ease_duration)
        # Ease out: from e to e+ease
        ease_out_end = min(total_duration, e + ease_duration)

        # Build a contribution for this spike
        # During [ease_in_start, s]: ramp from 1.0 to zoom_factor
        # During [s, e]: hold at zoom_factor
        # During [e, ease_out_end]: ramp from zoom_factor to 1.0
        zf = zoom_factor
        part = (
            f"if(between(t,{ease_in_start:.3f},{s:.3f}),"
            f"1+{zf - 1:.3f}*(t-{ease_in_start:.3f})/{max(ease_duration, 0.001):.3f},"
            f"if(between(t,{s:.3f},{e:.3f}),"
            f"{zf:.3f},"
            f"if(between(t,{e:.3f},{ease_out_end:.3f}),"
            f"{zf:.3f}-{zf - 1:.3f}*(t-{e:.3f})/{max(ease_duration, 0.001):.3f},"
            f"1)))"
        )
        zoom_expr_parts.append(part)

    if not zoom_expr_parts:
        return None

    # Combine all spike zoom expressions (take the max zoom from any overlapping spike)
    if len(zoom_expr_parts) == 1:
        zoom_expr = zoom_expr_parts[0]
    else:
        # Nested max() to pick the highest zoom at any point
        zoom_expr = zoom_expr_parts[0]
        for part in zoom_expr_parts[1:]:
            zoom_expr = f"max({zoom_expr},{part})"

    # Use scale+crop instead of zoompan:
    # - scale up by the zoom expression (w*z, h*z)
    # - crop back to original size, centered
    # This preserves the native framerate — no slideshow effect.
    # Ensure even dimensions with trunc() for codec compatibility.
    # max() clamping prevents scaled dimensions from dropping below the
    # crop target when zoom_expr rounds down to exactly 1.0.
    w = input_w
    h = input_h

    zoom_filter = (
        f"scale="
        f"'max({w},trunc(iw*({zoom_expr})/2)*2)'"
        f":'max({h},trunc(ih*({zoom_expr})/2)*2)'"
        f":eval=frame:flags=bilinear,"
        f"crop={w}:{h}"
    )

    return zoom_filter


# ──────────────────────────────────────────────
# Ken Burns (Slow Zoom) Filter
# ──────────────────────────────────────────────

def generate_kenburns_filter(total_duration, input_w, input_h,
                              start_zoom=1.0, end_zoom=1.05, fps=30):
    """
    Generate a subtle continuous slow zoom (Ken Burns effect).

    Uses scale+crop instead of zoompan to preserve native framerate.
    The zoom ramps linearly from start_zoom to end_zoom over the clip duration.

    Args:
        total_duration: Total clip duration in seconds
        input_w, input_h: Input dimensions (after crop)
        start_zoom: Starting zoom level (1.0 = no zoom)
        end_zoom: Ending zoom level (1.05 = 5% zoom in)
        fps: Video FPS (unused — kept for API compatibility)

    Returns:
        FFmpeg scale+crop filter string
    """
    if total_duration <= 0:
        return None

    # zoom = start_zoom + (end_zoom - start_zoom) * (t / total_duration)
    zoom_range = end_zoom - start_zoom
    zoom_expr = f"{start_zoom:.4f}+{zoom_range:.4f}*t/{total_duration:.3f}"

    w = input_w
    h = input_h

    zoom_filter = (
        f"scale="
        f"'max({w},trunc(iw*({zoom_expr})/2)*2)'"
        f":'max({h},trunc(ih*({zoom_expr})/2)*2)'"
        f":eval=frame:flags=bilinear,"
        f"crop={w}:{h}"
    )

    return zoom_filter


# ──────────────────────────────────────────────
# CLI Test Mode
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python effects.py <audio_path>")
        print("  Tests volume spike detection on the given audio file.")
        sys.exit(1)

    test_audio = sys.argv[1]
    print(f"Testing volume spike detection on: {test_audio}")

    spikes = detect_volume_spikes(test_audio, temp_dir=os.path.dirname(test_audio) or '.')
    print(f"\nDetected {len(spikes)} spikes:")
    for i, spike in enumerate(spikes):
        print(f"  Spike {i + 1}: {spike['start']:.1f}s - {spike['end']:.1f}s "
              f"(intensity: {spike['intensity']:.2f}x average)")

    if spikes:
        zoom_filter = generate_punchin_filter(spikes, 60.0, 1080, 1920)
        if zoom_filter:
            preview = zoom_filter[:200] + "..." if len(zoom_filter) > 200 else zoom_filter
            print(f"\nPunch-in filter preview: {preview}")
