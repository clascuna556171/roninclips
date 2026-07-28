import sys
import os
import subprocess
import mysql.connector
from groq import Groq
import json
from dotenv import load_dotenv
from faster_whisper import WhisperModel

# Fix Windows encoding — prevent crash on emoji/unicode in print() AND subprocess pipes.
# subprocess.run(..., text=True) uses locale.getpreferredencoding() which is cp1252 on Windows.
# PYTHONUTF8=1 forces ALL text I/O (including subprocess pipes) to use UTF-8.
if sys.platform == 'win32':
    os.environ['PYTHONUTF8'] = '1'
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Load Laravel's .env file from the parent directory
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# 1. Boot Environment & Context
VIDEO_ID = sys.argv[1]

# Parse processing settings from CLI arg (JSON string from Laravel)
DEFAULT_SETTINGS = {
    'output_format': '9:16',
    'caption_style': 'yellow_pop',
    'caption_font': 'Arial Black',
    'caption_position': 'bottom',
    'caption_layout': 'two_line',
    'transition_speed': 0.25,
    'full_video_mode': False,
    'smart_crop': True,
    'auto_captions': True,
    'punch_in_zoom': False,
    'ken_burns': False,
    'emoji_overlays': False,
    'whip_pan_transitions': False,
    'background_music': False,
    'bgm_path': '',
    'split_screen': False,
}

if len(sys.argv) > 2 and sys.argv[2] != '--b64':
    try:
        parsed = json.loads(sys.argv[2])
        for key, val in DEFAULT_SETTINGS.items():
            if key not in parsed:
                parsed[key] = val
        SETTINGS = parsed
    except json.JSONDecodeError:
        print(f"Warning: Could not parse settings JSON from CLI, using defaults.")
        SETTINGS = DEFAULT_SETTINGS.copy()
else:
    SETTINGS = DEFAULT_SETTINGS.copy()

print(f"Initial settings: {json.dumps(SETTINGS, indent=2)}")

client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))

# Fetch DB connection details from .env
db_host = os.environ.get("DB_HOST", "127.0.0.1")
db_user = os.environ.get("DB_USERNAME", "root")
db_password = os.environ.get("DB_PASSWORD", "")
db_name = os.environ.get("DB_DATABASE", "roninclips")
db_port = int(os.environ.get("DB_PORT", 3306))

db = mysql.connector.connect(
    host=db_host, user=db_user, password=db_password, database=db_name, port=db_port
)
cursor = db.cursor(dictionary=True)

# Import local modules
sys.path.insert(0, os.path.dirname(__file__))
from face_tracker import get_smart_crop_filter, get_video_info
from effects import detect_volume_spikes, generate_punchin_filter, generate_kenburns_filter
from emoji_overlay import scan_transcript_for_emojis, generate_emoji_overlay_data
from audio_mixer import detect_speech_regions, mix_background_music
from transitions import apply_whip_pan_transitions
from split_screen import get_split_screen_filter


# ──────────────────────────────────────────────
# Helper Functions
# ──────────────────────────────────────────────

def run_ffmpeg(cmd, **kwargs):
    """
    Run a subprocess command with UTF-8 encoding to avoid Windows cp1252 crashes.
    subprocess.run(..., text=True) uses locale.getpreferredencoding() which is cp1252 on Windows.
    FFmpeg's stderr often contains non-ASCII bytes that crash cp1252 decoding.
    This wrapper forces UTF-8 with error replacement.
    """
    kwargs.setdefault('shell', True)
    kwargs.setdefault('capture_output', True)
    # Replace text=True with explicit encoding
    kwargs.pop('text', None)
    return subprocess.run(cmd, encoding='utf-8', errors='replace', **kwargs)

def parse_time_to_seconds(time_val):
    """
    Convert a time value to float seconds.
    Handles: HH:MM:SS strings, HH:MM:SS.ms strings, timedelta objects, and numeric values.
    MySQL TIME columns return timedelta objects in Python — this handles all cases.
    """
    import datetime
    if isinstance(time_val, (int, float)):
        return float(time_val)
    if isinstance(time_val, datetime.timedelta):
        return time_val.total_seconds()
    if isinstance(time_val, str):
        parts = time_val.split(':')
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    # Last resort
    return float(str(time_val).split(':')[0]) * 3600 if ':' in str(time_val) else float(time_val)


