"""
RoninClips — Emoji Overlay Module
Scans word-level transcripts for keyword matches and generates animated
contextual emoji popups using pre-rendered PNG images overlaid via FFmpeg.

Approach:
1. Scan transcript words against a keyword→emoji mapping
2. Render each triggered emoji to a transparent PNG using Pillow
3. Generate FFmpeg overlay filters with enable/alpha for fade animations

NOTE: FFmpeg's drawtext filter cannot render color emoji (only monochrome
glyph outlines). This module uses Pillow to render real color emoji to PNGs
and overlays them with the `overlay` filter instead.
"""

import random
import os
from PIL import Image, ImageDraw, ImageFont


# ──────────────────────────────────────────────
# Keyword → Emoji Mapping
# ──────────────────────────────────────────────

# Curated mapping of trigger words/phrases to emojis.
# Each key is a lowercase word; values are emoji characters.
KEYWORD_EMOJI_MAP = {
    # Fire / Intensity
    'fire': '🔥', 'lit': '🔥', 'heat': '🔥', 'hot': '🔥', 'flames': '🔥',
    'burn': '🔥', 'burning': '🔥',
    # Skull / Dead
    'dead': '💀', 'dying': '💀', 'kill': '💀', 'killed': '💀', 'rip': '💀',
    # Laughter
    'funny': '😂', 'hilarious': '😂', 'laugh': '😂', 'laughing': '😂',
    'lol': '😂', 'lmao': '😂', 'joke': '😂', 'jokes': '😂',
    # Money
    'money': '💰', 'cash': '💰', 'rich': '💰', 'dollar': '💰', 'dollars': '💰',
    'million': '💰', 'billion': '💰', 'profit': '💰', 'paid': '💰',
    # 100 / Perfect
    'perfect': '💯', 'exactly': '💯', 'hundred': '💯', 'facts': '💯',
    'real': '💯', 'truth': '💯',
    # Mind blown
    'crazy': '🤯', 'insane': '🤯', 'wild': '🤯', 'unbelievable': '🤯',
    'mindblowing': '🤯', 'incredible': '🤯', 'impossible': '🤯',
    # Target / Accuracy
    'accurate': '🎯', 'target': '🎯', 'goal': '🎯', 'nailed': '🎯',
    'bullseye': '🎯', 'spot': '🎯',
    # Love / Heart
    'love': '❤️', 'heart': '❤️', 'amazing': '❤️', 'beautiful': '❤️',
    # Rocket / Growth
    'rocket': '🚀', 'launch': '🚀', 'skyrocket': '🚀', 'moon': '🚀',
    'growth': '🚀', 'explode': '🚀', 'blowup': '🚀',
    # Warning / Danger
    'danger': '⚠️', 'warning': '⚠️', 'careful': '⚠️', 'risk': '⚠️',
    'dangerous': '⚠️',
    # Crown / King
    'king': '👑', 'queen': '👑', 'goat': '👑', 'legend': '👑', 'best': '👑',
    'greatest': '👑', 'champion': '👑',
    # Clap / Respect
    'respect': '👏', 'bravo': '👏', 'applause': '👏', 'congrats': '👏',
    'congratulations': '👏',
    # Crying / Sad
    'sad': '😢', 'cry': '😢', 'crying': '😢', 'tears': '😢', 'heartbreak': '😢',
    # Thinking
    'think': '🤔', 'thinking': '🤔', 'wonder': '🤔', 'wondering': '🤔',
    'question': '🤔', 'curious': '🤔',
    # Shock / Surprise
    'shock': '😱', 'shocked': '😱', 'surprise': '😱', 'surprised': '😱',
    'omg': '😱', 'woah': '😱', 'wow': '😱',
    # Strong / Muscle
    'strong': '💪', 'strength': '💪', 'powerful': '💪', 'power': '💪',
    'grind': '💪', 'hustle': '💪', 'work': '💪', 'workout': '💪',
    # Eyes / Watch
    'watch': '👀', 'look': '👀', 'see': '👀', 'notice': '👀', 'secret': '👀',
    # Win / Victory
    'win': '🏆', 'winner': '🏆', 'winning': '🏆', 'victory': '🏆', 'trophy': '🏆',
    # Brain / Genius
    'smart': '🧠', 'genius': '🧠', 'brain': '🧠', 'iq': '🧠', 'mind': '🧠',
    # Idea / Lightbulb
    'idea': '💡', 'solution': '💡', 'strategy': '💡', 'tip': '💡',
    # Crypto / Finance
    'crypto': '📈', 'bitcoin': '📈', 'btc': '📈', 'stock': '📈', 'investment': '📈',
}

