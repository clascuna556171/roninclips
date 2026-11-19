import sys
import os
import subprocess
import json
import re
import threading
import concurrent.futures
import urllib.request
import urllib.error
from dotenv import load_dotenv, dotenv_values
from faster_whisper import WhisperModel
from groq import Groq

WHISPER_LOCK = threading.Lock()

# Fix Windows encoding — prevent crash on emoji/unicode in print() AND subprocess pipes.
if sys.platform == 'win32':
    os.environ['PYTHONUTF8'] = '1'
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Load Laravel's .env file from the parent directory
ENV_FILE = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(ENV_FILE)

# Keys pasted in the dashboard are written to .env. A long-running PHP worker can still hold
# the old value in its environment, so the file wins for these keys when it sets them.
API_KEY_VARS = ('GROQ_API_KEY', 'GEMINI_API_KEY')


def load_api_keys(env_path=ENV_FILE, environ=os.environ):
    try:
        values = dotenv_values(env_path)
    except Exception:
        return
    for var in API_KEY_VARS:
        val = (values.get(var) or '').strip()
        if val:
            environ[var] = val


load_api_keys()

# 1. Boot Environment & Context
VIDEO_ID = sys.argv[1] if (__name__ == "__main__" and len(sys.argv) > 1) else None

# Default settings
DEFAULT_SETTINGS = {
    'output_format': '9:16',
    'caption_style': 'yellow_pop',
    'caption_font': 'Arial Black',
    'caption_position': 'bottom',
    'caption_layout': 'two_line',
    'transition_speed': 0.25,
    'full_video_mode': False,
    'whisper_model': 'small',
    'language_mode': 'auto',
    'hardware_accel': 'auto',
    'smart_crop': True,
    'auto_captions': True,
    'punch_in_zoom': False,
    'ken_burns': False,
    'emoji_overlays': False,
    'whip_pan_transitions': False,
    'background_music': False,
    'bgm_path': '',
    'split_screen': False,
    'gaming_layout': False,
    'clean_captions': False,      # mask swear words in captions (slurs are always masked)
    'loudness_normalize': True,   # finished clip at -14 LUFS
}

if __name__ == "__main__" and len(sys.argv) > 2 and sys.argv[2] != '--b64':
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

if __name__ == "__main__":
    print(f"Initial settings: {json.dumps(SETTINGS, indent=2)}")

client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))

# Import local modules
sys.path.insert(0, os.path.dirname(__file__))
from db_helper import get_db, DatabaseUnavailable
from vod_import import import_vod, import_vod_sparse, fetch_clip_source, cleanup_sparse_files, VodImportError
from moments import detect_moments, detect_moments_from_signals, load_chat
from hw_accel import get_whisper_config, detect_ffmpeg_encoder, get_hardware_status
from face_tracker import get_smart_crop_filter, get_video_info
from effects import detect_volume_spikes, generate_punchin_filter, generate_kenburns_filter
from emoji_overlay import scan_transcript_for_emojis, generate_emoji_overlay_data
from audio_mixer import detect_speech_regions, mix_background_music, normalize_loudness
from transitions import apply_whip_pan_transitions
from split_screen import get_split_screen_filter
from gaming_layout import get_gaming_layout
from subtitles import generate_ass_subtitles, format_ass_time, ffmpeg_escape_path


# ──────────────────────────────────────────────
# Helper Functions
# ──────────────────────────────────────────────

def run_ffmpeg(cmd, **kwargs):
    """
    Run a subprocess command with UTF-8 encoding to avoid Windows cp1252 crashes.
    FFmpeg's stderr often contains non-ASCII bytes that crash cp1252 decoding.
    Uses shell=False automatically when cmd is passed as a list of arguments.
    """
    kwargs.setdefault('shell', isinstance(cmd, str))
    kwargs.setdefault('capture_output', True)
    kwargs.pop('text', None)
    return subprocess.run(cmd, encoding='utf-8', errors='replace', **kwargs)


def parse_time_to_seconds(time_val):
    """
    Convert a time value to float seconds.
    Handles: HH:MM:SS strings, MM:SS strings, HH:MM:SS.ms strings, timedelta objects, and numeric values.
    """
    import datetime
    if isinstance(time_val, (int, float)):
        return float(time_val)
    if isinstance(time_val, datetime.timedelta):
        return time_val.total_seconds()
    if isinstance(time_val, str):
        cleaned = time_val.strip().rstrip('sS')
        parts = cleaned.split(':')
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(parts[0])
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


def parse_groq_json_response(raw_text):
    """
    Robustly extracts and parses JSON array from LLM response text,
    handling markdown wrappers, conversational preambles, and postscripts.
    """
    if not raw_text:
        raise ValueError("Empty response received from LLM.")

    # 1. Direct stripped attempt
    clean = raw_text.replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(clean)
        if isinstance(data, list):
            return data
    except Exception:
        pass

    # 2. Regex search for array of objects [ { ... } ]
    match = re.search(r'\[\s*\{.*\}\s*\]', raw_text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, list):
                return data
        except Exception:
            pass

    # 3. Bracket boundary slice [ ... ]
    start_idx = raw_text.find('[')
    end_idx = raw_text.rfind(']')
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        slice_text = raw_text[start_idx:end_idx + 1]
        try:
            data = json.loads(slice_text)
            if isinstance(data, list):
                return data
        except Exception as e:
            raise ValueError(f"Found JSON array brackets but parsing failed: {e}. Output snippet: {slice_text[:250]}...")

    raise ValueError(f"Could not locate a valid JSON array in model output. Response preview: {raw_text[:300]}...")


def split_transcript_into_chunks(transcript_text, max_chars=28000):
    """
    Split a long transcript into newline-aligned chunks of at most max_chars
    so multi-hour podcasts or streams can be analyzed across their full length.
    """
    text = (transcript_text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks = []
    current_lines = []
    current_len = 0

    for line in text.splitlines():
        line_len = len(line) + 1
        if current_lines and current_len + line_len > max_chars:
            chunks.append("\n".join(current_lines))
            current_lines = [line]
            current_len = line_len
        else:
            current_lines.append(line)
            current_len += line_len

    if current_lines:
        chunks.append("\n".join(current_lines))

    return chunks


# ──────────────────────────────────────────────
# Groq helpers (shared by AI hooks and stream moments)
# ──────────────────────────────────────────────

GROQ_PREFERRED_MODELS = [
    "openai/gpt-oss-120b",
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-20b",
    "qwen/qwen3.6-27b",
    "llama-3.1-8b-instant",
    "qwen/qwen3-32b",
    "groq/compound",
    "groq/compound-mini",
]

GROQ_SYSTEM_PROMPT = ("You are an elite short-form video editor and viral strategist AI. You analyze transcripts, "
                      "find the most viral moments, score them with precision, and generate high-converting social "
                      "media copy. Always respond with valid JSON only, no markdown.")


def get_groq_models():
    """GROQ_MODEL override first, then live models in preferred order, then the rest."""
    groq_models = []
    if not os.environ.get("GROQ_API_KEY", "").strip():
        return groq_models
    custom_model = os.environ.get("GROQ_MODEL", "").strip()
    if custom_model:
        groq_models.append(custom_model)
    try:
        live_models = client.models.list().data
        active_chat_ids = [
            m.id for m in live_models
            if not any(k in m.id.lower() for k in ['whisper', 'orpheus', 'tts', 'playai', 'guard', 'embedding'])
        ]
        for pref in GROQ_PREFERRED_MODELS:
            if pref in active_chat_ids and pref not in groq_models:
                groq_models.append(pref)
        for m_id in active_chat_ids:
            if m_id not in groq_models:
                groq_models.append(m_id)
        print(f"  Live Groq models discovered: {len(active_chat_ids)} models available")
    except Exception as query_err:
        print(f"  ℹ️ Live model query skipped ({query_err}), using curated active fallback list.")
        for pref in GROQ_PREFERRED_MODELS:
            if pref not in groq_models:
                groq_models.append(pref)
    return groq_models


def groq_complete(prompt, groq_models):
    """Try each model in order. Returns (raw_text or None, last_error)."""
    last_error = None
    for model_name in groq_models:
        try:
            print(f"  Trying model: {model_name}...")
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": GROQ_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                model=model_name,
                temperature=0.3,
            )
            print(f"  Success with model: {model_name}")
            return chat_completion.choices[0].message.content, None
        except Exception as model_err:
            last_error = model_err
    return None, last_error


