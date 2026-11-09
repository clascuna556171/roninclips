"""
RoninClips — Shared ASS Subtitle Generator Module
Generates Advanced SubStation Alpha (.ass) word-by-word animated subtitles
and escapes paths for FFmpeg subtitle filters.
"""

import re

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
    'hormozi_box': {
        'active_color': '\\c&H00D7FF&',      # Gold / Warm Yellow (#FFD700 -> BGR 00D7FF)
        'inactive_color': '\\c&HFFFFFF&',    # White
        'outline_size': 6,
        'shadow_size': 4,
    },
    'karaoke_green': {
        'active_color': '\\c&H00FF66&',      # Neon Lime (#66FF00 -> BGR 00FF66)
        'inactive_color': '\\c&HFFFFFF&',    # White
        'outline_size': 5,
        'shadow_size': 3,
    },
    'cyber_pink': {
        'active_color': '\\c&HFF00FF&',      # Neon Magenta / Pink (#FF00FF -> BGR FF00FF)
        'inactive_color': '\\c&H00FFFF&',    # Electric Yellow (#FFFF00 -> BGR 00FFFF)
        'outline_size': 5,
        'shadow_size': 3,
    },
    'fire_gold': {
        'active_color': '\\c&H0045FF&',      # Fire Red-Orange (#FF4500 -> BGR 0045FF)
        'inactive_color': '\\c&H00D7FF&',    # Warm Gold (#FFD700 -> BGR 00D7FF)
        'outline_size': 6,
        'shadow_size': 3,
    },
    'electric_violet': {
        'active_color': '\\c&HF755A8&',      # Electric Violet (#A855F7 -> BGR F755A8)
        'inactive_color': '\\c&HFFFFFF&',    # Crisp White
        'outline_size': 5,
        'shadow_size': 3,
    },
}


def format_ass_time(seconds):
    """Convert seconds to ASS time format H:MM:SS.CC"""
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def ffmpeg_escape_path(path):
    """
    Escape a file path for use inside FFmpeg filter strings (e.g., ass= or subtitles=).
    Handles Windows drive letters, backslashes, and special characters.
    """
    p = path.replace('\\', '/')
    p = p.replace(':', '\\:')
    return p


def generate_ass_subtitles(words, output_path, output_w=1080, output_h=1920,
                            style_preset='yellow_pop', font_family='Arial Black',
                            position='bottom', layout_mode='two_line'):
    """
    Generate an ASS subtitle file with word-by-word highlighting.
    """
    style_cfg = PALETTES.get(style_preset, PALETTES['yellow_pop'])

    if layout_mode == 'single_word':
        chunk_size = 1
        font_size = max(60, int(output_h / 18))
    elif layout_mode == 'full_line':
        chunk_size = 7
        font_size = max(40, int(output_h / 28))
    else:  # 'two_line' default
        chunk_size = 4
        font_size = max(48, int(output_h / 24))

    pos = str(position).lower()
    if pos == 'top':
        alignment = 8
        margin_v = int(output_h * 0.10)
    elif pos == 'center':
        alignment = 5
        margin_v = 0
    else:  # 'bottom' default
        alignment = 2
        margin_v = int(output_h * 0.14)

    outline_val = style_cfg['outline_size']
    shadow_val = style_cfg['shadow_size']
    font_name = re.sub(r'[,\r\n]', '', font_family).strip() if font_family else 'Arial Black'

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
            if i < len(chunk) - 1:
                event_end = chunk[i + 1]['start']
            else:
                event_end = chunk_end

            if event_end - event_start < 0.05:
                event_end = event_start + 0.15

            parts = []
            for j, w in enumerate(chunk):
                word_text = re.sub(r'[{}\\]', '', str(w.get('word', ''))).strip().upper()
                if not word_text:
                    continue

                line_prefix = "\\N " if (layout_mode == 'two_line' and j == 2) else ""

                if j == i:
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