# Minimum seconds between emoji popups to avoid visual spam
MIN_EMOJI_GAP = 3.0

# How long each emoji stays visible
EMOJI_DISPLAY_DURATION = 1.5

# Emoji PNG size (square)
EMOJI_PNG_SIZE = 128


# ──────────────────────────────────────────────
# Transcript Scanner
# ──────────────────────────────────────────────

def scan_transcript_for_emojis(words, min_gap=MIN_EMOJI_GAP):
    """
    Scan a word-level transcript for keyword matches.

    Args:
        words: List of {'word': str, 'start': float, 'end': float} dicts
               from Whisper word-level timestamps.
        min_gap: Minimum seconds between emoji events to avoid clutter.

    Returns:
        List of {'emoji': str, 'time': float, 'duration': float} events,
        sorted by time.
    """
    events = []
    last_emoji_time = -999.0

    for w in words:
        clean_word = w['word'].strip().lower()
        # Strip common punctuation
        clean_word = clean_word.strip('.,!?;:\'"()-')

        if clean_word in KEYWORD_EMOJI_MAP:
            trigger_time = w['start']

            # Enforce minimum gap
            if trigger_time - last_emoji_time < min_gap:
                continue

            events.append({
                'emoji': KEYWORD_EMOJI_MAP[clean_word],
                'time': trigger_time,
                'duration': EMOJI_DISPLAY_DURATION,
            })
            last_emoji_time = trigger_time

    return events


# ──────────────────────────────────────────────
# Emoji PNG Rendering (Pillow)
# ──────────────────────────────────────────────

def _find_emoji_font(size=EMOJI_PNG_SIZE):
    """
    Find a suitable color emoji font on the system.
    Returns a Pillow ImageFont object.
    """
    # Try common emoji font paths
    font_candidates = [
        # Windows — Segoe UI Emoji (full color emoji support)
        'C:/Windows/Fonts/seguiemj.ttf',
        # Fallback Windows paths
        os.path.expandvars('%WINDIR%/Fonts/seguiemj.ttf'),
        # Linux — Noto Color Emoji
        '/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf',
        '/usr/share/fonts/noto-cjk/NotoColorEmoji.ttf',
        # macOS — Apple Color Emoji
        '/System/Library/Fonts/Apple Color Emoji.ttc',
    ]

    for path in font_candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue

    # Fallback: use default font (won't have color emoji but won't crash)
    print("  [emoji_overlay] WARNING: No color emoji font found, using default")
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return ImageFont.load_default()


