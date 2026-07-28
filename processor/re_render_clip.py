import sys
import os
import subprocess
import mysql.connector
import json
from dotenv import load_dotenv

if sys.platform == 'win32':
    os.environ['PYTHONUTF8'] = '1'
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

CLIP_ID = sys.argv[1]

db = mysql.connector.connect(
    host=os.environ.get("DB_HOST", "127.0.0.1"),
    user=os.environ.get("DB_USERNAME", "root"),
    password=os.environ.get("DB_PASSWORD", ""),
    database=os.environ.get("DB_DATABASE", "roninclips"),
    port=int(os.environ.get("DB_PORT", 3306))
)
cursor = db.cursor(dictionary=True)

def run_ffmpeg(cmd, **kwargs):
    kwargs.setdefault('shell', True)
    kwargs.setdefault('capture_output', True)
    kwargs.pop('text', None)
    return subprocess.run(cmd, encoding='utf-8', errors='replace', **kwargs)

def format_ass_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"

def ffmpeg_escape_path(path):
    p = path.replace('\\', '/')
    p = p.replace(':', '\\:')
    return p

def generate_ass_subtitles(words, output_path, output_w=1080, output_h=1920,
                            style_preset='yellow_pop', font_family='Arial Black',
                            position='bottom', layout_mode='two_line'):
    PALETTES = {
        'yellow_pop': { 'active_color': '\\c&H00FFFF&', 'inactive_color': '\\c&HFFFFFF&', 'outline_size': 4, 'shadow_size': 2 },
        'neon_cyan': { 'active_color': '\\c&HFFFF00&', 'inactive_color': '\\c&HEEEEEE&', 'outline_size': 4, 'shadow_size': 2 },
        'bold_white': { 'active_color': '\\c&H00FF00&', 'inactive_color': '\\c&HFFFFFF&', 'outline_size': 5, 'shadow_size': 3 },
    }
    style_cfg = PALETTES.get(style_preset, PALETTES['yellow_pop'])

    if layout_mode == 'single_word':
        chunk_size = 1; font_size = max(60, int(output_h / 18))
    elif layout_mode == 'full_line':
        chunk_size = 7; font_size = max(40, int(output_h / 28))
    else:
        chunk_size = 4; font_size = max(48, int(output_h / 24))

    pos = str(position).lower()
    if pos == 'top': alignment = 8; margin_v = int(output_h * 0.10)
    elif pos == 'center': alignment = 5; margin_v = 0
    else: alignment = 2; margin_v = int(output_h * 0.14)

    outline_val = style_cfg['outline_size']; shadow_val = style_cfg['shadow_size']
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
    chunks = [words[i:i + chunk_size] for i in range(0, len(words), chunk_size)]
    events = []
    for chunk in chunks:
        chunk_end = chunk[-1]['end']
        for i, current_word in enumerate(chunk):
            event_start = current_word['start']
            event_end = chunk[i + 1]['start'] if i < len(chunk) - 1 else chunk_end
            if event_end - event_start < 0.05: event_end = event_start + 0.15
            
            parts = []
            for j, w in enumerate(chunk):
                word_text = w['word'].strip().upper()
                if not word_text: continue
                line_prefix = "\\N " if (layout_mode == 'two_line' and j == 2) else ""
                if j == i:
                    parts.append(f"{line_prefix}{{{style_cfg['active_color']}\\fscx115\\fscy115}}{word_text}{{{style_cfg['inactive_color']}\\fscx100\\fscy100}}")
                else:
                    parts.append(line_prefix + word_text)
            
            text = " ".join(parts)
            if text.strip():
                start_str, end_str = format_ass_time(event_start), format_ass_time(event_end)
                events.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{text}")

    with open(output_path, 'w', encoding='utf-8-sig') as f:
        f.write(ass_header + '\n'.join(events) + '\n')
    return len(events)

if __name__ == "__main__":
    cursor.execute("SELECT * FROM video_clips WHERE id = %s", (CLIP_ID,))
    clip = cursor.fetchone()
    if not clip:
        sys.exit(1)
        
    cursor.execute("SELECT * FROM long_videos WHERE id = %s", (clip['long_video_id'],))
    video = cursor.fetchone()
    
    SETTINGS = {
        'output_format': '9:16', 'caption_style': 'yellow_pop', 'caption_font': 'Arial Black',
        'caption_position': 'bottom', 'caption_layout': 'two_line', 'smart_crop': True
    }
    if video and video.get('processing_settings'):
        try:
            db_settings = json.loads(video['processing_settings'])
            SETTINGS.update(db_settings)
        except:
            pass
            
    temp_dir = os.path.join(os.path.dirname(__file__), '..', 'storage/app')
    output_dir = os.path.join(temp_dir, 'public')
    words_json_path = os.path.join(temp_dir, f"clip_{CLIP_ID}_words.json")
    intermediate_clip = os.path.join(temp_dir, f"intermediate_{CLIP_ID}.mp4")
    ass_path = os.path.join(temp_dir, f"clip_{CLIP_ID}.ass")
    output_clip = os.path.join(output_dir, f"clip_{CLIP_ID}.mp4")

    try:
        with open(words_json_path, 'r', encoding='utf-8') as f:
            all_words = json.load(f)
    except FileNotFoundError:
        cursor.execute("UPDATE video_clips SET status = 'ready' WHERE id = %s", (CLIP_ID,))
        db.commit()
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
    
    filters = []
    
    # We will just do a static center crop for the re-render for simplicity 
    # instead of re-running the face tracker.
    # To do this correctly, we get intermediate clip dimensions
    probe = run_ffmpeg(f'ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 "{intermediate_clip}"')
    try:
        w, h = map(int, probe.stdout.strip().split('x'))
    except:
        w, h = 1920, 1080

    if SETTINGS['output_format'] == '9:16':
        crop_h = h
        crop_w = int(h * 9 / 16)
        crop_w = crop_w - (crop_w % 2)
        crop_x = (w - crop_w) // 2
        filters.append(f"crop={crop_w}:{crop_h}:{crop_x}:0")
        filters.append("scale=1080:1920:force_original_aspect_ratio=decrease")
        filters.append("pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black")
        
    if os.path.exists(ass_path):
        ass_ffmpeg = ffmpeg_escape_path(ass_path)
        filters.append(f"ass='{ass_ffmpeg}'")
        
    vf = ",".join(filters) if filters else "null"
    
    run_ffmpeg(
        f'ffmpeg -i "{intermediate_clip}" -vf "{vf}" -c:v libx264 -preset fast -crf 22 -c:a copy -y "{output_clip}"'
    )
    
    cursor.execute("UPDATE video_clips SET status = 'ready' WHERE id = %s", (CLIP_ID,))
    db.commit()
