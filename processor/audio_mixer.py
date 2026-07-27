"""
RoninClips — Audio Mixer Module
Handles background music mixing with automatic audio ducking.

Uses RMS-based speech detection (from effects.py) to dynamically lower
the background music volume when the speaker is talking, creating a
professional auto-ducking effect.
"""

import subprocess
import os
import sys

# Import sibling module for audio analysis
sys.path.insert(0, os.path.dirname(__file__))
from effects import analyze_audio_rms, extract_wav_for_analysis


# ──────────────────────────────────────────────
# Speech Region Detection
# ──────────────────────────────────────────────

def detect_speech_regions(audio_path, temp_dir=None, silence_threshold=0.02,
                          min_speech_duration=0.3, merge_gap=0.5):
    """
    Detect regions where speech is present in the audio.

    Uses RMS energy analysis — regions with RMS above the silence threshold
    are considered speech. Adjacent speech regions are merged.

    Args:
        audio_path: Path to the audio file
        temp_dir: Directory for temporary WAV conversion
        silence_threshold: RMS below this = silence (0.02 is a good default)
        min_speech_duration: Minimum duration in seconds for a speech region
        merge_gap: Merge speech regions closer than this many seconds

    Returns:
        List of {'start': float, 'end': float} dicts representing speech regions
    """
    if temp_dir is None:
        temp_dir = os.path.dirname(audio_path) or '.'

    wav_path = os.path.join(temp_dir, '_temp_speech_detect.wav')

    try:
        if not extract_wav_for_analysis(audio_path, wav_path):
            print("  [audio_mixer] Failed to convert audio for speech detection")
            return []

        rms_values = analyze_audio_rms(wav_path, window_size_ms=100)
        if not rms_values:
            return []

        # Find speech regions (RMS above silence threshold)
        regions = []
        current_start = None

        for time_sec, rms in rms_values:
            if rms >= silence_threshold:
                if current_start is None:
                    current_start = time_sec
            else:
                if current_start is not None:
                    duration = time_sec - current_start
                    if duration >= min_speech_duration:
                        regions.append({
                            'start': current_start,
                            'end': time_sec,
                        })
                    current_start = None

        # Handle speech at end of audio
        if current_start is not None and rms_values:
            end_time = rms_values[-1][0]
            duration = end_time - current_start
            if duration >= min_speech_duration:
                regions.append({
                    'start': current_start,
                    'end': end_time,
                })

        # Merge nearby speech regions
        if regions and merge_gap > 0:
            merged = [regions[0].copy()]
            for region in regions[1:]:
                if region['start'] - merged[-1]['end'] <= merge_gap:
                    merged[-1]['end'] = region['end']
                else:
                    merged.append(region.copy())
            regions = merged

        print(f"  [audio_mixer] Detected {len(regions)} speech regions")
        return regions

    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)


# ──────────────────────────────────────────────
# Ducking Volume Expression
# ──────────────────────────────────────────────

def generate_ducking_filter(speech_regions, clip_duration,
                            music_volume=0.40, duck_volume=0.12,
                            fade_duration=0.3):
    """
    Generate an FFmpeg volume expression for the music track that ducks
    during speech regions.

    The expression ramps volume:
    - Normal (no speech): music_volume (e.g., 0.40 = 40%)
    - During speech: duck_volume (e.g., 0.12 = 12%)
    - Transitions: smooth ramp over fade_duration seconds

    Args:
        speech_regions: List of {'start': float, 'end': float} dicts
        clip_duration: Total clip length in seconds
        music_volume: Volume level when no speech (0.0-1.0)
        duck_volume: Volume level during speech (0.0-1.0)
        fade_duration: Duration of volume ramp in seconds

    Returns:
        FFmpeg volume expression string (for use in -af "volume='expr'")
    """
    if not speech_regions:
        # No speech detected — play music at normal volume
        return f"volume={music_volume}"

    # Build a volume expression using nested if(between()) calls
    # Default volume is music_volume; during speech regions it drops to duck_volume
    # with fade_duration ramps on either side

    expr_parts = []

    for region in speech_regions:
        s = region['start']
        e = region['end']

        # Ramp down: from s - fade to s
        ramp_down_start = max(0, s - fade_duration)
        # Ramp up: from e to e + fade
        ramp_up_end = min(clip_duration, e + fade_duration)

        vol_range = music_volume - duck_volume

        # Ramp down expression
        ramp_down = (
            f"if(between(t,{ramp_down_start:.3f},{s:.3f}),"
            f"{music_volume}-{vol_range:.3f}*(t-{ramp_down_start:.3f})/{max(fade_duration, 0.001):.3f},"
        )

        # Hold at duck volume
        hold = (
            f"if(between(t,{s:.3f},{e:.3f}),"
            f"{duck_volume},"
        )

        # Ramp up expression
        ramp_up = (
            f"if(between(t,{e:.3f},{ramp_up_end:.3f}),"
            f"{duck_volume}+{vol_range:.3f}*(t-{e:.3f})/{max(fade_duration, 0.001):.3f},"
        )

        expr_parts.append(ramp_down + hold + ramp_up)

    # Build nested expression — default to music_volume
    # We need to close all the if() calls
    full_expr = ""
    for part in expr_parts:
        full_expr += part

    # Default fallback for all non-matched time ranges
    full_expr += f"{music_volume}"

    # Close all the nested if() brackets (3 per region: ramp_down, hold, ramp_up)
    full_expr += ")" * (len(expr_parts) * 3)

    return f"volume='{full_expr}'"