def render_emoji_png(emoji_char, output_path, size=EMOJI_PNG_SIZE):
    """
    Render a single emoji character to a transparent PNG file using Pillow.

    Args:
        emoji_char: The emoji character string (e.g., '🔥')
        output_path: Where to save the PNG
        size: Size of the output image (square)

    Returns:
        True if rendering succeeded, False otherwise
    """
    try:
        # Create transparent RGBA canvas (larger to accommodate emoji with padding)
        canvas_size = size + 32  # extra padding
        img = Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Load emoji font
        font = _find_emoji_font(size)

        # Get the bounding box of the emoji to center it
        bbox = draw.textbbox((0, 0), emoji_char, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        # Center the emoji on the canvas
        x = (canvas_size - text_w) // 2 - bbox[0]
        y = (canvas_size - text_h) // 2 - bbox[1]

        # Draw the emoji
        draw.text((x, y), emoji_char, font=font, embedded_color=True)

        # Crop to actual content + small padding
        content_bbox = img.getbbox()
        if content_bbox:
            pad = 4
            crop_box = (
                max(0, content_bbox[0] - pad),
                max(0, content_bbox[1] - pad),
                min(canvas_size, content_bbox[2] + pad),
                min(canvas_size, content_bbox[3] + pad),
            )
            img = img.crop(crop_box)

        # Ensure even dimensions (required by some FFmpeg pixel formats)
        w, h = img.size
        if w % 2 != 0:
            w += 1
        if h % 2 != 0:
            h += 1
        if (w, h) != img.size:
            new_img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            new_img.paste(img, (0, 0))
            img = new_img

        img.save(output_path, 'PNG')
        return True

    except Exception as e:
        print(f"  [emoji_overlay] Failed to render emoji '{emoji_char}': {e}")
        return False


def prepare_emoji_pngs(emoji_events, temp_dir):
    """
    Render all unique emojis needed for the events to PNG files.

    Args:
        emoji_events: List of {'emoji': str, 'time': float, 'duration': float}
        temp_dir: Directory to save PNG files

    Returns:
        Dict mapping emoji character → PNG file path.
        Only includes successfully rendered emojis.
    """
    os.makedirs(temp_dir, exist_ok=True)

    unique_emojis = set(e['emoji'] for e in emoji_events)
    emoji_paths = {}

    for emoji_char in unique_emojis:
        # Create a safe filename from the emoji's Unicode codepoints
        codepoints = '-'.join(f'{ord(c):04x}' for c in emoji_char)
        png_path = os.path.join(temp_dir, f'emoji_{codepoints}.png')

        if os.path.exists(png_path) or render_emoji_png(emoji_char, png_path):
            emoji_paths[emoji_char] = png_path

    print(f"  [emoji_overlay] Rendered {len(emoji_paths)}/{len(unique_emojis)} emoji PNGs")
    return emoji_paths


# ──────────────────────────────────────────────
# FFmpeg Overlay Filter Generation
# ──────────────────────────────────────────────

def _random_position(output_w, output_h, emoji_size, seed):
    """
    Generate a random position in the upper-right quadrant of the frame,
    avoiding the caption zone (bottom 30%) and edges.

    Uses a deterministic seed so positions are reproducible.
    """
    rng = random.Random(seed)

    # Upper-right quadrant: X in [50%..85%], Y in [5%..35%]
    margin = emoji_size
    x_min = int(output_w * 0.50) + margin
    x_max = int(output_w * 0.85) - margin
    y_min = int(output_h * 0.05) + margin
    y_max = int(output_h * 0.35) - margin

    x = rng.randint(x_min, max(x_min + 1, x_max))
    y = rng.randint(y_min, max(y_min + 1, y_max))

    return x, y


def _escape_path_for_ffmpeg(path):
    """Escape a file path for use inside FFmpeg filter expressions."""
    # Convert backslashes to forward slashes
    p = path.replace('\\', '/')
    # Escape colons (drive letters like C:)
    p = p.replace(':', '\\:')
    # Escape single quotes
    p = p.replace("'", "'\\''")
    return p


def generate_emoji_overlay_data(emoji_events, output_w=1080, output_h=1920, temp_dir=None):
    """
    Generate emoji overlay data: pre-rendered PNG files and FFmpeg filter info.

    This replaces the old drawtext approach with overlay filters that can
    actually display color emoji.

    IMPORTANT DESIGN NOTES:
    - PNG inputs are single-frame still images with NO timeline, so FFmpeg's
      fade filter (which uses stream timestamps) does NOT work on them.
    - Each emoji event gets its OWN input file reference — even if the same
      emoji appears multiple times — because FFmpeg cannot reference the same
      input stream (e.g., [1:v]) more than once in a filter graph.

    Args:
        emoji_events: List of {'emoji': str, 'time': float, 'duration': float}
        output_w: Output video width
        output_h: Output video height
        temp_dir: Directory for temporary emoji PNG files

    Returns:
        dict with:
        - 'input_files': List of PNG file paths to add as FFmpeg inputs
        - 'filter_parts': List of FFmpeg filter strings to append
        - 'final_label': The output label name from the last overlay
        Or None if no events or rendering fails.
    """
    if not emoji_events or not temp_dir:
        return None

    emoji_size = max(48, int(output_h / 30))  # ~64px on 1920p

    # Render emoji PNGs
    emoji_paths = prepare_emoji_pngs(emoji_events, temp_dir)
    if not emoji_paths:
        return None

    # Build overlay filter chain
    # Each emoji event gets its OWN -i input (even if same emoji char)
    # because FFmpeg can't reference the same input stream twice.

    input_files = []   # PNG paths — one per EVENT, not per unique emoji
    filter_parts = []

    # Validate events and build input list (one input per event)
    valid_events = []
    for event in emoji_events:
        emoji_char = event['emoji']
        if emoji_char in emoji_paths:
            input_files.append(emoji_paths[emoji_char])
            valid_events.append(event)

    if not input_files:
        return None

    # Build overlay chain
    # Each event gets an overlay. We chain them: [video] -> overlay1 -> overlay2 -> ...
    # The video stream is assumed to be labeled [vemoji_in] by the caller

    prev_label = 'vemoji_in'
    overlay_count = 0

    for i, event in enumerate(valid_events):
        t_start = event['time']
        t_dur = event['duration']
        t_end = t_start + t_dur

        # Each event's input index is i+1 (0 is the main video)
        input_idx = i + 1

        # Random position (upper-right quadrant, avoid caption zone)
        x, y = _random_position(output_w, output_h, emoji_size, seed=i + int(t_start * 100))

        out_label = f'vemoji_{overlay_count}'
        emoji_label_scaled = f'emoji_s{overlay_count}'

        # Scale the PNG to desired size — NO fade filters (they don't work
        # on still images since PNGs have no timeline/pts progression).
        # Visibility is controlled entirely by the overlay's `enable` expression.
        filter_parts.append(
            f'[{input_idx}:v]'
            f'scale={emoji_size}:{emoji_size}:flags=lanczos,'
            f'format=rgba'
            f'[{emoji_label_scaled}]'
        )

        # Overlay with enable expression for visibility window.
        # The emoji pops in at t_start and disappears at t_end — clean pop
        # animation that matches TikTok/Shorts style emoji overlays.
        filter_parts.append(
            f'[{prev_label}][{emoji_label_scaled}]'
            f"overlay=x={x}:y={y}:"
            f"enable='between(t,{t_start:.3f},{t_end:.3f})'"
            f'[{out_label}]'
        )

        prev_label = out_label
        overlay_count += 1

    if overlay_count == 0:
        return None

    return {
        'input_files': input_files,
        'filter_parts': filter_parts,
        'final_label': prev_label,
    }


# ──────────────────────────────────────────────
# Legacy API (backward-compatible wrapper)
# ──────────────────────────────────────────────

def generate_emoji_overlay_filter(emoji_events, output_w=1080, output_h=1920):
    """
    Legacy API — returns None since the old drawtext approach doesn't work
    for color emoji. Use generate_emoji_overlay_data() instead.

    This function exists so the old engine.py code doesn't crash during
    the transition to the new overlay approach.
    """
    # Return None to signal the caller to skip (old drawtext approach is broken)
    # The new approach requires temp_dir and multi-input FFmpeg, which the
    # caller must handle explicitly via generate_emoji_overlay_data()
    return None


# ──────────────────────────────────────────────
# CLI Test Mode
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import tempfile

    # Test with fake transcript words
    test_words = [
        {'word': 'This', 'start': 0.0, 'end': 0.3},
        {'word': 'is', 'start': 0.3, 'end': 0.5},
        {'word': 'fire', 'start': 0.5, 'end': 0.8},
        {'word': 'bro', 'start': 0.8, 'end': 1.0},
        {'word': 'that', 'start': 2.0, 'end': 2.2},
        {'word': 'was', 'start': 2.2, 'end': 2.4},
        {'word': 'hilarious', 'start': 2.4, 'end': 3.0},
        {'word': 'I', 'start': 5.0, 'end': 5.1},
        {'word': 'made', 'start': 5.1, 'end': 5.3},
        {'word': 'a', 'start': 5.3, 'end': 5.4},
        {'word': 'million', 'start': 5.4, 'end': 5.9},
        {'word': 'dollars', 'start': 5.9, 'end': 6.5},
        {'word': 'that', 'start': 10.0, 'end': 10.2},
        {'word': 'is', 'start': 10.2, 'end': 10.4},
        {'word': 'crazy', 'start': 10.4, 'end': 10.9},
        {'word': 'wow', 'start': 15.0, 'end': 15.3},
    ]

    # Fix Windows console encoding for emoji
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

    print("Testing emoji overlay scanner...")
    events = scan_transcript_for_emojis(test_words)
    print(f"\nDetected {len(events)} emoji events:")
    for ev in events:
        print(f"  {ev['emoji']}  at {ev['time']:.1f}s (duration: {ev['duration']:.1f}s)")

    if events:
        with tempfile.TemporaryDirectory() as tmpdir:
            data = generate_emoji_overlay_data(events, 1080, 1920, tmpdir)
            if data:
                print(f"\nEmoji input files: {len(data['input_files'])}")
                for p in data['input_files']:
                    print(f"  {p}")
                print(f"\nFilter parts ({len(data['filter_parts'])}):")
                for fp in data['filter_parts']:
                    preview = fp[:120] + "..." if len(fp) > 120 else fp
                    print(f"  {preview}")
                print(f"\nFinal label: {data['final_label']}")
            else:
                print("\nNo overlay data generated (PNG rendering may have failed)")