def format_time(seconds):
    """Convert seconds to HH:MM:SS string."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_seconds_ffmpeg(seconds):
    """Convert seconds to HH:MM:SS.mmm format for precise FFmpeg seeking."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def format_ass_time(seconds):
    """Convert seconds to ASS time format H:MM:SS.CC"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def ffmpeg_escape_path(path):
    """
    Escape a file path for use inside FFmpeg filter strings (e.g., ass= or subtitles=).
    Handles Windows drive letters, backslashes, and special characters.
    """
    # Normalize to forward slashes
    p = path.replace('\\', '/')
    # Escape colons (C: drive letters) — FFmpeg filter parser uses : as delimiter
    p = p.replace(':', '\\:')
    return p


def generate_ass_subtitles(words, output_path, output_w=1080, output_h=1920,
                            style_preset='yellow_pop', font_family='Arial Black',
                            position='bottom', layout_mode='two_line'):
    """
    Generate an ASS subtitle file with OpusClips-style word-by-word highlighting.
    Supports customizable color palettes, font families, positioning, and layout modes.
    """
    # Palette configurations (ASS color format: &H00BBGGRR&)
    PALETTES = {
        'yellow_pop': {
            'active_color': '\\c&H00FFFF&',      # Yellow (RGB #FFFF00 -> BGR 00FFFF)
            'inactive_color': '\\c&HFFFFFF&',    # White
            'outline_size': 4,
            'shadow_size': 2,
        },
        'neon_cyan': {
            'active_color': '\\c&HFFFF00&',      # Cyan (RGB #00FFFF -> BGR FFFF00)
            'inactive_color': '\\c&HEEEEEE&',    # Off-white
            'outline_size': 4,
            'shadow_size': 2,
        },
        'bold_white': {
            'active_color': '\\c&H00FF00&',      # Neon Green (RGB #00FF00 -> BGR 00FF00)
            'inactive_color': '\\c&HFFFFFF&',    # Pure White
            'outline_size': 5,
            'shadow_size': 3,
        },
    }

    style_cfg = PALETTES.get(style_preset, PALETTES['yellow_pop'])

    # Font sizing & Layout chunk size
    if layout_mode == 'single_word':
        chunk_size = 1
        font_size = max(60, int(output_h / 18))
    elif layout_mode == 'full_line':
        chunk_size = 7
        font_size = max(40, int(output_h / 28))
    else:  # 'two_line' default
        chunk_size = 4
        font_size = max(48, int(output_h / 24))

    # Positioning (ASS Alignment: 2=Bottom, 5=Center, 8=Top)
    pos = str(position).lower()
    if pos == 'top':
        alignment = 8
        margin_v = int(output_h * 0.10)
    elif pos == 'center':
        alignment = 5
        margin_v = 0
    else:  # 'bottom' default
        alignment = 2
        margin_v = int(output_h * 0.14)  # 14% bottom margin to clear TikTok/Reels UI

    outline_val = style_cfg['outline_size']
    shadow_val = style_cfg['shadow_size']
    font_name = font_family.strip() if font_family else 'Arial Black'

    ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {output_w}
PlayResY: {output_h}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{outline_val},{shadow_val},{alignment},20,20,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    chunks = []
    for i in range(0, len(words), chunk_size):
        chunks.append(words[i:i + chunk_size])

    events = []
    for chunk in chunks:
        chunk_end = chunk[-1]['end']

        for i, current_word in enumerate(chunk):
            event_start = current_word['start']
            if i < len(chunk) - 1:
                event_end = chunk[i + 1]['start']
            else:
                event_end = chunk_end

            if event_end - event_start < 0.05:
                event_end = event_start + 0.15

            parts = []
            for j, w in enumerate(chunk):
                word_text = w['word'].strip().upper()
                if not word_text:
                    continue

                line_prefix = "\\N " if (layout_mode == 'two_line' and j == 2) else ""

                if j == i:
                    # Highlight + scale pop (115% size) for active word
                    active_tag = "{" + style_cfg['active_color'] + "\\fscx115\\fscy115}"
                    reset_tag = "{" + style_cfg['inactive_color'] + "\\fscx100\\fscy100}"
                    parts.append(line_prefix + active_tag + word_text + reset_tag)
                else:
                    parts.append(line_prefix + word_text)

            text = " ".join(parts)
            if text.strip():
                start_str = format_ass_time(event_start)
                end_str = format_ass_time(event_end)
                events.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{text}")

    with open(output_path, 'w', encoding='utf-8-sig') as f:
        f.write(ass_header)
        f.write('\n'.join(events))
        f.write('\n')

    return len(events)


# ──────────────────────────────────────────────
# Main Pipeline
# ──────────────────────────────────────────────

try:
    # Fetch video metadata
    cursor.execute("SELECT * FROM long_videos WHERE id = %s", (VIDEO_ID,))
    video = cursor.fetchone()

    if not video:
        raise Exception(f"Video with id {VIDEO_ID} not found in database.")

    # Override settings from DB if available (fixes Windows CLI JSON escaping issues)
    if video.get('processing_settings'):
        try:
            db_settings = json.loads(video['processing_settings'])
            SETTINGS.update(db_settings)
            
            # Normalize boolean values
            for key in ['full_video_mode', 'smart_crop', 'auto_captions', 'punch_in_zoom', 'ken_burns',
                        'emoji_overlays', 'whip_pan_transitions', 'background_music', 'split_screen']:
                val = SETTINGS.get(key)
                if isinstance(val, str):
                    SETTINGS[key] = val.lower() in ('true', '1', 'yes')
                elif isinstance(val, (int, float)):
                    SETTINGS[key] = bool(val)
                    
            print(f"Loaded DB processing settings: {json.dumps(SETTINGS, indent=2)}")
        except Exception as e:
            print(f"Warning: Could not parse DB settings: {e}")

    cursor.execute("UPDATE long_videos SET status = 'transcribing' WHERE id = %s", (VIDEO_ID,))
    db.commit()

    # 2. Extract Audio
    audio_path = os.path.join(os.path.dirname(__file__), '..', f'storage/app/temp_{VIDEO_ID}.mp3')
    audio_path = os.path.abspath(audio_path)
    os.makedirs(os.path.dirname(audio_path), exist_ok=True)

    print(f"Extracting audio from: {video['storage_path']}")
    result = run_ffmpeg(
        f'ffmpeg -i "{video["storage_path"]}" -b:a 64k -ac 1 -ar 16000 -map a "{audio_path}" -y'
    )
    if not os.path.exists(audio_path):
        raise Exception(f"FFmpeg failed to extract audio. stderr: {result.stderr[-500:]}")

    print(f"Audio extracted: {os.path.getsize(audio_path) / 1024:.0f} KB")

    # 3. Transcribe Locally with Faster-Whisper
    print("Transcribing audio locally with Faster-Whisper (small model)...")
    whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
    segments_iter, info = whisper_model.transcribe(audio_path, beam_size=5)

    print(f"Detected language: {info.language} (probability: {info.language_probability:.2f})")

    transcript_text = ""
    for segment in segments_iter:
        transcript_text += f"[{format_time(segment.start)} - {format_time(segment.end)}] {segment.text.strip()}\n"

    print(f"Transcription complete. Length: {len(transcript_text)} chars")

    if not transcript_text.strip():
        raise Exception("Transcription produced empty result — audio may have no speech.")

    # 4. Analyze — AI Clip Extraction OR Full Video Mode
    cursor.execute("UPDATE long_videos SET status = 'analyzing' WHERE id = %s", (VIDEO_ID,))
    db.commit()

    if SETTINGS.get('full_video_mode', False):
        # ─── FULL VIDEO MODE: Skip Groq AI, process entire video ───
        print("🎬 FULL VIDEO MODE — Skipping AI clip extraction.")
        print("   Measuring source video duration with ffprobe...")

        duration_result = run_ffmpeg(
            f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{video["storage_path"]}"'
        )
        try:
            total_seconds = float(duration_result.stdout.strip())
        except (ValueError, AttributeError):
            raise Exception(f"Could not determine video duration via ffprobe. stdout={duration_result.stdout}, stderr={duration_result.stderr}")

        full_end = format_time(total_seconds)
        print(f"   Video duration: {total_seconds:.2f}s ({full_end})")

        # Insert a single clip covering the entire video
        cursor.execute(
            "INSERT INTO video_clips (long_video_id, start_time, end_time, hook_explanation) VALUES (%s, %s, %s, %s)",
            (VIDEO_ID, '00:00:00', full_end, 'Full Video — Subtitles & Rendered Effects')
        )
        db.commit()
        print(f"   Inserted 1 full-video clip entry.")
    else:
        # ─── VIRAL CLIPS MODE: Groq AI hook extraction ───
        print("Analyzing transcript with Groq LLM...")
        clip_count = SETTINGS.get('target_clip_count', 3)
        prompt = f"""Analyze the following video transcript. Find up to {clip_count} highly engaging, self-contained clips suitable for short-form video (TikTok/Shorts). 
