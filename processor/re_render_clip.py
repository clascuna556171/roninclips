"""
RoninClips — Fast In-Browser Transcript Re-renderer
Reads updated word JSON, generates a fresh ASS subtitle script,
and burns it directly onto the existing intermediate clip.
Supports SQLite & MySQL via db_helper and GPU hardware encoding via hw_accel.
"""

import sys
import os
import re
import subprocess
import json
from dotenv import load_dotenv

if sys.platform == 'win32':
    os.environ['PYTHONUTF8'] = '1'
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(__file__))
from db_helper import get_db, DatabaseUnavailable
from hw_accel import detect_ffmpeg_encoder
from subtitles import generate_ass_subtitles, format_ass_time, ffmpeg_escape_path, caption_xy, settings_caption_xy

CLIP_ID = sys.argv[1] if len(sys.argv) > 1 else None
# `--preview-frame`: write one caption-free frame of the rendered layout (clip_<id>_preview.jpg) for the
# caption editor, then exit without re-rendering.
PREVIEW_FRAME = '--preview-frame' in sys.argv[2:]
CLI_ARGS = [a for a in sys.argv[2:] if a != '--preview-frame']


def resolve_caption(settings, clip_caption, gaming, cli_position=None):
    """(style, position preset, pos_xy) for this clip.
    Saved per-clip choices (`crop_coordinates_json.caption`) win over the job settings;
    the gaming layout keeps bottom captions unless the clip has its own position."""
    clip_caption = clip_caption if isinstance(clip_caption, dict) else {}
    style = clip_caption.get('style') or settings.get('caption_style', 'yellow_pop')
    clip_xy = caption_xy((clip_caption.get('x'), clip_caption.get('y')))
    if clip_xy:
        return style, 'bottom', clip_xy
    if clip_caption.get('position'):
        return style, clip_caption['position'], None
    if cli_position:
        return style, cli_position, None
    if gaming:
        return style, 'bottom', None
    return style, settings.get('caption_position', 'bottom'), settings_caption_xy(settings)

def run_ffmpeg(cmd, **kwargs):
    kwargs.setdefault('shell', isinstance(cmd, str))
    kwargs.setdefault('capture_output', True)
    kwargs.pop('text', None)
    return subprocess.run(cmd, encoding='utf-8', errors='replace', **kwargs)

