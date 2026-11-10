# ⚔️ RoninClips — Master Architecture Blueprint & Context (`PROJECTCONTEXT.MD`)

> **CORE CONSTRAINT:** This project is **100% free and local-first with zero recurring fees or paid cloud services.**
> All video transcription, face tracking, and rendering execute locally on the host machine using Faster-Whisper, MediaPipe, and FFmpeg with free-tier Groq LLMs for viral hook detection.

---

## ⚡ 1. System Architecture Overview

RoninClips is structured as a coordinated local ecosystem:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          USER / BROWSER INTERFACE                           │
│     Web Dashboard (Blade + Vanilla CSS + Offline Lucide + Live Polling)     │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTP POST / GET / AJAX
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      LARAVEL 12/13 CONTROLLER & ORCHESTRATION               │
│   • VideoController: store, retry, getLogs, openExplorer, getClipStatus,    │
│     getTranscript, reRenderClip, destroy, destroyClip                       │
│   • Automatic storage cleanup & non-blocking background process spawning    │
└──────────────────┬───────────────────────────────────────┬──────────────────┘
                   │ SQL (Read/Write State)                │ Spawns Worker Process
                   ▼                                       ▼
┌──────────────────────────────────────┐  ┌───────────────────────────────────┐
│        DATABASE (SQLITE / MYSQL)     │  │      PYTHON PROCESSING ENGINE     │
│   • long_videos (Metadata, Settings) │  │  • engine.py (Single-Pass Whisper)│
│   • video_clips (Timestamps, Paths)  │  │  • face_tracker.py (MediaPipe)    │
│   • db_helper.py (Unified Interface) │  │  • split_screen.py (Podcasts)     │
└──────────────────────────────────────┘  │  • audio_mixer.py (RMS Ducking)   │
                                          │  • effects.py (Punch-In/KenBurns) │
                                          │  • emoji_overlay.py (Pillow/PNG)  │
                                          │  • transitions.py (Whip-Pan)      │
                                          │  • subtitles.py (ASS Subtitles)   │
                                          │  • re_render_clip.py (Editor)     │
                                          └───────────────────────────────────┘
```

1. **Frontend & Control Center (Laravel):**
   - High-density dark glassmorphic creator studio (`resources/views/dashboard.blade.php`).
   - Drag-and-drop local path ingestion with native Windows file picker dialog support.
   - Dynamic hardware badge (`CUDA GPU` vs `CPU ENGINE`) and active job telemetry.
   - Real-time progress bar and live terminal log streamer (`GET /videos/{id}/logs`).
   - Lightbox video preview with TikTok/Reels/Shorts 9:16 safe-zone bounding boxes.
   - In-browser word-level transcript editor with live status polling (`GET /clips/{clip}/status`).
   - 1-click retry button for failed processing jobs (`POST /videos/{video}/retry`).

2. **Data & Storage Layer:**
   - **Zero-config SQLite default** (`database/database.sqlite`) with automatic MySQL fallback support via `processor/db_helper.py` and Laravel Eloquent models (`LongVideo`, `VideoClip`).
   - Stores source video file paths, processing settings JSON, transcript text, AI-generated hook explanations, virality scores, and crop coordinates.
   - Automatic disk cleanup (`cleanupClipFiles`) prevents orphaned `.mp4`, `.ass`, `.json`, and log files from accumulating.

3. **Core Processing Engine (Python 3.10+):**
   - **Audio Extraction:** High-speed FFmpeg stream copy/extract to `storage/app/temp_{video_id}.mp3`.
   - **Single-Pass Whisper Transcription:** Runs local `faster-whisper` (`WhisperModel`) once with `word_timestamps=True` on GPU (float16) or CPU (int8), slicing word timings per clip to cut runtime in half.
   - **Multi-Chunk Groq Hook Discovery:** Splits full-length transcripts into 28,000-character windows, queries free-tier Groq LLMs (`openai/gpt-oss-120b`, `llama-3.3-70b-versatile`), and aggregates the highest `virality_score` clips.
   - **Frame-Accurate Intermediate Clips:** Cuts lossless source segments (`storage/app/intermediate_{clip_id}.mp4`) to prevent audio/video drift.
   - **Visual & Audio Enhancements:** MediaPipe BlazeFace smart 9:16 crop, dual-speaker podcast split-screen, RMS volume spike punch-in zoom, Ken Burns subtle motion, dynamic RMS auto-ducked background music, Pillow emoji overlays, and directional whip-pan transitions.
   - **Shared Animated Subtitles:** Word-by-word highlighted Advanced SubStation Alpha (`.ass`) subtitle generation via `processor/subtitles.py` with ASS tag and punctuation sanitization.
   - **In-Browser Re-renderer (`processor/re_render_clip.py`):** Re-burns ASS subtitles and re-mixes BGM onto existing intermediate clips in seconds without re-running transcription or AI analysis.

---

## 🛠️ 2. Key Directories & Core Files

| File / Directory | Role & Description |
| :--- | :--- |
| `app/Http/Controllers/VideoController.php` | Orchestrates pipeline dispatch, retry flow, log streaming, and clip cleanup. |
| `resources/views/dashboard.blade.php` | Creator studio layout, TUI HUD, safe-zone preview modal, and transcript editor. |
| `processor/engine.py` | Pipeline orchestrator (Audio extract, Whisper, Groq, intermediate clips, effects). |
| `processor/re_render_clip.py` | Fast in-browser subtitle and BGM re-renderer for edited clips. |
| `processor/subtitles.py` | Shared ASS subtitle generator, palette definitions, and FFmpeg path escaping. |
| `processor/audio_mixer.py` | Speech region detection (RMS energy) and dynamic BGM volume ducking. |
| `processor/effects.py` | Volume spike punch-in zoom and Ken Burns pan filters. |
| `processor/face_tracker.py` | MediaPipe BlazeFace short-range face tracking for dynamic 9:16 crop. |
| `processor/split_screen.py` | Podcast two-speaker dual-crop vertical 9:16 filter complex. |
| `processor/hw_accel.py` | Hardware detection for NVIDIA CUDA fp16 and FFmpeg NVENC/QSV/AMF encoders. |
| `processor/db_helper.py` | Unified database abstraction layer supporting SQLite and MySQL. |
| `public/js/lucide.min.js` | Local bundled Lucide icons for 100% offline air-gapped readiness. |
| `tests/Feature/ExampleTest.php` | Laravel Pest feature tests (dashboard, validation, status, retry, cleanup). |
| `tests/python/test_processor.py` | Python unittest suite (subtitles, filters, Groq parsing, chunking, timestamps). |

---

## ⚡ 3. Critical Implementation Rules

1. **Local-First & Offline:**
   - Do not add paid external APIs or cloud storage requirements.
   - All styling, icons, and fonts must render immediately without blocking on external CDN connections.
2. **Intermediate Clip Preservation:**
   - Always preserve `storage/app/intermediate_{clip_id}.mp4` while a clip exists so transcript edits can re-render in seconds.
   - Delete intermediate clips only when the clip or parent video is deleted via `VideoController::cleanupClipFiles`.
3. **Shell-Safe Subprocesses:**
   - Pass argument arrays (`shell=False`) in Python subprocess execution.
   - Sanitize and escape all file paths and arguments passed to Windows/Linux command shells.
