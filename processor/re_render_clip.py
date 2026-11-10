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
from db_helper import get_db
from hw_accel import detect_ffmpeg_encoder
from subtitles import generate_ass_subtitles, format_ass_time, ffmpeg_escape_path

CLIP_ID = sys.argv[1] if len(sys.argv) > 1 else None

def run_ffmpeg(cmd, **kwargs):
    kwargs.setdefault('shell', isinstance(cmd, str))
    kwargs.setdefault('capture_output', True)
    kwargs.pop('text', None)
    return subprocess.run(cmd, encoding='utf-8', errors='replace', **kwargs)

if __name__ == "__main__":
    if not CLIP_ID:
        sys.exit(0)

    db = get_db()
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
    if len(sys.argv) > 2 and sys.argv[2].strip():
        SETTINGS['caption_style'] = sys.argv[2].strip()
    if len(sys.argv) > 3 and sys.argv[3].strip():
        SETTINGS['caption_position'] = sys.argv[3].strip()
            
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

    try:
        with open(words_json_path, 'r', encoding='utf-8') as f:
            all_words = json.load(f)
    except FileNotFoundError:
        cursor.execute("UPDATE video_clips SET status = 'ready' WHERE id = %s", (CLIP_ID,))
        db.commit()
        db.close()
        sys.exit(1)
        
    render_w = 1080 if SETTINGS['output_format'] == '9:16' else 1920
    render_h = 1920 if SETTINGS['output_format'] == '9:16' else 1080
    
    generate_ass_subtitles(
        all_words, ass_path, render_w, render_h,
        style_preset=SETTINGS.get('caption_style', 'yellow_pop'),
        font_family=SETTINGS.get('caption_font', 'Arial Black'),
        position=SETTINGS.get('caption_position', 'bottom'),
        layout_mode=SETTINGS.get('caption_layout', 'two_line')
    )
    
    # Check if crop metadata or split screen was saved during initial processing
    crop_info = None
    if clip.get('crop_coordinates_json'):
        try:
            crop_info = json.loads(clip['crop_coordinates_json'])
        except Exception:
            crop_info = None

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
        if use_split_screen and saved_split_fc:
            # Re-apply saved split-screen complex filter with updated subtitles
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
            
            run_ffmpeg([
                'ffmpeg', '-i', intermediate_clip, '-filter_complex', full_fc,
                '-map', '[outv]', '-map', '0:a'
            ] + enc_args + ['-c:a', 'copy', '-y', output_clip])
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
            
            run_ffmpeg([
                'ffmpeg', '-i', intermediate_clip, '-vf', vf
            ] + enc_args + ['-c:a', 'copy', '-y', output_clip])

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
    
    if os.path.exists(ass_path):
        try:
            os.remove(ass_path)
        except Exception:
            pass

    cursor.execute("UPDATE video_clips SET status = 'ready', updated_at = CURRENT_TIMESTAMP WHERE id = %s", (CLIP_ID,))
    db.commit()
    db.close()
    print(f"Re-render completed for clip {CLIP_ID}")