if __name__ == "__main__":
    if not CLIP_ID:
        sys.exit(0)

    try:
        db = get_db()
    except DatabaseUnavailable as db_err:
        print(f"DATABASE ERROR: {db_err}")
        sys.exit(1)
    cursor = db.cursor()

    cursor.execute("SELECT * FROM video_clips WHERE id = %s", (CLIP_ID,))
    clip = cursor.fetchone()
    if not clip:
        db.close()
        sys.exit(1)
        
    cursor.execute("SELECT * FROM long_videos WHERE id = %s", (clip['long_video_id'],))
    video = cursor.fetchone()
    
    SETTINGS = {
        'output_format': '9:16', 'caption_style': 'yellow_pop', 'caption_font': 'Arial Black',
        'caption_position': 'bottom', 'caption_layout': 'two_line', 'smart_crop': True,
        'hardware_accel': 'auto'
    }
    if video and video.get('processing_settings'):
        try:
            db_settings = json.loads(video['processing_settings'])
            SETTINGS.update(db_settings)
        except Exception:
            pass

    # CLI style & position overrides if specified
    CLI_STYLE = CLI_ARGS[0].strip() if len(CLI_ARGS) > 0 and CLI_ARGS[0].strip() else None
    CLI_POSITION = CLI_ARGS[1].strip() if len(CLI_ARGS) > 1 and CLI_ARGS[1].strip() else None
            
    temp_dir = os.path.join(os.path.dirname(__file__), '..', 'storage/app')
    output_dir = os.path.join(temp_dir, 'public')
    words_json_path = os.path.join(temp_dir, f"clip_{CLIP_ID}_words.json")
    intermediate_clip = os.path.join(temp_dir, f"intermediate_{CLIP_ID}.mp4")
    ass_path = os.path.join(temp_dir, f"clip_{CLIP_ID}.ass")
    output_clip = os.path.join(output_dir, f"clip_{CLIP_ID}.mp4")

    # If intermediate clip does not exist, recreate it from source video
    if not os.path.exists(intermediate_clip) and video and os.path.exists(video.get('storage_path', '')):
        start_val = str(clip.get('start_time', '00:00:00'))
        end_val = str(clip.get('end_time', '00:00:30'))
        run_ffmpeg([
            'ffmpeg', '-i', video['storage_path'], '-ss', start_val, '-to', end_val,
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-c:a', 'aac', '-b:a', '128k',
            '-avoid_negative_ts', 'make_zero', intermediate_clip, '-y'
        ])

    # Check if crop metadata, split screen or gaming layout was saved during initial processing
    crop_info = None
    if clip.get('crop_coordinates_json'):
        try:
            crop_info = json.loads(clip['crop_coordinates_json'])
        except Exception:
            crop_info = None
    gaming_info = crop_info.get('gaming_layout') if crop_info else None

    # Captions are optional: a facecam adjustment re-renders clips that have none
    all_words = None
    try:
        with open(words_json_path, 'r', encoding='utf-8') as f:
            all_words = json.load(f)
    except FileNotFoundError:
        print(f"  ℹ️ [Clip #{CLIP_ID}] No transcript words saved, rendering without captions")

    render_w = 1080 if SETTINGS['output_format'] == '9:16' else 1920
    render_h = 1920 if SETTINGS['output_format'] == '9:16' else 1080

    caption_style, caption_position, caption_pos_xy = resolve_caption(
        SETTINGS, crop_info.get('caption') if crop_info else None, bool(gaming_info), CLI_POSITION)
    if CLI_STYLE:
        caption_style = CLI_STYLE

    if PREVIEW_FRAME:
        all_words = None  # the editor draws the caption itself
        if os.path.exists(ass_path):
            os.remove(ass_path)

    if all_words:
        generate_ass_subtitles(
            all_words, ass_path, render_w, render_h,
            style_preset=caption_style,
            font_family=SETTINGS.get('caption_font', 'Arial Black'),
            position=caption_position,
            layout_mode=SETTINGS.get('caption_layout', 'two_line'),
            mask_swears=bool(SETTINGS.get('clean_captions')),
            pos_xy=caption_pos_xy
        )

    use_split_screen = crop_info.get('use_split_screen', False) if crop_info else False
    saved_crop_filter = crop_info.get('crop_filter') if crop_info else None
    saved_zoom_filter = crop_info.get('zoom_filter') if crop_info else None
    saved_split_fc = crop_info.get('split_filter_complex') if crop_info else None

    filters = []
    probe = run_ffmpeg([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height', '-of', 'csv=s=x:p=0', intermediate_clip
    ])
    try:
        w, h = map(int, probe.stdout.strip().split('x'))
    except Exception:
        w, h = 1920, 1080

    _, encoder_flags = detect_ffmpeg_encoder(preferred_accel=SETTINGS.get('hardware_accel', 'auto'))
    enc_args = encoder_flags.split() if encoder_flags else ['-c:v', 'libx264', '-preset', 'fast', '-crf', '22']
    if gaming_info:
        # Rebuild the gaming layout from the (possibly user-adjusted) facecam box
        from gaming_layout import build_gaming_filter
        use_split_screen = True
        saved_zoom_filter = None
        saved_split_fc = build_gaming_filter(
            int(gaming_info.get('input_w') or w),
            int(gaming_info.get('input_h') or h),
            gaming_info.get('cam_box')
        )

    if PREVIEW_FRAME:
        # Output seeking (after -i) so time-based crop/zoom expressions see the real time
        dur = run_ffmpeg(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                          '-of', 'default=noprint_wrappers=1:nokey=1', intermediate_clip])
        try:
            seek = min(float(dur.stdout.strip()) * 0.4, 8.0)
        except ValueError:
            seek = 1.0
        preview_path = os.path.join(output_dir, f"clip_{CLIP_ID}_preview.jpg")
        if os.path.exists(preview_path):
            os.remove(preview_path)
        out_args = ['-ss', f"{seek:.2f}", '-frames:v', '1', '-q:v', '3', '-an', '-y', preview_path]
    else:
        out_args = enc_args + ['-c:a', 'copy', '-y', output_clip]

    if use_split_screen and saved_split_fc:
        # Re-apply saved split-screen / gaming complex filter with updated subtitles
        extra_vf = []
        if saved_zoom_filter:
            extra_vf.append(saved_zoom_filter)
        if os.path.exists(ass_path):
            ass_ffmpeg = ffmpeg_escape_path(ass_path)
            extra_vf.append(f"ass='{ass_ffmpeg}'")
        full_fc = saved_split_fc
        if extra_vf:
            extra_chain = ",".join(extra_vf)
            full_fc = saved_split_fc.replace('[outv]', f'[_splitraw];[_splitraw]{extra_chain}[outv]')
        
        maps = ['-map', '[outv]'] + ([] if PREVIEW_FRAME else ['-map', '0:a'])
        run_ffmpeg(['ffmpeg', '-i', intermediate_clip, '-filter_complex', full_fc] + maps + out_args)
    else:
        if saved_crop_filter:
            # Re-use exact face tracking crop
            filters.append(saved_crop_filter)
            if SETTINGS['output_format'] == '9:16':
                filters.append("scale=1080:1920:force_original_aspect_ratio=decrease")
                filters.append("pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black")
        elif SETTINGS['output_format'] == '9:16':
            # Fallback to center crop if no saved face tracking filter
            crop_h = h
            crop_w = int(h * 9 / 16)
            crop_w = crop_w - (crop_w % 2)
            crop_x = (w - crop_w) // 2
            filters.append(f"crop={crop_w}:{crop_h}:{crop_x}:0")
            filters.append("scale=1080:1920:force_original_aspect_ratio=decrease")
            filters.append("pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black")
            
        if saved_zoom_filter:
            filters.append(saved_zoom_filter)

        if os.path.exists(ass_path):
            ass_ffmpeg = ffmpeg_escape_path(ass_path)
            filters.append(f"ass='{ass_ffmpeg}'")
            
        vf = ",".join(filters) if filters else "null"
        
        run_ffmpeg(['ffmpeg', '-i', intermediate_clip, '-vf', vf] + out_args)

    if PREVIEW_FRAME:
        db.close()
        ok = os.path.exists(preview_path)
        print(f"Preview frame {'written' if ok else 'FAILED'} for clip {CLIP_ID}")
        sys.exit(0 if ok else 1)

    # Re-apply Background Music with Auto-Ducking if enabled in video settings
    if SETTINGS.get('background_music') and SETTINGS.get('bgm_path') and os.path.exists(output_clip):
        bgm_path = SETTINGS['bgm_path']
        if os.path.exists(bgm_path):
            try:
                from audio_mixer import detect_speech_regions, mix_background_music
                print(f"  🎵 [Clip #{CLIP_ID}] Re-mixing background music with auto-ducking...")
                temp_audio = os.path.join(temp_dir, f"clip_{CLIP_ID}_rerender_audio.wav")
                run_ffmpeg(['ffmpeg', '-i', intermediate_clip, '-vn', '-ac', '1', '-ar', '16000', temp_audio, '-y'])
                speech_regions = []
                if os.path.exists(temp_audio):
                    speech_regions = detect_speech_regions(temp_audio, temp_dir=temp_dir)

                clip_dur = 30.0
                dur_res = run_ffmpeg([
                    'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                    '-of', 'default=noprint_wrappers=1:nokey=1', output_clip
                ])
                try:
                    clip_dur = float(dur_res.stdout.strip())
                except Exception:
                    pass

                bgm_output = os.path.join(temp_dir, f"clip_{CLIP_ID}_bgm.mp4")
                success = mix_background_music(
                    output_clip, bgm_path, bgm_output,
                    speech_regions, clip_dur,
                    music_volume=0.40, duck_volume=0.12
                )
                if success and os.path.exists(bgm_output):
                    os.replace(bgm_output, output_clip)
                    print(f"  ✅ [Clip #{CLIP_ID}] Background music re-mixed")
                elif os.path.exists(bgm_output):
                    os.remove(bgm_output)

                if os.path.exists(temp_audio):
                    os.remove(temp_audio)
            except Exception as bgm_err:
                print(f"  ⚠️ [Clip #{CLIP_ID}] BGM re-mix error: {bgm_err}")

    # Loudness (-14 LUFS): the intermediate clip is not normalised, so redo it after every re-render
    if SETTINGS.get('loudness_normalize', True) and os.path.exists(output_clip):
        try:
            from audio_mixer import normalize_loudness
            normalize_loudness(output_clip, temp_dir)
        except Exception as loud_err:
            print(f"  ⚠️ [Clip #{CLIP_ID}] Loudness error: {loud_err}")

    if os.path.exists(ass_path):
        try:
            os.remove(ass_path)
        except Exception:
            pass

    cursor.execute("UPDATE video_clips SET status = 'ready', updated_at = CURRENT_TIMESTAMP WHERE id = %s", (CLIP_ID,))
    db.commit()
    db.close()
    print(f"Re-render completed for clip {CLIP_ID}")