# ──────────────────────────────────────────────
# Gemini backup (used only when every Groq model fails or no Groq key is set)
# ──────────────────────────────────────────────

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_PREFERRED_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
]
GEMINI_SKIP_WORDS = ('embedding', 'tts', 'image', 'live', 'audio', 'aqa', 'vision', 'gemma')
GEMINI_MAX_MODELS = 5
_gemini_models_cache = None


def _gemini_request(path, api_key, body=None, timeout=120):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(
        f"{GEMINI_API_BASE}/{path}",
        data=data,
        headers={'Content-Type': 'application/json', 'x-goog-api-key': api_key},
        method='POST' if data is not None else 'GET',
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as http_err:
        detail = ''
        try:
            detail = json.loads(http_err.read().decode('utf-8')).get('error', {}).get('message', '')
        except Exception:
            pass
        raise RuntimeError(f"Gemini HTTP {http_err.code}: {detail or http_err.reason}") from None


def pick_gemini_models(live_names, custom_model=''):
    """GEMINI_MODEL override first, then preferred live models, then other live text models (flash first)."""
    models = [custom_model] if custom_model else []
    live = [n for n in live_names if n.startswith('gemini') and not any(w in n for w in GEMINI_SKIP_WORDS)]
    if not live:
        live = list(GEMINI_PREFERRED_MODELS)
    for pref in GEMINI_PREFERRED_MODELS:
        if pref in live and pref not in models:
            models.append(pref)
    for name in sorted(live, key=lambda n: ('flash' not in n, n)):
        if name not in models:
            models.append(name)
    return models[:GEMINI_MAX_MODELS]


def get_gemini_models():
    global _gemini_models_cache
    if _gemini_models_cache is not None:
        return _gemini_models_cache
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        _gemini_models_cache = []
        return _gemini_models_cache
    live_names = []
    try:
        payload = _gemini_request('models?pageSize=200', api_key, timeout=20)
        live_names = [
            m.get('name', '').removeprefix('models/') for m in payload.get('models', [])
            if 'generateContent' in m.get('supportedGenerationMethods', [])
        ]
    except Exception as list_err:
        print(f"  ℹ️ Gemini model list skipped ({list_err}), using curated list.")
    _gemini_models_cache = pick_gemini_models(live_names, os.environ.get("GEMINI_MODEL", "").strip())
    return _gemini_models_cache


def gemini_extract_text(payload):
    candidates = payload.get('candidates') or []
    if not candidates:
        reason = (payload.get('promptFeedback') or {}).get('blockReason', 'no candidates')
        raise RuntimeError(f"Gemini returned no answer ({reason})")
    parts = (candidates[0].get('content') or {}).get('parts') or []
    text = ''.join(p.get('text', '') for p in parts if not p.get('thought'))
    if not text.strip():
        raise RuntimeError(f"Gemini returned empty text ({candidates[0].get('finishReason', 'unknown')})")
    return text


def gemini_complete(prompt, gemini_models):
    """Try each Gemini model in order. Returns (raw_text or None, last_error)."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    last_error = None
    for model_name in gemini_models:
        try:
            print(f"  Trying Gemini model: {model_name}...")
            payload = _gemini_request(f"models/{model_name}:generateContent", api_key, {
                'systemInstruction': {'parts': [{'text': GROQ_SYSTEM_PROMPT}]},
                'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
                'generationConfig': {'temperature': 0.3, 'responseMimeType': 'application/json'},
            })
            text = gemini_extract_text(payload)
            print(f"  Success with Gemini model: {model_name}")
            return text, None
        except Exception as model_err:
            last_error = model_err
    return None, last_error


def llm_complete(prompt, groq_models):
    """Groq first, Gemini as the backup. Returns (raw_text or None, last_error)."""
    has_groq = bool(os.environ.get("GROQ_API_KEY", "").strip())
    has_gemini = bool(os.environ.get("GEMINI_API_KEY", "").strip())
    if not has_groq and not has_gemini:
        return None, RuntimeError("No AI key set. Paste a Groq or Gemini key in the dashboard's API KEYS panel.")

    last_error = None
    if has_groq and groq_models:
        raw, last_error = groq_complete(prompt, groq_models)
        if raw is not None:
            return raw, None
    if has_gemini:
        if has_groq:
            print(f"  ⚠️ Groq failed ({last_error}); switching to Gemini backup.")
        raw, gemini_err = gemini_complete(prompt, get_gemini_models())
        if raw is not None:
            return raw, None
        last_error = gemini_err
    return None, last_error


# ──────────────────────────────────────────────
# Stream moments (chat flood + audio spike) helpers
# ──────────────────────────────────────────────

STREAM_HASHTAGS = '#stream #gaming #clips #fyp #twitch'
MIN_EXCERPT_CHARS = 40   # below this the transcript can't help Groq; use signal-based titles


def _signal_pct(z):
    return max(50, min(99, int(round(60 + 4 * (z or 0)))))


def moment_fallback_meta(m):
    """Metadata built from the detector alone (used when Groq is skipped or fails)."""
    summary = m['summary']
    return {
        'title': f"Stream moment at {format_time(m['peak'])}",
        'virality_score': _signal_pct(m['score']),
        'hook_strength': _signal_pct(m['chat_z'] if m.get('chat_msgs_10s') is not None else m['score']),
        'pacing_energy': _signal_pct(m['audio_z']),
        'shareability': _signal_pct(m['score']),
        'reason': summary,
        'social_caption': f"{summary} 🔥",
        'hashtags': STREAM_HASHTAGS,
        'shorts_description': summary,
        'source': 'stream_moments',
        'signal_summary': summary,
        'signals': {k: m.get(k) for k in ('peak', 'score', 'chat_z', 'audio_z',
                                         'chat_msgs_10s', 'chat_ratio', 'audio_db_above')},
    }


def build_moment_prompt(candidates, count):
    blocks = []
    for i, m in enumerate(candidates):
        excerpt = (m.get('excerpt') or '').strip()[:1200] or '(no clear speech)'
        blocks.append(f"Moment {i}: {format_time(m['start'])}-{format_time(m['end'])}\n"
                      f"Signals: {m['summary']}\nTranscript: \"{excerpt}\"")
    return f"""These are candidate moments from a livestream VOD, found automatically where chat flooded and/or the stream audio spiked.
Pick the best {count} for short-form vertical clips (TikTok / Reels / Shorts), best first. Do not invent times; refer to moments only by their id.
For each pick give a realistic Virality Score (1-100) with sub-scores, a punchy high-CTR title, a social caption with emojis, hashtags and a YouTube Shorts description.

Return STRICTLY a JSON array, no markdown:
[
  {{
    "id": 0,
    "title": "Short Punchy Title",
    "virality_score": 90,
    "hook_strength": 90,
    "pacing_energy": 90,
    "shareability": 90,
    "reason": "Why this moment works",
    "social_caption": "Caption with emojis",
    "hashtags": "#gaming #fyp",
    "shorts_description": "Search-optimized description"
  }}
]

Candidates:
""" + "\n\n".join(blocks)


def merge_moment_picks(candidates, picks, count):
    """
    Groq's valid picks first (in its order, by id), then fill from the detector's
    ranking. Returns [(moment, meta)] sorted by start time.
    """
    chosen = []
    used = set()
    for p in picks or []:
        if not isinstance(p, dict) or len(chosen) >= count:
            continue
        try:
            idx = int(p.get('id'))
        except (TypeError, ValueError):
            continue
        if idx in used or not (0 <= idx < len(candidates)):
            continue
        m = candidates[idx]
        meta = moment_fallback_meta(m)
        for key in ('title', 'reason', 'social_caption', 'hashtags', 'shorts_description'):
            if isinstance(p.get(key), str) and p[key].strip():
                meta[key] = p[key].strip()
        for key in ('virality_score', 'hook_strength', 'pacing_energy', 'shareability'):
            try:
                meta[key] = max(1, min(100, int(p[key])))
            except (KeyError, TypeError, ValueError):
                pass
        chosen.append((m, meta))
        used.add(idx)
    for idx, m in enumerate(candidates):
        if len(chosen) >= count:
            break
        if idx not in used:
            chosen.append((m, moment_fallback_meta(m)))
            used.add(idx)
    chosen.sort(key=lambda pair: pair[0]['start'])
    return chosen


def _is_cuda_error(err):
    return 'cublas' in str(err).lower() or 'cuda' in str(err).lower()


def transcribe_moment_windows(whisper_model, whisper_tier, audio_path, candidates, task, temp_dir):
    """
    Transcribe only the candidate windows. Adds m['excerpt'] to each candidate and returns
    (transcript_text, full_words, whisper_model) with VOD-absolute word timestamps.
    """
    full_words = []
    lines = []
    for i, m in enumerate(candidates):
        print(f"  📝 Transcribing moment window {i + 1}/{len(candidates)} "
              f"({format_time(m['start'])}-{format_time(m['end'])})...")
        wav = os.path.join(temp_dir, f"moment_{VIDEO_ID}_{i}.wav")
        run_ffmpeg(['ffmpeg', '-ss', f"{m['start']:.3f}", '-t', f"{m['end'] - m['start']:.3f}",
                    '-i', audio_path, '-ac', '1', '-ar', '16000', wav, '-y'])
        segments = []
        try:
            if os.path.exists(wav):
                try:
                    with WHISPER_LOCK:
                        segments = list(whisper_model.transcribe(wav, beam_size=5, word_timestamps=True, task=task)[0])
                except Exception as w_err:
                    if not _is_cuda_error(w_err):
                        raise
                    print(f"  ⚠️ Whisper CUDA execution failed ({w_err}), falling back to CPU (int8)...")
                    whisper_model = WhisperModel(whisper_tier, device='cpu', compute_type='int8')
                    with WHISPER_LOCK:
                        segments = list(whisper_model.transcribe(wav, beam_size=5, word_timestamps=True, task=task)[0])
        finally:
            if os.path.exists(wav):
                os.remove(wav)
        texts = []
        for seg in segments:
            texts.append(seg.text.strip())
            lines.append(f"[{format_time(m['start'] + seg.start)} - {format_time(m['start'] + seg.end)}] {seg.text.strip()}")
            for w in (seg.words or []):
                full_words.append({'word': w.word.strip(), 'start': m['start'] + w.start, 'end': m['start'] + w.end})
        m['excerpt'] = ' '.join(t for t in texts if t)
    full_words.sort(key=lambda w: w['start'])
    return "\n".join(lines), full_words, whisper_model


def render_single_clip(sc, video, SETTINGS, whisper_model, encoder_flags, output_dir, temp_dir, full_words=None):
    """
    Renders a single candidate video clip with all visual effects and audio processing.
    Can be executed concurrently in a worker thread.
    """
    clip_id = sc['id']
    thread_db = get_db()
    thread_cursor = thread_db.cursor()

    try:
        output_clip = os.path.join(output_dir, f"clip_{clip_id}.mp4")
        relative_output = f"storage/app/public/clip_{clip_id}.mp4"
        
        thread_cursor.execute("UPDATE video_clips SET status = 'rendering' WHERE id = %s", (clip_id,))
        thread_db.commit()

        clip_start = parse_time_to_seconds(sc['start_time'])
        clip_end = parse_time_to_seconds(sc['end_time'])
        clip_duration = clip_end - clip_start
        clip_start_str = format_seconds_ffmpeg(clip_start)
        clip_end_str = format_seconds_ffmpeg(clip_end)
        clip_duration_str = format_seconds_ffmpeg(clip_duration)

        print(f"\n{'='*60}")
        print(f"  Rendering clip {clip_id}: {clip_start_str} -> {clip_end_str} ({clip_duration:.2f}s)")
        print(f"  Settings: crop={SETTINGS['smart_crop']}, captions={SETTINGS['auto_captions']}, "
              f"punch_in={SETTINGS['punch_in_zoom']}, ken_burns={SETTINGS['ken_burns']}, "
              f"emoji={SETTINGS['emoji_overlays']}, transitions={SETTINGS['whip_pan_transitions']}, "
              f"bgm={SETTINGS['background_music']}, split={SETTINGS['split_screen']}, "
              f"format={SETTINGS['output_format']}")
        print(f"{'='*60}")

        # ─── Step A: Extract clean intermediate clip ───
        intermediate_clip = os.path.join(temp_dir, f"intermediate_{clip_id}.mp4")
        print(f"  📦 [Clip #{clip_id}] Extracting intermediate clip...")

        # Sparse (watchlist) clips come from their own downloaded window, which starts at
        # VOD time `_src_offset`; seek within that file instead of the full VOD.
        source_path = sc.get('_src_path') or video['storage_path']
        src_offset = float(sc.get('_src_offset') or 0.0)
        seek_start_str = format_seconds_ffmpeg(max(0.0, clip_start - src_offset))
        seek_end_str = format_seconds_ffmpeg(max(0.0, clip_end - src_offset))

        intermediate_result = run_ffmpeg([
            'ffmpeg', '-i', source_path, '-ss', seek_start_str, '-t', clip_duration_str,
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-c:a', 'aac', '-b:a', '128k',
            '-avoid_negative_ts', 'make_zero', '-async', '1',
            intermediate_clip, '-y'
        ])
        if intermediate_result.returncode != 0 or not os.path.exists(intermediate_clip):
            # Fallback: try input seeking
            print(f"  ⚠️ [Clip #{clip_id}] Output seeking failed, trying input seeking fallback...")
            run_ffmpeg([
                'ffmpeg', '-ss', seek_start_str, '-to', seek_end_str, '-i', source_path,
                '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-c:a', 'aac', '-b:a', '128k',
                '-avoid_negative_ts', 'make_zero',
                intermediate_clip, '-y'
            ])

        if not os.path.exists(intermediate_clip):
            print(f"  ❌ [Clip #{clip_id}] Failed to extract intermediate clip, skipping")
            thread_cursor.execute("UPDATE video_clips SET status = 'pending' WHERE id = %s", (clip_id,))
            thread_db.commit()
            return False

        inter_w, inter_h, inter_fps = get_video_info(intermediate_clip)
        print(f"  ✅ [Clip #{clip_id}] Intermediate clip: {inter_w}x{inter_h} @ {inter_fps:.1f}fps")

        # ─── Step A.2: Extract audio from intermediate for transcription ───
        clip_audio = os.path.join(temp_dir, f"clip_audio_{clip_id}.mp3")
        run_ffmpeg([
            'ffmpeg', '-i', intermediate_clip,
            '-b:a', '64k', '-ac', '1', '-ar', '16000', clip_audio, '-y'
        ])

        # ─── Step B: Split-Screen OR Smart Crop ───
        crop_filter = None
        split_filter_complex = None
        use_split_screen = False
        use_gaming_layout = False
        gaming_info = None
        render_w = inter_w
        render_h = inter_h

        if SETTINGS.get('gaming_layout') and SETTINGS['output_format'] == '9:16':
            print(f"  🎮 [Clip #{clip_id}] Looking for streamer facecam (gaming layout)...")
            try:
                gaming_info = get_gaming_layout(intermediate_clip, clip_duration)
                if gaming_info:
                    use_gaming_layout = True
                    render_w, render_h = 1080, 1920
                    print(f"  ✅ [Clip #{clip_id}] Gaming layout ready "
                          f"({'facecam + gameplay' if gaming_info['cam_box'] else 'gameplay only'})")
            except Exception as gaming_err:
                print(f"  ⚠️ [Clip #{clip_id}] Gaming layout failed: {gaming_err}, falling back")

        if use_gaming_layout:
            pass
        elif SETTINGS['split_screen'] and SETTINGS['output_format'] == '9:16':
            print(f"  👥 [Clip #{clip_id}] Detecting speakers for split-screen...")
            try:
                split_fc, split_w, split_h = get_split_screen_filter(
                    intermediate_clip,
                    start_time=0.0,
                    duration=clip_duration,
                    output_w=1080, output_h=1920
                )
                if split_fc:
                    split_filter_complex = split_fc
                    use_split_screen = True
                    render_w = split_w
                    render_h = split_h
                    print(f"  ✅ [Clip #{clip_id}] Split-screen ready: {split_w}x{split_h}")
                else:
                    print(f"  ℹ️ [Clip #{clip_id}] Could not detect 2 speakers — falling back to normal crop")
            except Exception as split_err:
                print(f"  ⚠️ [Clip #{clip_id}] Split-screen detection failed: {split_err}, falling back")

        if use_gaming_layout:
            pass
        elif not use_split_screen and SETTINGS['smart_crop'] and SETTINGS['output_format'] == '9:16':
            print(f"  🎯 [Clip #{clip_id}] Running face detection for smart crop...")
            try:
                crop_filter, crop_w, crop_h = get_smart_crop_filter(
                    intermediate_clip,
                    start_time=0.0,
                    duration=clip_duration,
                    sample_every_n=5,
                    output_ratio=(9, 16),
                    dynamic=False
                )
                if crop_filter:
                    render_w = crop_w
                    render_h = crop_h
                    print(f"  ✅ [Clip #{clip_id}] Smart crop ready: {crop_w}x{crop_h}")
                else:
                    crop_h_fallback = inter_h
                    crop_w_fallback = int(inter_h * 9 / 16)
                    crop_w_fallback = crop_w_fallback - (crop_w_fallback % 2)
                    crop_x = (inter_w - crop_w_fallback) // 2
                    crop_filter = f"crop={crop_w_fallback}:{crop_h_fallback}:{crop_x}:0"
                    render_w = crop_w_fallback
                    render_h = crop_h_fallback
            except Exception as track_err:
                print(f"  ⚠️ [Clip #{clip_id}] Face tracking fallback: {track_err}")
                crop_h_fallback = inter_h
                crop_w_fallback = int(inter_h * 9 / 16)
                crop_w_fallback = crop_w_fallback - (crop_w_fallback % 2)
                crop_x = (inter_w - crop_w_fallback) // 2
                crop_filter = f"crop={crop_w_fallback}:{crop_h_fallback}:{crop_x}:0"
                render_w = crop_w_fallback
                render_h = crop_h_fallback

        elif not use_split_screen and SETTINGS['output_format'] == '9:16':
            crop_h_static = inter_h
            crop_w_static = int(inter_h * 9 / 16)
            crop_w_static = crop_w_static - (crop_w_static % 2)
            crop_x = (inter_w - crop_w_static) // 2
            crop_filter = f"crop={crop_w_static}:{crop_h_static}:{crop_x}:0"
            render_w = crop_w_static
            render_h = crop_h_static

        # ─── Step C: Punch-In Zoom Detection ───
        if SETTINGS['output_format'] == '9:16':
            zoom_w, zoom_h = 1080, 1920
        else:
            zoom_w, zoom_h = render_w, render_h

        zoom_filter = None
        if use_gaming_layout and (SETTINGS['punch_in_zoom'] or SETTINGS['ken_burns']):
            print(f"  ℹ️ [Clip #{clip_id}] Punch-in / Ken Burns are off in gaming layout")
        elif SETTINGS['punch_in_zoom'] and os.path.exists(clip_audio):
            print(f"  🔊 [Clip #{clip_id}] Detecting volume spikes for punch-in zoom...")
            try:
                spikes = detect_volume_spikes(clip_audio, temp_dir=temp_dir)
                if spikes:
                    zoom_filter = generate_punchin_filter(
                        spikes, clip_duration, zoom_w, zoom_h,
                        zoom_factor=1.15, ease_duration=0.3
                    )
                    if zoom_filter:
                        print(f"  ✅ [Clip #{clip_id}] Punch-in zoom ready: {len(spikes)} spike(s)")
            except Exception as fx_err:
                print(f"  ⚠️ [Clip #{clip_id}] Punch-in detection failed: {fx_err}")

        # ─── Step D: Ken Burns Slow Zoom ───
        if not use_gaming_layout and not zoom_filter and SETTINGS['ken_burns'] and not SETTINGS['punch_in_zoom']:
            print(f"  🎬 [Clip #{clip_id}] Generating Ken Burns slow zoom...")
            try:
                zoom_filter = generate_kenburns_filter(
                    clip_duration, zoom_w, zoom_h,
                    start_zoom=1.0, end_zoom=1.05, fps=inter_fps
                )
                if zoom_filter:
                    print(f"  ✅ [Clip #{clip_id}] Ken Burns ready")
            except Exception as kb_err:
                print(f"  ⚠️ [Clip #{clip_id}] Ken Burns failed: {kb_err}")

        # ─── Step E: Transcribe clip for word-level captions ───
        all_words = []
        ass_path = None
        if SETTINGS['auto_captions']:
            if full_words:
                for w in full_words:
                    if w['end'] > clip_start and w['start'] < clip_end:
                        rebased_start = round(max(0.0, w['start'] - clip_start), 3)
                        rebased_end = round(min(clip_duration, max(rebased_start + 0.05, w['end'] - clip_start)), 3)
                        all_words.append({
                            'word': w['word'].strip(),
                            'start': rebased_start,
                            'end': rebased_end,
                        })
                if all_words:
                    print(f"  ⚡ [Clip #{clip_id}] Sliced {len(all_words)} cached word timestamps from master transcript.")

            if not all_words and os.path.exists(clip_audio):
                whisper_tier = SETTINGS.get('whisper_model', 'small').lower().strip()
                if whisper_tier not in ('tiny', 'base', 'small', 'medium', 'large-v3'):
                    whisper_tier = 'small'
                whisper_task = 'translate' if SETTINGS.get('language_mode') == 'translate_en' else 'transcribe'
                print(f"  📝 [Clip #{clip_id}] Transcribing clip with word-level timestamps (task={whisper_task})...")
                try:
                    with WHISPER_LOCK:
                        clip_segments, _ = whisper_model.transcribe(
                            clip_audio, beam_size=5, word_timestamps=True, task=whisper_task
                        )
                        for seg in clip_segments:
                            if seg.words:
                                for w in seg.words:
                                    all_words.append({
                                        'word': w.word.strip(),
                                        'start': w.start,
                                        'end': w.end,
                                    })
                except Exception as clip_w_err:
                    print(f"  ⚠️ [Clip #{clip_id}] Whisper transcription error ({clip_w_err}), attempting CPU fallback...")
                    try:
                        cpu_model = WhisperModel(whisper_tier, device='cpu', compute_type='int8')
                        clip_segments, _ = cpu_model.transcribe(
                            clip_audio, beam_size=5, word_timestamps=True, task=whisper_task
                        )
                        for seg in clip_segments:
                            if seg.words:
                                for w in seg.words:
                                    all_words.append({
                                        'word': w.word.strip(),
                                        'start': w.start,
                                        'end': w.end,
                                    })
                    except Exception as cpu_err:
                        print(f"  ⚠️ [Clip #{clip_id}] Subtitle generation skipped: {cpu_err}")

            print(f"  [Clip #{clip_id}] Found {len(all_words)} words for captions.")

            if all_words:
                words_json_path = os.path.join(temp_dir, f"clip_{clip_id}_words.json")
                with open(words_json_path, 'w', encoding='utf-8') as f:
                    json.dump(all_words, f, ensure_ascii=False, indent=2)
                print(f"  💾 Saved transcript JSON for editor: {words_json_path}")

                sub_w = 1080 if SETTINGS['output_format'] == '9:16' else render_w
                sub_h = 1920 if SETTINGS['output_format'] == '9:16' else render_h

                ass_path = os.path.join(temp_dir, f"clip_{clip_id}.ass")
                num_events = generate_ass_subtitles(
                    all_words, ass_path, sub_w, sub_h,
                    style_preset=SETTINGS.get('caption_style', 'yellow_pop'),
                    font_family=SETTINGS.get('caption_font', 'Arial Black'),
                    # Gaming layout: captions always sit in the blurred area under the gameplay
                    position='bottom' if use_gaming_layout else SETTINGS.get('caption_position', 'bottom'),
                    layout_mode=SETTINGS.get('caption_layout', 'two_line'),
                    mask_swears=bool(SETTINGS.get('clean_captions'))
                )
                print(f"  [Clip #{clip_id}] Generated {num_events} caption events.")

        # ─── Step E.5: Emoji Overlay ───
        emoji_overlay_data = None
        if SETTINGS['emoji_overlays'] and all_words:
            print(f"  😄 [Clip #{clip_id}] Scanning transcript for emoji triggers...")
            try:
                emoji_events = scan_transcript_for_emojis(all_words)
                if emoji_events:
                    emoji_temp = os.path.join(temp_dir, f'emoji_{clip_id}')
                    overlay_w = 1080 if SETTINGS['output_format'] == '9:16' else render_w
                    overlay_h = 1920 if SETTINGS['output_format'] == '9:16' else render_h
                    emoji_overlay_data = generate_emoji_overlay_data(
                        emoji_events, overlay_w, overlay_h, temp_dir=emoji_temp
                    )
                    if emoji_overlay_data:
                        print(f"  ✅ [Clip #{clip_id}] Emoji overlay ready: {len(emoji_events)} emoji(s)")
            except Exception as emoji_err:
                print(f"  ⚠️ [Clip #{clip_id}] Emoji overlay failed: {emoji_err}")

        # ─── Step F: Build composite FFmpeg filter chain ───
        filters = []
        if not use_split_screen and not use_gaming_layout:
            if crop_filter:
                filters.append(crop_filter)
            if SETTINGS['output_format'] == '9:16':
                filters.append("scale=1080:1920:force_original_aspect_ratio=decrease")
                filters.append("pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black")

        if zoom_filter:
            filters.append(zoom_filter)

        if ass_path and os.path.exists(ass_path):
            ass_ffmpeg = ffmpeg_escape_path(ass_path)
            filters.append(f"ass='{ass_ffmpeg}'")

        # ─── Step G: Render with FFmpeg ───
        if use_split_screen or use_gaming_layout:
            layout_fc = gaming_info['filter_complex'] if use_gaming_layout else split_filter_complex
            extra_vf = []
            if ass_path and os.path.exists(ass_path):
                ass_ffmpeg = ffmpeg_escape_path(ass_path)
                extra_vf.append(f"ass='{ass_ffmpeg}'")

            full_fc = layout_fc
            if extra_vf:
                extra_chain = ",".join(extra_vf)
                full_fc = layout_fc.replace('[outv]', f'[_splitraw];[_splitraw]{extra_chain}[outv]')

            ffmpeg_cmd = (
                f'ffmpeg -i "{intermediate_clip}" '
                f'-filter_complex "{full_fc}" '
                f'-map "[outv]" -map 0:a '
                f'{encoder_flags} -c:a aac -b:a 128k -movflags +faststart '
                f'"{output_clip}" -y'
            )
            layout_name = 'gaming layout' if use_gaming_layout else 'split-screen'
            print(f"  🎬 [Clip #{clip_id}] Encoding {layout_name}...")
            encode_result = run_ffmpeg(ffmpeg_cmd)
            if encode_result.returncode != 0:
                print(f"  ⚠️ [Clip #{clip_id}] {layout_name} encode failed, falling back to normal crop")
                print(f"     {(encode_result.stderr or '')[-600:]}")
                crop_h_fb = inter_h
                crop_w_fb = int(inter_h * 9 / 16)
                crop_w_fb = crop_w_fb - (crop_w_fb % 2)
                crop_x_fb = (inter_w - crop_w_fb) // 2
                fb_vf = f"crop={crop_w_fb}:{crop_h_fb}:{crop_x_fb}:0,scale=1080:1920"
                run_ffmpeg(
                    f'ffmpeg -i "{intermediate_clip}" -vf "{fb_vf}" {encoder_flags} -c:a aac -b:a 128k -movflags +faststart "{output_clip}" -y'
                )

        elif emoji_overlay_data:
            non_ass_filters = [f for f in filters if not f.startswith("ass=")]
            ass_filter = next((f for f in filters if f.startswith("ass=")), None)
            vf_chain = ",".join(non_ass_filters) if non_ass_filters else "null"

            emoji_inputs = "".join([f' -i "{png}"' for png in emoji_overlay_data['input_files']])
            fc_parts = [f"[0:v]{vf_chain}[vemoji_in]"] + emoji_overlay_data['filter_parts']
            final_label = emoji_overlay_data['final_label']
            if ass_filter:
                fc_parts.append(f"[{final_label}]{ass_filter}[vfinal]")
                final_label = "vfinal"

            filter_complex = ";".join(fc_parts)
            ffmpeg_cmd = (
                f'ffmpeg -i "{intermediate_clip}"{emoji_inputs} '
                f'-filter_complex "{filter_complex}" '
                f'-map "[{final_label}]" -map 0:a '
                f'{encoder_flags} -c:a aac -b:a 128k -movflags +faststart '
                f'"{output_clip}" -y'
            )
            print(f"  🎬 [Clip #{clip_id}] Encoding with effects + emojis...")
            encode_result = run_ffmpeg(ffmpeg_cmd)
            if encode_result.returncode != 0:
                print(f"  ⚠️ [Clip #{clip_id}] Emoji encode failed, falling back to standard filters...")
                vf_string = ",".join(filters) if filters else "null"
                run_ffmpeg(f'ffmpeg -i "{intermediate_clip}" -vf "{vf_string}" {encoder_flags} -c:a aac -b:a 128k -movflags +faststart "{output_clip}" -y')

        elif filters:
            vf_string = ",".join(filters)
            ffmpeg_cmd = (
                f'ffmpeg -i "{intermediate_clip}" -vf "{vf_string}" {encoder_flags} '
                f'-c:a aac -b:a 128k -movflags +faststart "{output_clip}" -y'
            )
            print(f"  🎬 [Clip #{clip_id}] Encoding with effects...")
            encode_result = run_ffmpeg(ffmpeg_cmd)
            if encode_result.returncode != 0:
                print(f"  ⚠️ [Clip #{clip_id}] Filter encode failed, falling back...")
                run_ffmpeg(f'ffmpeg -i "{intermediate_clip}" {encoder_flags} -c:a aac -b:a 128k -movflags +faststart "{output_clip}" -y')
        else:
            print(f"  📋 [Clip #{clip_id}] No effects enabled, simple encode...")
            run_ffmpeg(f'ffmpeg -i "{intermediate_clip}" {encoder_flags} -c:a aac -b:a 128k -movflags +faststart "{output_clip}" -y')

        # ─── Step G.5: Whip-Pan Transitions ───
        if SETTINGS['whip_pan_transitions'] and os.path.exists(output_clip):
            print(f"  🌀 [Clip #{clip_id}] Applying whip-pan transitions...")
            try:
                transition_output = os.path.join(temp_dir, f"clip_{clip_id}_transitions.mp4")
                t_duration = float(SETTINGS.get('transition_speed', 0.25))
                success = apply_whip_pan_transitions(
                    output_clip, transition_output,
                    transition_duration=t_duration, auto_detect=True, scene_threshold=0.3
                )
                if success and os.path.exists(transition_output):
                    os.replace(transition_output, output_clip)
                    print(f"  ✅ [Clip #{clip_id}] Whip-pan transitions applied")
                elif os.path.exists(transition_output):
                    os.remove(transition_output)
            except Exception as trans_err:
                print(f"  ⚠️ [Clip #{clip_id}] Whip-pan transitions error: {trans_err}")

        # ─── Step G.6: Background Music Mixing ───
        if SETTINGS['background_music'] and SETTINGS.get('bgm_path') and os.path.exists(output_clip):
            bgm_path = SETTINGS['bgm_path']
            if os.path.exists(bgm_path):
                print(f"  🎵 [Clip #{clip_id}] Mixing background music with auto-ducking...")
                try:
                    speech_regions = []
                    if os.path.exists(clip_audio):
                        speech_regions = detect_speech_regions(clip_audio, temp_dir=temp_dir)
                    bgm_output = os.path.join(temp_dir, f"clip_{clip_id}_bgm.mp4")
                    success = mix_background_music(
                        output_clip, bgm_path, bgm_output,
                        speech_regions, clip_duration,
                        music_volume=0.40, duck_volume=0.12
                    )
                    if success and os.path.exists(bgm_output):
                        os.replace(bgm_output, output_clip)
                        print(f"  ✅ [Clip #{clip_id}] Background music mixed")
                    elif os.path.exists(bgm_output):
                        os.remove(bgm_output)
                except Exception as bgm_err:
                    print(f"  ⚠️ [Clip #{clip_id}] BGM error: {bgm_err}")

        # ─── Step G.7: Loudness (-14 LUFS), last so it covers the music mix too ───
        if SETTINGS.get('loudness_normalize', True) and os.path.exists(output_clip):
            try:
                if normalize_loudness(output_clip, temp_dir):
                    print(f"  🔊 [Clip #{clip_id}] Loudness normalised to -14 LUFS")
            except Exception as loud_err:
                print(f"  ⚠️ [Clip #{clip_id}] Loudness error: {loud_err}")

        # ─── Cleanup temp files for this clip ───
        if ass_path and os.path.exists(ass_path):
            os.remove(ass_path)
        if os.path.exists(clip_audio):
            os.remove(clip_audio)
        # Preserve intermediate_clip for instant in-browser subtitle re-rendering (re_render_clip.py)
        emoji_temp = os.path.join(temp_dir, f'emoji_{clip_id}')
        if os.path.isdir(emoji_temp):
            import shutil
            shutil.rmtree(emoji_temp, ignore_errors=True)

        crop_data = {
            'crop_filter': crop_filter,
            'zoom_filter': zoom_filter,
            'use_split_screen': use_split_screen,
            'split_filter_complex': split_filter_complex if use_split_screen else None,
            'render_w': render_w,
            'render_h': render_h,
        }
        if use_gaming_layout:
            crop_data['gaming_layout'] = {
                'cam_box': gaming_info['cam_box'],
                'input_w': gaming_info['input_w'],
                'input_h': gaming_info['input_h'],
                'auto_detected': gaming_info['auto_detected'],
            }
            # Still frame for the "Adjust facecam" editor in the dashboard
            frame_path = os.path.join(output_dir, f"clip_{clip_id}_frame.jpg")
            run_ffmpeg([
                'ffmpeg', '-ss', f"{clip_duration / 2:.2f}", '-i', intermediate_clip,
                '-frames:v', '1', '-q:v', '3', frame_path, '-y'
            ])
        thread_cursor.execute(
            "UPDATE video_clips SET output_path = %s, crop_coordinates_json = %s, status = 'ready' WHERE id = %s",
            (relative_output, json.dumps(crop_data), clip_id)
        )
        thread_db.commit()
        print(f"  ✅ [Clip #{clip_id}] Ready!")
        return True

    except Exception as clip_err:
        print(f"  ❌ Error rendering clip {clip_id}: {clip_err}")
        try:
            thread_cursor.execute("UPDATE video_clips SET status = 'pending' WHERE id = %s", (clip_id,))
            thread_db.commit()
        except Exception:
            pass
        return False
    finally:
        thread_db.close()


# ──────────────────────────────────────────────
# Main Pipeline Execution
# ──────────────────────────────────────────────

def run_pipeline():
    if VIDEO_ID is None:
        # Loaded directly without arguments
        sys.exit(0)

    db = get_db()
    cursor = db.cursor()

    try:
        # 1. Fetch video metadata
        cursor.execute("SELECT * FROM long_videos WHERE id = %s", (VIDEO_ID,))
        video = cursor.fetchone()

        if not video:
            raise Exception(f"Video with id {VIDEO_ID} not found in database.")

        # Override settings from DB if available
        if video.get('processing_settings'):
            try:
                db_settings = json.loads(video['processing_settings'])
                SETTINGS.update(db_settings)
                
                for key in ['full_video_mode', 'smart_crop', 'auto_captions', 'punch_in_zoom', 'ken_burns',
                            'emoji_overlays', 'whip_pan_transitions', 'background_music', 'split_screen',
                            'gaming_layout']:
                    val = SETTINGS.get(key)
                    if isinstance(val, str):
                        SETTINGS[key] = val.lower() in ('true', '1', 'yes')
                    elif isinstance(val, (int, float)):
                        SETTINGS[key] = bool(val)
                        
                print(f"Loaded DB processing settings: {json.dumps(SETTINGS, indent=2)}")
            except Exception as e:
                print(f"Warning: Could not parse DB settings: {e}")

        # 1b. Link import: download a Twitch/Kick VOD (+ Twitch chat) before the normal pipeline.
        # Sparse mode (watchlist): download audio + chat only, then just the picked clip windows.
        sparse = bool(SETTINGS.get('sparse_download')) and bool(SETTINGS.get('source_url'))
        if sparse:
            SETTINGS['stream_moments'] = True
            SETTINGS['full_video_mode'] = False
        chat_only = False
        vod_duration = None
        if SETTINGS.get('source_url'):
            try:
                stored_settings = json.loads(video.get('processing_settings') or '{}')
            except (TypeError, ValueError):
                stored_settings = {}
            stored_settings.pop('import_error', None)
            try:
                if sparse:
                    imported = import_vod_sparse(VIDEO_ID, SETTINGS['source_url'])
                else:
                    imported = import_vod(VIDEO_ID, SETTINGS['source_url'])
            except VodImportError as imp_err:
                print(f"\nIMPORT ERROR: {imp_err}")
                stored_settings['import_error'] = str(imp_err)
                cursor.execute("UPDATE long_videos SET status = 'failed', processing_settings = %s WHERE id = %s",
                               (json.dumps(stored_settings), VIDEO_ID))
                db.commit()
                return
            stored_settings.update({
                'chat_status': imported['chat_status'],
                'chat_path': imported['chat_path'],
                'chat_count': imported['chat_count'],
            })
            if sparse:
                stored_settings['audio_status'] = imported['audio_status']
                # Keep the watchlist's "Channel · title" name; only fill in a generic one
                title = (video.get('filename') or '') if stored_settings.get('watchlist') else ''
                title = (title or imported['title'])[:180]
            else:
                title = imported['title'][:180]
            cursor.execute("UPDATE long_videos SET storage_path = %s, filename = %s, processing_settings = %s WHERE id = %s",
                           (imported['path'] or '', title, json.dumps(stored_settings), VIDEO_ID))
            db.commit()
            video['storage_path'] = imported['path'] or ''
            video['filename'] = title
            SETTINGS['chat_path'] = imported['chat_path']
            vod_duration = imported.get('duration')
            chat_only = sparse and not imported['path']

        # Detect hardware configuration
        hw_pref = SETTINGS.get('hardware_accel', 'auto')
        whisper_cfg = get_whisper_config(preferred_accel=hw_pref)
        encoder_name, encoder_flags = detect_ffmpeg_encoder(preferred_accel=hw_pref)
        
        print(f"\n🚀 Hardware Acceleration Status:")
        print(f"   Whisper Device:    {whisper_cfg['device_name']}")
        print(f"   FFmpeg Video Enc:  {encoder_name} ({'Hardware Accelerated' if encoder_name != 'libx264' else 'CPU'})")

        cursor.execute("UPDATE long_videos SET status = 'transcribing' WHERE id = %s", (VIDEO_ID,))
        db.commit()

        # 2. Extract Audio
        audio_path = os.path.join(os.path.dirname(__file__), '..', f'storage/app/temp_{VIDEO_ID}.mp3')
        audio_path = os.path.abspath(audio_path)
        os.makedirs(os.path.dirname(audio_path), exist_ok=True)

        if chat_only:
            print("\nNo audio copy (chat-only fallback): moments come from chat alone; "
                  "each clip is transcribed after its window is downloaded.")
        else:
            print(f"\nExtracting audio from: {video['storage_path']}")
            result = run_ffmpeg([
                'ffmpeg', '-i', video['storage_path'], '-b:a', '64k', '-ac', '1', '-ar', '16000', '-map', 'a', audio_path, '-y'
            ])
            if not os.path.exists(audio_path):
                raise Exception(f"FFmpeg failed to extract audio. stderr: {result.stderr[-500:]}")

            print(f"Audio extracted: {os.path.getsize(audio_path) / 1024:.0f} KB")

        # 3. Transcribe Locally with Faster-Whisper
        whisper_tier = SETTINGS.get('whisper_model', 'small').lower().strip()
        if whisper_tier not in ('tiny', 'base', 'small', 'medium', 'large-v3'):
            whisper_tier = 'small'

        whisper_task = 'translate' if SETTINGS.get('language_mode') == 'translate_en' else 'transcribe'
        print(f"\nTranscribing audio with Faster-Whisper ({whisper_tier} model on {whisper_cfg['device_name']}, task={whisper_task})...")
        
        try:
            whisper_model = WhisperModel(
                whisper_tier,
                device=whisper_cfg['device'],
                compute_type=whisper_cfg['compute_type']
            )
        except Exception as w_init_err:
            print(f"  ⚠️ Whisper GPU initialization failed ({w_init_err}), falling back to CPU (int8)...")
            whisper_model = WhisperModel(whisper_tier, device='cpu', compute_type='int8')

        full_words = []
        moment_candidates = None
        moments_mode = bool(SETTINGS.get('stream_moments')) and not SETTINGS.get('full_video_mode', False)
        if moments_mode:
            # Feature 3: find chat floods + audio spikes first, then transcribe only those windows
            chat_path = SETTINGS.get('chat_path')
            if chat_path and not os.path.exists(chat_path):
                print(f"  ⚠️ Chat log not found at {chat_path}; using audio only.")
                chat_path = None
            clip_count = int(SETTINGS.get('target_clip_count', 3))
            if chat_only:
                if not chat_path or not vod_duration:
                    raise Exception("Chat-only fallback needs the chat log and the VOD length, and one is missing.")
                print(f"\nScanning for stream moments (chat only, no audio pass)...")
                # Flat loudness = no audio spikes, so the score is chat alone
                moment_candidates = detect_moments_from_signals(
                    [-60.0] * int(vod_duration), load_chat(chat_path), clip_count * 2)
                vod_seconds, used_chat = int(vod_duration), True
            else:
                print(f"\nScanning for stream moments ({'chat + audio' if chat_path else 'audio only'})...")
                moment_candidates, vod_seconds, used_chat = detect_moments(audio_path, chat_path, clip_count * 2)
            print(f"  Scanned {vod_seconds}s of {'chat' if chat_only else 'audio'}"
                  f"{' and chat' if used_chat and not chat_only else ''}: {len(moment_candidates)} candidate moments")
            for i, m in enumerate(moment_candidates):
                print(f"   #{i} @ {format_time(m['peak'])} score {m['score']:.2f}: {m['summary']}")
            if not moment_candidates:
                raise Exception("No chat or audio spikes found (the VOD may be silent). Try AI Viral Hooks or Full Video mode.")
            if chat_only:
                transcript_text = ''
                for m in moment_candidates:
                    m['excerpt'] = ''
            else:
                transcript_text, full_words, whisper_model = transcribe_moment_windows(
                    whisper_model, whisper_tier, audio_path, moment_candidates, whisper_task, os.path.dirname(audio_path))
            print(f"Transcription complete. Length: {len(transcript_text)} chars")
            if not transcript_text.strip():
                transcript_text = "[No dialogue detected in moment windows]"
        else:
            try:
                segments_iter, info = whisper_model.transcribe(audio_path, beam_size=5, word_timestamps=True, task=whisper_task)
                transcript_text = ""
                for segment in segments_iter:
                    transcript_text += f"[{format_time(segment.start)} - {format_time(segment.end)}] {segment.text.strip()}\n"
                    if segment.words:
                        for w in segment.words:
                            full_words.append({
                                'word': w.word.strip(),
                                'start': w.start,
                                'end': w.end,
                            })
                print(f"Detected language: {info.language} (probability: {info.language_probability:.2f})")
            except Exception as w_trans_err:
                if ('cublas' in str(w_trans_err).lower() or 'cuda' in str(w_trans_err).lower()) and whisper_cfg.get('device') == 'cuda':
                    print(f"  ⚠️ Whisper CUDA execution failed ({w_trans_err}), falling back to CPU (int8)...")
                    whisper_model = WhisperModel(whisper_tier, device='cpu', compute_type='int8')
                    segments_iter, info = whisper_model.transcribe(audio_path, beam_size=5, word_timestamps=True, task=whisper_task)
                    transcript_text = ""
                    full_words = []
                    for segment in segments_iter:
                        transcript_text += f"[{format_time(segment.start)} - {format_time(segment.end)}] {segment.text.strip()}\n"
                        if segment.words:
                            for w in segment.words:
                                full_words.append({
                                    'word': w.word.strip(),
                                    'start': w.start,
                                    'end': w.end,
                                })
                    print(f"Detected language: {info.language} (probability: {info.language_probability:.2f})")
                else:
                    raise w_trans_err

            print(f"Transcription complete. Length: {len(transcript_text)} chars")

            if not transcript_text.strip():
                if SETTINGS.get('full_video_mode', False):
                    transcript_text = "[No dialogue detected]"
                    print("  ℹ️ Full video mode: No speech detected in audio track, proceeding with visual render.")
                else:
                    raise Exception("Transcription produced empty result — audio may have no speech.")

        cursor.execute("UPDATE long_videos SET transcript = %s WHERE id = %s", (transcript_text, VIDEO_ID))
        db.commit()

        # 4. Analyze — AI Clip Extraction OR Full Video Mode
        cursor.execute("UPDATE long_videos SET status = 'analyzing' WHERE id = %s", (VIDEO_ID,))
        db.commit()

        if SETTINGS.get('full_video_mode', False):
            print("\n🎬 FULL VIDEO MODE — Skipping AI clip extraction.")
            duration_result = run_ffmpeg([
                'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', video['storage_path']
            ])
            try:
                total_seconds = float(duration_result.stdout.strip())
            except Exception:
                raise Exception(f"Could not determine video duration via ffprobe.")

            full_end = format_seconds_ffmpeg(total_seconds)
            print(f"   Video duration: {total_seconds:.2f}s ({full_end})")

            full_meta = {
                'title': 'Full Video Render',
                'virality_score': 90,
                'hook_strength': 90,
                'pacing_energy': 90,
                'shareability': 90,
                'reason': 'Full Video — Subtitles & Rendered Effects',
                'social_caption': 'Full length video with animated dynamic subtitles. 🔥 Watch now!',
                'hashtags': '#fullvideo #content #roninclips #videoediting',
                'shorts_description': 'Full video processed with RoninClips AI.'
            }
            cursor.execute(
                "INSERT INTO video_clips (long_video_id, start_time, end_time, hook_explanation) VALUES (%s, %s, %s, %s)",
                (int(VIDEO_ID), '00:00:00.000', full_end, json.dumps(full_meta, ensure_ascii=False))
            )
            db.commit()
            print(f"   Inserted 1 full-video clip entry.")
        elif moments_mode:
            clip_count = int(SETTINGS.get('target_clip_count', 3))
            excerpt_chars = sum(len(m.get('excerpt') or '') for m in moment_candidates)
            picks = None
            if excerpt_chars < MIN_EXCERPT_CHARS:
                print(f"\nℹ️ Moment windows have almost no speech ({excerpt_chars} chars); titling from chat/audio signals.")
            else:
                print("\nRanking stream moments with the AI (titles & social kit)...")
                raw_response, groq_err = llm_complete(build_moment_prompt(moment_candidates, clip_count), get_groq_models())
                if raw_response is None:
                    print(f"  ⚠️ AI unavailable ({groq_err}); titling from chat/audio signals.")
                else:
                    try:
                        picks = parse_groq_json_response(raw_response)
                    except Exception as parse_err:
                        print(f"  ⚠️ AI JSON parse warning ({parse_err}); titling from chat/audio signals.")

            chosen = merge_moment_picks(moment_candidates, picks, clip_count)
            print(f"Selected {len(chosen)} stream moments.")
            for m, meta in chosen:
                cursor.execute(
                    "INSERT INTO video_clips (long_video_id, start_time, end_time, hook_explanation) VALUES (%s, %s, %s, %s)",
                    (VIDEO_ID, format_seconds_ffmpeg(m['start']), format_seconds_ffmpeg(m['end']),
                     json.dumps(meta, ensure_ascii=False))
                )
            db.commit()
        else:
            print("\nAnalyzing transcript with the AI (Groq, Gemini backup) for virality scoring & social kit...")
            clip_count = int(SETTINGS.get('target_clip_count', 3))
            chunks = split_transcript_into_chunks(transcript_text, max_chars=28000)
            per_chunk_count = max(2, clip_count) if len(chunks) > 1 else clip_count

            groq_models = get_groq_models()

            all_candidates = []
            last_error = None

            for c_idx, chunk_text in enumerate(chunks):
                if len(chunks) > 1:
                    print(f"  📑 Analyzing transcript chunk {c_idx + 1}/{len(chunks)} ({len(chunk_text)} chars)...")

                prompt = f"""Analyze the following video transcript segment. Find up to {per_chunk_count} highly engaging, self-contained clips suitable for short-form viral video (TikTok / Instagram Reels / YouTube Shorts).
Each clip must be between 30 and 60 seconds long.
Use the timestamps from the transcript to determine start and end times.
For each clip, calculate a realistic Virality Score (1-100) with sub-scores, a high-CTR title, engaging social caption with emojis, trending hashtags, and YouTube Shorts description.

Return your answer STRICTLY in JSON format matching this structure without any markdown wrappers or surrounding text:
[
  {{
    "start": "00:01:15",
    "end": "00:02:00",
    "title": "Short Punchy High-CTR Title",
    "virality_score": 94,
    "hook_strength": 96,
    "pacing_energy": 90,
    "shareability": 95,
    "reason": "Why this segment has high viral retention and psychological engagement",
    "social_caption": "Most people get this completely wrong... 😳 Watch until the end to see why. 🔥",
    "hashtags": "#viral #podcast #trending #fyp #mindset",
    "shorts_description": "Search-optimized YouTube Shorts description..."
  }}
]

Transcript:
{chunk_text}"""

                raw_response, chunk_err = llm_complete(prompt, groq_models)
                if chunk_err is not None:
                    last_error = chunk_err

                if raw_response is not None:
                    try:
                        chunk_clips = parse_groq_json_response(raw_response)
                        all_candidates.extend(chunk_clips)
                    except Exception as parse_err:
                        last_error = parse_err
                        print(f"  ⚠️ Chunk {c_idx + 1} JSON parse warning: {parse_err}")

            if not all_candidates:
                raise Exception(f"All AI models (Groq, Gemini backup) failed or returned no valid clips. Last error: {last_error}.")

            # Rank across chunks by virality_score descending and cap to target_clip_count
            if len(chunks) > 1 and len(all_candidates) > clip_count:
                all_candidates.sort(key=lambda c: int(c.get('virality_score', 80)), reverse=True)
                clips = all_candidates[:clip_count]
                clips.sort(key=lambda c: parse_time_to_seconds(c.get('start', '00:00:00')))
            else:
                clips = all_candidates[:clip_count]

            print(f"Found {len(clips)} viral hook candidates with scoring & social kits.")

            for clip in clips:
                meta = {
                    'title': clip.get('title', f"Viral Clip {clip.get('start', '')}"),
                    'virality_score': int(clip.get('virality_score', 88)),
                    'hook_strength': int(clip.get('hook_strength', 90)),
                    'pacing_energy': int(clip.get('pacing_energy', 85)),
                    'shareability': int(clip.get('shareability', 88)),
                    'reason': clip.get('reason', 'High engagement segment'),
                    'social_caption': clip.get('social_caption', ''),
                    'hashtags': clip.get('hashtags', '#viral #shorts #trending'),
                    'shorts_description': clip.get('shorts_description', '')
                }
                cursor.execute(
                    "INSERT INTO video_clips (long_video_id, start_time, end_time, hook_explanation) VALUES (%s, %s, %s, %s)",
                    (VIDEO_ID, clip['start'], clip['end'], json.dumps(meta))
                )
            db.commit()

        # 5. Render Clips with Parallel Processing
        cursor.execute("UPDATE long_videos SET status = 'processing' WHERE id = %s", (VIDEO_ID,))
        db.commit()

        cursor.execute("SELECT * FROM video_clips WHERE long_video_id = %s", (VIDEO_ID,))
        saved_clips = cursor.fetchall()

        output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'storage/app/public'))
        temp_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'storage/app'))
        os.makedirs(output_dir, exist_ok=True)

        if sparse:
            # Fetch only the picked windows at 1080p, each lined up by sound against the scanned audio
            vod_out_dir = os.path.join(temp_dir, 'vods', str(VIDEO_ID))
            ready_clips = []
            for i, sc in enumerate(saved_clips):
                c_start = parse_time_to_seconds(sc['start_time'])
                c_end = parse_time_to_seconds(sc['end_time'])
                print(f"\nDownloading clip window {i + 1}/{len(saved_clips)} "
                      f"({format_time(c_start)}-{format_time(c_end)}, 1080p)...")
                try:
                    src_path, src_offset = fetch_clip_source(
                        SETTINGS['source_url'], SETTINGS.get('source_platform', 'twitch'), vod_out_dir, sc['id'],
                        c_start, c_end, audio_path=video['storage_path'] or None, duration=vod_duration)
                except VodImportError as sec_err:
                    print(f"  ❌ Clip window {i + 1} could not be downloaded, dropping this clip: {sec_err}")
                    cursor.execute("DELETE FROM video_clips WHERE id = %s", (sc['id'],))
                    db.commit()
                    continue
                sc['_src_path'], sc['_src_offset'] = src_path, src_offset
                ready_clips.append(sc)
            if not ready_clips:
                raise Exception("None of the clip windows could be downloaded from Twitch.")
            saved_clips = ready_clips
            src_width, src_height, src_fps = get_video_info(saved_clips[0]['_src_path'])
        else:
            src_width, src_height, src_fps = get_video_info(video['storage_path'])
        print(f"\nSource video: {src_width}x{src_height} @ {src_fps:.1f}fps")
        print(f"Total clips to render: {len(saved_clips)}")

        # Multi-clip parallel execution (max 2 workers to balance CPU/VRAM usage)
        if len(saved_clips) > 1:
            print("⚡ Enabling Parallel Multi-Clip Rendering (2 concurrent workers)...")
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(render_single_clip, sc, video, SETTINGS, whisper_model, encoder_flags, output_dir, temp_dir, full_words)
                    for sc in saved_clips
                ]
                concurrent.futures.wait(futures)
        elif len(saved_clips) == 1:
            render_single_clip(saved_clips[0], video, SETTINGS, whisper_model, encoder_flags, output_dir, temp_dir, full_words)

        cursor.execute("UPDATE long_videos SET status = 'completed' WHERE id = %s", (VIDEO_ID,))
        db.commit()
        if sparse:
            freed = cleanup_sparse_files(VIDEO_ID)
            print(f"🧹 Deleted the audio copy and clip windows ({freed / 1e9:.2f} GB). Chat log kept.")
        print("\n🎉 Pipeline completed successfully!")

    except Exception as e:
        print(f"Pipeline failed: {e}")
        try:
            cursor.execute("UPDATE long_videos SET status = 'failed' WHERE id = %s", (VIDEO_ID,))
            db.commit()
        except Exception:
            pass
    finally:
        if 'audio_path' in locals() and os.path.exists(audio_path):
            os.remove(audio_path)
        db.close()

    print("Pipeline process finished.")

if __name__ == "__main__":
    try:
        run_pipeline()
    except DatabaseUnavailable as db_err:
        print(f"DATABASE ERROR: {db_err}")
        sys.exit(1)