# ──────────────────────────────────────────────
# Music Mixing
# ──────────────────────────────────────────────

def get_audio_duration(audio_path):
    """Get audio file duration in seconds using FFprobe."""
    cmd = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_entries', 'format=duration', audio_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace', timeout=15)
        import json
        info = json.loads(result.stdout)
        return float(info['format']['duration'])
    except Exception:
        return None


def mix_background_music(clip_video_path, music_path, output_path,
                         speech_regions, clip_duration,
                         music_volume=0.40, duck_volume=0.12,
                         fade_in=1.0, fade_out=2.0):
    """
    Mix background music into a rendered clip with auto-ducking.

    The music track is:
    - Looped if shorter than the clip
    - Faded in at the start
    - Faded out at the end
    - Ducked during speech regions

    Args:
        clip_video_path: Path to the rendered clip (with original audio)
        music_path: Path to the background music file (.mp3/.wav)
        output_path: Path for the output file with mixed audio
        speech_regions: List of {'start': float, 'end': float} dicts
        clip_duration: Clip duration in seconds
        music_volume: Normal music volume (0.0-1.0)
        duck_volume: Ducked music volume during speech (0.0-1.0)
        fade_in: Fade-in duration in seconds at start
        fade_out: Fade-out duration in seconds at end

    Returns:
        True if mixing succeeded, False otherwise
    """
    if not os.path.exists(music_path):
        print(f"  [audio_mixer] Music file not found: {music_path}")
        return False

    # Build the ducking volume expression
    ducking_expr = generate_ducking_filter(
        speech_regions, clip_duration,
        music_volume=music_volume, duck_volume=duck_volume
    )

    # Build the music audio filter chain:
    # 1. Loop the music to cover the full clip duration
    # 2. Trim to clip duration
    # 3. Apply ducking volume
    # 4. Apply fade in/out

    music_duration = get_audio_duration(music_path)
    loop_count = 1
    if music_duration and music_duration > 0:
        loop_count = max(1, int(clip_duration / music_duration) + 1)

    # FFmpeg filter graph:
    # [0:a] = original clip audio
    # [1:a] = music track (looped + trimmed + ducked + faded)
    # Mix them together with amix

    fade_out_start = max(0, clip_duration - fade_out)

    music_filter = (
        f"[1:a]aloop=loop={loop_count - 1}:size=2147483647,"
        f"atrim=0:{clip_duration:.3f},"
        f"asetpts=PTS-STARTPTS,"
        f"{ducking_expr},"
        f"afade=t=in:st=0:d={fade_in:.1f},"
        f"afade=t=out:st={fade_out_start:.1f}:d={fade_out:.1f}"
        f"[music];"
        f"[0:a][music]amix=inputs=2:duration=first:dropout_transition=2"
    )

    cmd = (
        f'ffmpeg -i "{clip_video_path}" '
        f'-stream_loop -1 -i "{music_path}" '
        f'-filter_complex "{music_filter}" '
        f'-c:v copy -c:a aac -b:a 192k '
        f'-shortest '
        f'"{output_path}" -y'
    )

    print(f"  [audio_mixer] Mixing background music with auto-ducking...")
    result = subprocess.run(cmd, shell=True, capture_output=True, encoding='utf-8', errors='replace')

    if result.returncode != 0:
        print(f"  [audio_mixer] ⚠️ Music mixing failed: {result.stderr[-300:]}")
        return False

    print(f"  [audio_mixer] ✅ Background music mixed successfully")
    return True


# ──────────────────────────────────────────────
# CLI Test Mode
# ──────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python audio_mixer.py <audio_path>")
        print("  Tests speech region detection on the given audio file.")
        sys.exit(1)

    test_audio = sys.argv[1]
    print(f"Testing speech detection on: {test_audio}")

    regions = detect_speech_regions(test_audio, temp_dir=os.path.dirname(test_audio) or '.')
    print(f"\nDetected {len(regions)} speech regions:")
    for i, region in enumerate(regions):
        dur = region['end'] - region['start']
        print(f"  Region {i + 1}: {region['start']:.1f}s - {region['end']:.1f}s ({dur:.1f}s)")

    if regions:
        ducking = generate_ducking_filter(regions, clip_duration=60.0)
        preview = ducking[:200] + "..." if len(ducking) > 200 else ducking
        print(f"\nDucking filter preview: {preview}")