Each clip must be between 30 and 60 seconds long.
Use the timestamps from the transcript to determine start and end times.
Return your answer strictly in JSON format exactly matching this structure without any markdown wrappers:
[
  {{"start": "00:01:15", "end": "00:02:00", "reason": "Why this segment is hooky"}}
]

Transcript:
{transcript_text[:8000]}"""

        # Try multiple models in case some are blocked at the project level
        groq_models = [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "llama3-8b-8192",
            "llama3-70b-8192",
            "gemma2-9b-it",
            "mixtral-8x7b-32768",
        ]

        raw_response = None
        last_error = None
        for model_name in groq_models:
            try:
                print(f"  Trying model: {model_name}...")
                chat_completion = client.chat.completions.create(
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a video editor AI. You analyze transcripts and find the most engaging clips. Always respond with valid JSON only, no markdown."
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                    model=model_name,
                    temperature=0.3,
                )
                raw_response = chat_completion.choices[0].message.content
                print(f"  Success with model: {model_name}")
                break
            except Exception as model_err:
                last_error = model_err
                print(f"  Model {model_name} failed: {model_err}")
                continue

        if raw_response is None:
            raise Exception(f"All Groq models failed. Last error: {last_error}. Please enable at least one model at https://console.groq.com/settings/project/limits")

        clean_json = raw_response.replace("```json", "").replace("```", "").strip()
        clips = json.loads(clean_json)

        print(f"Found {len(clips)} viral hook candidates.")

        # 5. Save Timestamps
        for clip in clips:
            cursor.execute(
                "INSERT INTO video_clips (long_video_id, start_time, end_time, hook_explanation) VALUES (%s, %s, %s, %s)",
                (VIDEO_ID, clip['start'], clip['end'], clip['reason'])
            )
        db.commit()

    # 6. Render Clips with Smart Cropping, Effects & Auto-Captions
    cursor.execute("UPDATE long_videos SET status = 'processing' WHERE id = %s", (VIDEO_ID,))
    db.commit()

    cursor.execute("SELECT * FROM video_clips WHERE long_video_id = %s", (VIDEO_ID,))
    saved_clips = cursor.fetchall()

    output_dir = os.path.join(os.path.dirname(__file__), '..', 'storage/app/public')
    output_dir = os.path.abspath(output_dir)
    temp_dir = os.path.join(os.path.dirname(__file__), '..', 'storage/app')
    temp_dir = os.path.abspath(temp_dir)
    os.makedirs(output_dir, exist_ok=True)

    # Get source video info for effect calculations
    src_width, src_height, src_fps = get_video_info(video['storage_path'])
    print(f"Source video: {src_width}x{src_height} @ {src_fps:.1f}fps")

    for sc in saved_clips:
        output_clip = os.path.join(output_dir, f"clip_{sc['id']}.mp4")
        relative_output = f"storage/app/public/clip_{sc['id']}.mp4"
        cursor.execute("UPDATE video_clips SET status = 'rendering' WHERE id = %s", (sc['id'],))
        db.commit()

        # MySQL TIME columns return timedelta objects — convert to float seconds
        clip_start = parse_time_to_seconds(sc['start_time'])
        clip_end = parse_time_to_seconds(sc['end_time'])
        clip_duration = clip_end - clip_start
        clip_start_str = format_seconds_ffmpeg(clip_start)
        clip_end_str = format_seconds_ffmpeg(clip_end)
        clip_duration_str = format_seconds_ffmpeg(clip_duration)

        print(f"\n{'='*60}")
        print(f"  Rendering clip {sc['id']}: {clip_start_str} -> {clip_end_str} ({clip_duration:.2f}s)")
        print(f"  Settings: crop={SETTINGS['smart_crop']}, captions={SETTINGS['auto_captions']}, "
              f"punch_in={SETTINGS['punch_in_zoom']}, ken_burns={SETTINGS['ken_burns']}, "
              f"emoji={SETTINGS['emoji_overlays']}, transitions={SETTINGS['whip_pan_transitions']}, "
              f"bgm={SETTINGS['background_music']}, split={SETTINGS['split_screen']}, "
              f"format={SETTINGS['output_format']}")
        print(f"{'='*60}")

        # ─── Step A: Extract clean intermediate clip ───
        # This is the KEY fix for subtitle/audio desync.
        # By extracting a clean intermediate clip first, we guarantee that:
        #   - audio t=0 == video t=0 == subtitle t=0
        #   - No keyframe seeking issues
        #   - All subsequent filters work on a self-contained clip
        intermediate_clip = os.path.join(temp_dir, f"intermediate_{sc['id']}.mp4")
        print(f"  📦 Extracting intermediate clip...")
        # Use OUTPUT seeking (-ss after -i) for frame-accurate extraction.
        # Input seeking (-ss before -i) is fast but snaps to the nearest keyframe,
        # causing A/V desync that manifests as "delayed subtitles".
        # -avoid_negative_ts make_zero: prevents negative timestamps from confusing
        #   downstream filters and subtitle timing.
        # -async 1: forces the audio stream to start at exactly t=0, guaranteeing
        #   that audio and video are perfectly aligned in the intermediate.
        intermediate_result = run_ffmpeg(
            f'ffmpeg -i "{video["storage_path"]}" -ss {clip_start_str} -t {clip_duration_str} '
            f'-c:v libx264 -preset veryfast -crf 20 -c:a aac -b:a 128k '
            f'-avoid_negative_ts make_zero -async 1 '
            f'"{intermediate_clip}" -y'
        )
        if intermediate_result.returncode != 0 or not os.path.exists(intermediate_clip):
            # Fallback: try input seeking (faster but less precise)
            print(f"  ⚠️ Output seeking failed, trying input seeking fallback...")
            run_ffmpeg(
                f'ffmpeg -ss {clip_start_str} -to {clip_end_str} -i "{video["storage_path"]}" '
                f'-c:v libx264 -preset veryfast -crf 20 -c:a aac -b:a 128k '
                f'-avoid_negative_ts make_zero '
                f'"{intermediate_clip}" -y'
            )

        if not os.path.exists(intermediate_clip):
            print(f"  ❌ Failed to extract intermediate clip, skipping")
            cursor.execute("UPDATE video_clips SET status = 'pending' WHERE id = %s", (sc['id'],))
            db.commit()
            continue

        # Get intermediate clip info (dimensions may differ slightly from source)
        inter_w, inter_h, inter_fps = get_video_info(intermediate_clip)
        print(f"  ✅ Intermediate clip: {inter_w}x{inter_h} @ {inter_fps:.1f}fps")

        # ─── Step A.2: Extract audio from intermediate for transcription ───
        clip_audio = os.path.join(temp_dir, f"clip_audio_{sc['id']}.mp3")
        run_ffmpeg(
            f'ffmpeg -i "{intermediate_clip}" '
            f'-b:a 64k -ac 1 -ar 16000 "{clip_audio}" -y'
        )

        # ─── Step B: Split-Screen OR Smart Crop ───
        # NOTE: Face detection still runs on the ORIGINAL video (needs original timestamps)
        #       but the crop filter will be applied to the intermediate clip.
        crop_filter = None
        split_filter_complex = None
        use_split_screen = False
        render_w = inter_w
        render_h = inter_h

        if SETTINGS['split_screen'] and SETTINGS['output_format'] == '9:16':
            print(f"  👥 Detecting speakers for split-screen...")
            try:
                split_fc, split_w, split_h = get_split_screen_filter(
                    video['storage_path'],
                    start_time=clip_start,
                    duration=clip_duration,
                    output_w=1080, output_h=1920
                )
                if split_fc:
                    split_filter_complex = split_fc
                    use_split_screen = True
                    render_w = split_w
                    render_h = split_h
                    print(f"  ✅ Split-screen ready: {split_w}x{split_h}")
                else:
                    print(f"  ℹ️ Could not detect 2 speakers — falling back to normal crop")
            except Exception as split_err:
                print(f"  ⚠️ Split-screen detection failed: {split_err}, falling back")

        if not use_split_screen and SETTINGS['smart_crop'] and SETTINGS['output_format'] == '9:16':
            print(f"  🎯 Running face detection for smart crop...")
            try:
                crop_filter, crop_w, crop_h = get_smart_crop_filter(
                    video['storage_path'],
                    start_time=clip_start,
                    duration=clip_duration,
                    sample_every_n=5,
                    output_ratio=(9, 16),
                    dynamic=False
                )
                if crop_filter:
                    render_w = crop_w
                    render_h = crop_h
                    print(f"  ✅ Smart crop ready: {crop_w}x{crop_h}")
                else:
                    print(f"  ⚠️ Face tracker returned no filter, using center crop fallback")
                    crop_h_fallback = inter_h
                    crop_w_fallback = int(inter_h * 9 / 16)
                    crop_w_fallback = crop_w_fallback - (crop_w_fallback % 2)
                    crop_x = (inter_w - crop_w_fallback) // 2
                    crop_filter = f"crop={crop_w_fallback}:{crop_h_fallback}:{crop_x}:0"
                    render_w = crop_w_fallback
                    render_h = crop_h_fallback
            except Exception as track_err:
                print(f"  ⚠️ Face tracking failed: {track_err}, using center crop fallback")
                crop_h_fallback = inter_h
                crop_w_fallback = int(inter_h * 9 / 16)
                crop_w_fallback = crop_w_fallback - (crop_w_fallback % 2)
                crop_x = (inter_w - crop_w_fallback) // 2
                crop_filter = f"crop={crop_w_fallback}:{crop_h_fallback}:{crop_x}:0"
                render_w = crop_w_fallback
                render_h = crop_h_fallback

        elif not use_split_screen and SETTINGS['output_format'] == '9:16':
            print(f"  📐 Static center crop to 9:16...")
            crop_h_static = inter_h
            crop_w_static = int(inter_h * 9 / 16)
            crop_w_static = crop_w_static - (crop_w_static % 2)
            crop_x = (inter_w - crop_w_static) // 2
            crop_filter = f"crop={crop_w_static}:{crop_h_static}:{crop_x}:0"
            render_w = crop_w_static
            render_h = crop_h_static

        # ─── Step C: Punch-In Zoom Detection ───
        # Zoom filters are applied AFTER the scale-to-output step in the filter chain,
        # so they need the FINAL output dimensions, not the pre-scale crop dimensions.
        if SETTINGS['output_format'] == '9:16':
            zoom_w, zoom_h = 1080, 1920
        else:
            zoom_w, zoom_h = render_w, render_h

        zoom_filter = None
        if SETTINGS['punch_in_zoom'] and os.path.exists(clip_audio):
            print(f"  🔊 Detecting volume spikes for punch-in zoom...")
            try:
                spikes = detect_volume_spikes(clip_audio, temp_dir=temp_dir)
                if spikes:
                    zoom_filter = generate_punchin_filter(
                        spikes, clip_duration, zoom_w, zoom_h,
                        zoom_factor=1.15, ease_duration=0.3
                    )
                    if zoom_filter:
                        print(f"  ✅ Punch-in zoom ready: {len(spikes)} spike(s)")
                else:
                    print(f"  ℹ️ No significant volume spikes detected")
            except Exception as fx_err:
                print(f"  ⚠️ Punch-in detection failed: {fx_err}")

        # ─── Step D: Ken Burns Slow Zoom ───
        if not zoom_filter and SETTINGS['ken_burns'] and not SETTINGS['punch_in_zoom']:
            print(f"  🎬 Generating Ken Burns slow zoom...")
            try:
                zoom_filter = generate_kenburns_filter(
                    clip_duration, zoom_w, zoom_h,
                    start_zoom=1.0, end_zoom=1.05, fps=inter_fps
                )
                if zoom_filter:
                    print(f"  ✅ Ken Burns ready")
            except Exception as kb_err:
                print(f"  ⚠️ Ken Burns failed: {kb_err}")

        # ─── Step E: Transcribe clip for word-level captions ───
        all_words = []
        ass_path = None
        if SETTINGS['auto_captions'] and os.path.exists(clip_audio):
            print(f"  📝 Transcribing clip with word-level timestamps...")
            clip_segments, _ = whisper_model.transcribe(
                clip_audio, beam_size=5, word_timestamps=True
            )

            for seg in clip_segments:
                if seg.words:
                    for w in seg.words:
                        all_words.append({
                            'word': w.word.strip(),
                            'start': w.start,
                            'end': w.end,
                        })

            print(f"  Found {len(all_words)} words for captions.")

            if all_words:
                words_json_path = os.path.join(temp_dir, f"clip_{sc['id']}_words.json")
                with open(words_json_path, 'w', encoding='utf-8') as f:
                    json.dump(all_words, f, ensure_ascii=False, indent=2)
                print(f"  💾 Saved transcript JSON for editor: {words_json_path}")

                if SETTINGS['output_format'] == '9:16':
                    sub_w = 1080
                    sub_h = 1920
                else:
                    sub_w = render_w
                    sub_h = render_h

                ass_path = os.path.join(temp_dir, f"clip_{sc['id']}.ass")
                num_events = generate_ass_subtitles(
                    all_words, ass_path, sub_w, sub_h,
                    style_preset=SETTINGS.get('caption_style', 'yellow_pop'),
                    font_family=SETTINGS.get('caption_font', 'Arial Black'),
                    position=SETTINGS.get('caption_position', 'bottom'),
                    layout_mode=SETTINGS.get('caption_layout', 'two_line')
                )
                print(f"  Generated {num_events} caption events (style={SETTINGS.get('caption_style', 'yellow_pop')}, font={SETTINGS.get('caption_font', 'Arial Black')}, pos={SETTINGS.get('caption_position', 'bottom')}, layout={SETTINGS.get('caption_layout', 'two_line')}).")

        # ─── Step E.5: Emoji Overlay ───
        emoji_overlay_data = None
        if SETTINGS['emoji_overlays'] and all_words:
            print(f"  😄 Scanning transcript for emoji triggers...")
            try:
                emoji_events = scan_transcript_for_emojis(all_words)
                if emoji_events:
                    emoji_temp = os.path.join(temp_dir, f'emoji_{sc["id"]}')
                    if SETTINGS['output_format'] == '9:16':
                        emoji_overlay_data = generate_emoji_overlay_data(
                            emoji_events, 1080, 1920, temp_dir=emoji_temp
                        )
                    else:
                        emoji_overlay_data = generate_emoji_overlay_data(
                            emoji_events, render_w, render_h, temp_dir=emoji_temp
                        )
                    if emoji_overlay_data:
                        print(f"  ✅ Emoji overlay ready: {len(emoji_events)} emoji(s), "
                              f"{len(emoji_overlay_data['input_files'])} PNG(s)")
                    else:
                        print(f"  ⚠️ Emoji PNG rendering failed, skipping emoji overlays")
                else:
                    print(f"  ℹ️ No emoji-triggering keywords found in transcript")
            except Exception as emoji_err:
                print(f"  ⚠️ Emoji overlay failed: {emoji_err}")

        # ─── Step F: Build composite FFmpeg filter chain ───
        filters = []

        if use_split_screen:
            # Split-screen mode uses filter_complex — handled separately below
            pass
        else:
            # 1. Crop (face tracking or static)
            if crop_filter:
                filters.append(crop_filter)

            # 2. Scale to final output resolution
            if SETTINGS['output_format'] == '9:16':
                filters.append("scale=1080:1920:force_original_aspect_ratio=decrease")
                filters.append("pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black")

        # 3. Zoom effects (scale+crop, preserves framerate — no more zoompan)
        if zoom_filter:
            filters.append(zoom_filter)

        # 4. Captions (always last so they render on top)
        if ass_path and os.path.exists(ass_path):
            ass_ffmpeg = ffmpeg_escape_path(ass_path)
            filters.append(f"ass='{ass_ffmpeg}'")

        # ─── Step G: Render with FFmpeg ───
        # All rendering now uses the INTERMEDIATE clip as input.
        # Since the intermediate is already trimmed to [t=0, duration],
        # there's no -ss/-t needed — audio and video are perfectly aligned.

        if use_split_screen:
            # ── Split-screen render ──
            # NOTE: split-screen needs the ORIGINAL video for correct crop coordinates,
            # so we still use the source with -ss/-t here.
            extra_vf = []
            if ass_path and os.path.exists(ass_path):
                ass_ffmpeg = ffmpeg_escape_path(ass_path)
                extra_vf.append(f"ass='{ass_ffmpeg}'")

            if extra_vf:
                extra_chain = ",".join(extra_vf)
                full_fc = split_filter_complex.replace('[outv]',
                    f'[_splitraw];[_splitraw]{extra_chain}[outv]')
            else:
                full_fc = split_filter_complex

            # Use intermediate clip — its audio is already time-aligned at t=0
            ffmpeg_cmd = (
                f'ffmpeg -i "{intermediate_clip}" '
                f'-filter_complex "{full_fc}" '
                f'-map "[outv]" -map 0:a '
                f'-c:v libx264 -preset medium -crf 22 '
                f'-profile:v high -level 4.0 -pix_fmt yuv420p '
                f'-c:a aac -b:a 128k -movflags +faststart '
                f'"{output_clip}" -y'
            )
            print(f"  🎬 Encoding split-screen...")
            encode_result = run_ffmpeg(ffmpeg_cmd)

            if encode_result.returncode != 0:
                print(f"  ⚠️ Split-screen encode failed, falling back to normal crop")
                print(f"  Error: {encode_result.stderr[-300:]}")
                use_split_screen = False
                crop_h_fb = inter_h
                crop_w_fb = int(inter_h * 9 / 16)
                crop_w_fb = crop_w_fb - (crop_w_fb % 2)
                crop_x_fb = (inter_w - crop_w_fb) // 2
                fb_vf = f"crop={crop_w_fb}:{crop_h_fb}:{crop_x_fb}:0,scale=1080:1920"
                run_ffmpeg(
                    f'ffmpeg -i "{intermediate_clip}" '
                    f'-vf "{fb_vf}" '
                    f'-c:v libx264 -preset medium -crf 22 '
                    f'-profile:v high -level 4.0 -pix_fmt yuv420p '
                    f'-c:a aac -b:a 128k -movflags +faststart '
                    f'"{output_clip}" -y'
                )

        elif emoji_overlay_data:
            # ── Emoji overlay requires filter_complex (multiple inputs) ──
            # IMPORTANT: The ASS subtitle filter must be separated from `filters`
            # and applied AFTER emoji overlays for two reasons:
            # 1. The ass= filter's quoted path causes quoting conflicts inside
            #    -filter_complex "..." strings, breaking the video stream silently
            # 2. Captions should render ON TOP of emoji overlays visually

            # Separate ASS filter from other video filters
            non_ass_filters = [f for f in filters if not f.startswith("ass=")]
            ass_filter = next((f for f in filters if f.startswith("ass=")), None)

            vf_chain = ",".join(non_ass_filters) if non_ass_filters else "null"

            emoji_inputs = ""
            for png_path in emoji_overlay_data['input_files']:
                emoji_inputs += f' -i "{png_path}"'

            fc_parts = []
            fc_parts.append(f"[0:v]{vf_chain}[vemoji_in]")
            fc_parts.extend(emoji_overlay_data['filter_parts'])

            # Apply ASS subtitles AFTER emoji overlays (renders on top)
            final_label = emoji_overlay_data['final_label']
            if ass_filter:
                fc_parts.append(f"[{final_label}]{ass_filter}[vfinal]")
                final_label = "vfinal"

            filter_complex = ";".join(fc_parts)

            # Use intermediate clip — no -ss/-t needed, timing starts at t=0
            ffmpeg_cmd = (
                f'ffmpeg -i "{intermediate_clip}"'
                f'{emoji_inputs} '
                f'-filter_complex "{filter_complex}" '
                f'-map "[{final_label}]" -map 0:a '
                f'-c:v libx264 -preset medium -crf 22 '
                f'-profile:v high -level 4.0 -pix_fmt yuv420p '
                f'-c:a aac -b:a 128k -movflags +faststart '
                f'"{output_clip}" -y'
            )
            print(f"  🎬 Encoding with effects + emoji overlays...")
            print(f"  Video filters: {vf_chain[:150]}...")
            print(f"  Emoji inputs: {len(emoji_overlay_data['input_files'])}")
            encode_result = run_ffmpeg(ffmpeg_cmd)

            if encode_result.returncode != 0:
                print(f"  ⚠️ FFmpeg encode with emoji overlays failed, trying without emoji...")
                print(f"  Error: {encode_result.stderr[-300:]}")
                if filters:
                    vf_string = ",".join(filters)
                    ffmpeg_fallback = (
                        f'ffmpeg -i "{intermediate_clip}" '
                        f'-vf "{vf_string}" '
                        f'-c:v libx264 -preset medium -crf 22 '
                        f'-profile:v high -level 4.0 -pix_fmt yuv420p '
                        f'-c:a aac -b:a 128k -movflags +faststart '
                        f'"{output_clip}" -y'
                    )
                    encode_result = run_ffmpeg(ffmpeg_fallback)

            if encode_result.returncode != 0:
                print(f"  ⚠️ All filter attempts failed, falling back to plain encode.")
                print(f"  Error: {encode_result.stderr[-300:]}")
                run_ffmpeg(
                    f'ffmpeg -i "{intermediate_clip}" '
                    f'-c:v libx264 -preset medium -crf 22 '
                    f'-profile:v high -level 4.0 -pix_fmt yuv420p '
                    f'-c:a aac -b:a 128k -movflags +faststart '
                    f'"{output_clip}" -y'
                )

        elif filters:
            vf_string = ",".join(filters)
            ffmpeg_cmd = (
                f'ffmpeg -i "{intermediate_clip}" '
                f'-vf "{vf_string}" '
                f'-c:v libx264 -preset medium -crf 22 '
                f'-profile:v high -level 4.0 -pix_fmt yuv420p '
                f'-c:a aac -b:a 128k -movflags +faststart '
                f'"{output_clip}" -y'
            )
            print(f"  🎬 Encoding with effects...")
            print(f"  Filter chain: {vf_string[:150]}...")
            encode_result = run_ffmpeg(ffmpeg_cmd)

            if encode_result.returncode != 0:
                print(f"  ⚠️ FFmpeg encode with effects failed, trying simpler filter...")
                print(f"  Error: {encode_result.stderr[-300:]}")

                simple_filters = [f for f in filters if not f.startswith("ass=")]
                if simple_filters:
                    vf_simple = ",".join(simple_filters)
                    ffmpeg_fallback = (
                        f'ffmpeg -i "{intermediate_clip}" '
                        f'-vf "{vf_simple}" '
                        f'-c:v libx264 -preset medium -crf 22 '
                        f'-profile:v high -level 4.0 -pix_fmt yuv420p '
                        f'-c:a aac -b:a 128k -movflags +faststart '
                        f'"{output_clip}" -y'
                    )
                    encode_result = run_ffmpeg(ffmpeg_fallback)

            if encode_result.returncode != 0:
                print(f"  ⚠️ All filter attempts failed, falling back to plain encode.")
                print(f"  Error: {encode_result.stderr[-300:]}")
                run_ffmpeg(
                    f'ffmpeg -i "{intermediate_clip}" '
                    f'-c:v libx264 -preset medium -crf 22 '
                    f'-profile:v high -level 4.0 -pix_fmt yuv420p '
                    f'-c:a aac -b:a 128k -movflags +faststart '
                    f'"{output_clip}" -y'
                )
        else:
            # No effects at all — encode the intermediate clip
            print(f"  📋 No effects enabled, simple encode...")
            run_ffmpeg(
                f'ffmpeg -i "{intermediate_clip}" '
                f'-c:v libx264 -preset medium -crf 22 '
                f'-profile:v high -level 4.0 -pix_fmt yuv420p '
                f'-c:a aac -b:a 128k -movflags +faststart '
                f'"{output_clip}" -y'
            )

        # ─── Step G.5: Whip-Pan Transitions (post-processing) ───
        if SETTINGS['whip_pan_transitions'] and os.path.exists(output_clip):
            print(f"  🌀 Applying whip-pan transitions...")
            try:
                transition_output = os.path.join(temp_dir, f"clip_{sc['id']}_transitions.mp4")
                t_duration = float(SETTINGS.get('transition_speed', 0.25))
                success = apply_whip_pan_transitions(
                    output_clip, transition_output,
                    transition_duration=t_duration,
                    auto_detect=True,
                    scene_threshold=0.3
                )
                if success and os.path.exists(transition_output):
                    os.replace(transition_output, output_clip)
                    print(f"  ✅ Whip-pan transitions applied")
                elif os.path.exists(transition_output):
                    os.remove(transition_output)
            except Exception as trans_err:
                print(f"  ⚠️ Whip-pan transitions failed: {trans_err}")
                transition_output = os.path.join(temp_dir, f"clip_{sc['id']}_transitions.mp4")
                if os.path.exists(transition_output):
                    os.remove(transition_output)

        # ─── Step G.6: Background Music Mixing (post-processing) ───
        if SETTINGS['background_music'] and SETTINGS.get('bgm_path') and os.path.exists(output_clip):
            bgm_path = SETTINGS['bgm_path']
            if os.path.exists(bgm_path):
                print(f"  🎵 Mixing background music with auto-ducking...")
                try:
                    speech_regions = []
                    if os.path.exists(clip_audio):
                        speech_regions = detect_speech_regions(clip_audio, temp_dir=temp_dir)
                    elif all_words:
                        speech_regions = []
                        if all_words:
                            current_start = all_words[0]['start']
                            current_end = all_words[0]['end']
                            for w in all_words[1:]:
                                if w['start'] - current_end < 0.5:
                                    current_end = w['end']
                                else:
                                    speech_regions.append({'start': current_start, 'end': current_end})
                                    current_start = w['start']
                                    current_end = w['end']
                            speech_regions.append({'start': current_start, 'end': current_end})

                    bgm_output = os.path.join(temp_dir, f"clip_{sc['id']}_bgm.mp4")
                    success = mix_background_music(
                        output_clip, bgm_path, bgm_output,
                        speech_regions, clip_duration,
                        music_volume=0.40, duck_volume=0.12
                    )
                    if success and os.path.exists(bgm_output):
                        os.replace(bgm_output, output_clip)
                        print(f"  ✅ Background music mixed")
                    elif os.path.exists(bgm_output):
                        os.remove(bgm_output)
                except Exception as bgm_err:
                    print(f"  ⚠️ Background music mixing failed: {bgm_err}")
                    bgm_output = os.path.join(temp_dir, f"clip_{sc['id']}_bgm.mp4")
                    if os.path.exists(bgm_output):
                        os.remove(bgm_output)
            else:
                print(f"  ⚠️ Background music file not found: {bgm_path}")

        # ─── Cleanup temp files ───
        if ass_path and os.path.exists(ass_path):
            os.remove(ass_path)
        if os.path.exists(clip_audio):
            os.remove(clip_audio)
        if os.path.exists(intermediate_clip):
            os.remove(intermediate_clip)
        emoji_temp = os.path.join(temp_dir, f'emoji_{sc["id"]}')
        if os.path.isdir(emoji_temp):
            import shutil
            shutil.rmtree(emoji_temp, ignore_errors=True)

        cursor.execute("UPDATE video_clips SET output_path = %s, status = 'ready' WHERE id = %s", (relative_output, sc['id']))
        db.commit()
        print(f"  ✅ Clip {sc['id']} ready!")

    cursor.execute("UPDATE long_videos SET status = 'completed' WHERE id = %s", (VIDEO_ID,))
    db.commit()
    print("\n🎉 Pipeline completed successfully!")

except Exception as e:
    print(f"Pipeline failed: {e}")
    try:
        cursor.execute("UPDATE long_videos SET status = 'failed' WHERE id = %s", (VIDEO_ID,))
        db.commit()
    except Exception:
        pass
finally:
    # Cleanup temp audio
    if 'audio_path' in locals() and os.path.exists(audio_path):
        os.remove(audio_path)
    try:
        db.close()
    except Exception:
        pass

print("Pipeline process finished.")
