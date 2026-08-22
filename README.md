# ⚔️ RoninClips — Local AI Video Clipper & Subtitle Engine

> **Extract viral hooks, calculate virality scores, generate social media copy, create animated word-by-word subtitles, and crop to 9:16 vertical video — 100% locally and free.**

Built with **Laravel 12**, **Python 3.10+**, **Faster-Whisper**, **Groq AI** (`openai/gpt-oss-120b`), **MediaPipe Smart Face Tracking**, and **CUDA/FFmpeg**.

---

## ⚡ Quick Start & Installation

Choose the installation method that fits your environment:

### Method A: One-Click Windows Setup (Recommended for Windows)

1. Clone the repository:
   ```cmd
   git clone https://github.com/clascuna556171/roninclips.git
   cd roninclips
   ```
2. Double-click **`setup.bat`** (or run `setup.bat` in your terminal).
   - *Automatically verifies prerequisites, creates `.env`, configures SQLite, creates an isolated Python `.venv`, installs dependencies, and runs database migrations.*
3. Open `.env` and paste your free [Groq API Key](https://console.groq.com):
   ```ini
   GROQ_API_KEY="gsk_your_groq_api_key_here"
   ```
4. Double-click **`start.bat`** to launch the dashboard at **http://127.0.0.1:8000**!

---

### Method B: One-Line PowerShell Command (Windows)

Paste this command into your PowerShell terminal:
```powershell
iwr -useb https://raw.githubusercontent.com/clascuna556171/roninclips/main/install.ps1 | iex
```

---

### Method C: Manual Installation (macOS / Linux / WSL / Windows)

```bash
# 1. Clone the repository
git clone https://github.com/clascuna556171/roninclips.git
cd roninclips

# 2. Environment configuration
cp .env.example .env
php artisan key:generate

# 3. Add your Groq API key in .env
# Edit .env and set: GROQ_API_KEY="gsk_..."

# 4. Install PHP and Python dependencies
composer install
python -m venv processor/.venv
# On Windows: processor\.venv\Scripts\pip install -r processor/requirements.txt
# On macOS/Linux: processor/.venv/bin/pip install -r processor/requirements.txt

# 5. Database setup (Zero-config SQLite default)
touch database/database.sqlite
php artisan migrate

# 6. Start the server
php artisan serve
```
Open **http://127.0.0.1:8000** in your browser.

---

## 📋 System Prerequisites

Ensure the following tools are installed on your system:

| Dependency | Minimum Version | Installation Command |
| :--- | :--- | :--- |
| **PHP** | `8.2+` (with `pdo_sqlite`, `fileinfo`, `curl`, `mbstring`) | `winget install PHP.PHP.8.3` / `brew install php` / `apt install php-cli php-sqlite3` |
| **Composer** | `2.x` | [getcomposer.org](https://getcomposer.org/download/) / `brew install composer` |
| **Python** | `3.10+` | [python.org](https://www.python.org/downloads/) / `brew install python` |
| **FFmpeg** | `5.0+` (added to System `PATH`) | `winget install Gyan.FFmpeg` / `brew install ffmpeg` / `apt install ffmpeg` |
| **Groq Cloud API Key** | Free tier | Get an instant free API key at [console.groq.com](https://console.groq.com) |

> [!TIP]
> **GPU Acceleration**: If you have an NVIDIA GPU (RTX / GTX), install the [NVIDIA CUDA Toolkit 12.x](https://developer.nvidia.com/cuda-downloads). RoninClips will automatically detect CUDA and enable GPU transcription and `h264_nvenc` encoding for 5x–10x faster processing!

---

## 🚀 Key Features

### 1. 📈 AI Virality Scoring & Social Media Posting Kit
- **1-100 Virality Scoring**: Powered by Groq's high-capacity LLMs (`openai/gpt-oss-120b`, `qwen/qwen3.6-27b`).
- **3-Bar Metric Breakdown**: Evaluates **Hook Strength** (first 3s pattern interrupt), **Pacing Flow** (audio cadence), and **Shareability Factor**.
- **1-Click Social Media Kit**: Auto-generates high-CTR video titles, formatted TikTok / Instagram Reels captions with emojis, trending hashtags, and YouTube Shorts descriptions.
- **Batch Export**: `[ COPY ALL POSTS ]` compiles all clips from a video into a single structured drop.

### 2. 🟡 Dynamic Animated Subtitles & Live Preview Simulator
- **Word-by-Word Highlighted Pop**: Synchronized subtitle highlights inspired by Opus Clip and Alex Hormozi.
- **6 Viral ASS Style Presets**: `Yellow Pop`, `Neon Cyan`, `Bold White`, `Hormozi Style`, `Karaoke Lime`, and `Cyber Pink`.
- **Live 9:16 Phone Simulator**: Interactive widget updates subtitle fonts, positions (top, center, bottom), colors, and layouts in real-time.

### 3. 🛡️ Social Media Safe-Zone HUD Overlays
- Real-time interactive guides for **TikTok**, **Instagram Reels**, and **YouTube Shorts** inside the full-screen cinema player.
- Visual bounding boxes ensure your text, face, and subtitles never get obscured by platform UI like like/comment buttons or captions.

### 4. 🌐 Multi-Language Offline Speech Translation
- Select **Auto-Detect** for native language subtitling or **Auto-Translate to English Subtitles** to automatically translate Spanish, Japanese, French, German, and 90+ languages into fluent English subtitles offline with Faster-Whisper without extra API fees.

### 5. ✏️ Word-Level Transcript Editor & Instant Re-Renderer
- Fix any speech mispronunciation or custom brand names in the interactive transcript word grid.
- Re-generates `.ass` subtitles and re-burns the clip in seconds without re-running transcription or AI analysis.

### 6. 🎯 Smart Face Tracking & Split-Screen
- **Smart 9:16 Auto-Crop**: MediaPipe BlazeFace tracking keeps the active speaker centered in the vertical frame with exponential smoothing.
- **Podcast Split-Screen**: Detects dual-speaker conversations and automatically stacks them into top/bottom vertical split panels.

### 7. 🌀 Creative Effects & Audio Ducking
- **Punch-In Dynamic Zoom**: Automatic 1.15x cut on vocal climax volume spikes.
- **Ken Burns Motion**: Smooth continuous zoom-in.
- **Emoji Overlays**: Keyword-triggered animated emoji popups.
- **BGM Auto-Ducking**: Automatically ducks background music during dialogue and boosts volume during pauses.

---

## ⚙️ Environment Configuration (`.env`)

```ini
# Database: Zero-config SQLite default (or switch to mysql)
DB_CONNECTION=sqlite

# Groq Cloud API Configuration (https://console.groq.com)
GROQ_API_KEY="gsk_your_key_here"

# Optional: Lock in a specific model (Default: auto-probes live active models)
GROQ_MODEL=openai/gpt-oss-120b
```

---

## ❓ Troubleshooting & FAQs

<details>
<summary><strong>Q: 'ffmpeg' is not recognized as an internal or external command</strong></summary>

**Solution**: Install FFmpeg and add it to your system PATH.
- On Windows: Run `winget install Gyan.FFmpeg` in PowerShell, then restart your terminal.
- On macOS: Run `brew install ffmpeg`.
- On Linux (Ubuntu/Debian): Run `sudo apt update && sudo apt install ffmpeg`.
</details>

<details>
<summary><strong>Q: PHP extension 'pdo_sqlite' or 'fileinfo' is missing</strong></summary>

**Solution**: Open your `php.ini` file and uncomment the following lines (remove leading `;`):
```ini
extension=pdo_sqlite
extension=sqlite3
extension=fileinfo
extension=curl
extension=mbstring
extension=openssl
```
</details>

<details>
<summary><strong>Q: How do I switch to MySQL instead of SQLite?</strong></summary>

**Solution**: Edit your `.env` file:
```ini
DB_CONNECTION=mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_DATABASE=roninclips
DB_USERNAME=root
DB_PASSWORD=your_password
```
Then run: `php artisan migrate`
</details>

---

## 📚 Codebase Architecture & Navigation

For a complete breakdown of every file, pipeline lifecycle, database schema, and architectural diagrams, refer to the [Master Codebase Map (CODETREE.md)](file:///c:/Users/Sebaz/roninclips/CODETREE.md).

---

## 📄 License
Licensed under the [MIT License](LICENSE).
