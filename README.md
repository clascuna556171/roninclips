# ⚔️ RoninClips — Local AI Video Clipper & Subtitle Engine

> **Extract viral hooks, generate word-by-word animated captions, apply smart face cropping, and edit full videos locally — 100% offline & free.**

Built by **Christian Lascuna** with **Laravel**, **Python**, **Faster-Whisper**, **Groq AI**, and **FFmpeg**.

---

## ⚡ Quick Start & Installation Commands

You can install and launch RoninClips using any of the single terminal command methods below:

### Method A: One-Line Terminal Command (PowerShell)
Paste this command into your PowerShell terminal:
```powershell
iwr -useb https://raw.githubusercontent.com/clascuna556171/roninclips/main/install.ps1 | iex
```

---

### Method B: NPX / NPM Global Command
If you have Node.js installed, you can launch RoninClips with `npx`:
```bash
npx roninclips
```
Or install it globally so you can type `roninclips` anywhere in your terminal:
```bash
npm install -g roninclips
roninclips
```

---

### Method C: One-Click Local Script
1. Clone the repository: `git clone https://github.com/clascuna556171/roninclips.git`
2. Double-click `setup.bat` to install.
3. Double-click `start.bat` to run!

---

## 🚀 Features

- ✂️ **Viral Hook Extraction (Groq AI)**: Analyzes video transcripts to identify high-engagement 30–60s clip candidates.
- 🎬 **Full Video Subtitles Mode**: Process entire videos without clip cutting — perfect for long-form subtitling.
- 🟡 **Dynamic Animated Subtitles**: Word-by-word pop animations, customizable colors (`Yellow Pop`, `Neon Cyan`, `Bold White`), fonts (`Arial Black`, `Impact`, `Trebuchet MS`, `Verdana`, `Montserrat`), positions, and layout modes.
- 🎯 **Smart Face Tracking & 9:16 Crop**: OpenCV face detection centers speakers for vertical shorts/reels.
- 👥 **Split-Screen Mode**: Automatically split multi-speaker podcasts into vertical split panels.
- 🌀 **Whip-Pan Transitions & Motion FX**: Multi-directional transition cuts, volume spike punch-in zooms, and Ken Burns motion.
- 😄 **Automatic Emoji Overlays**: Scans transcript keywords for automatic animated emoji triggers.
- 🎵 **Background Music Mixer**: Ducking BGM support.

---

## 🛠️ Manual Installation (macOS / Linux / WSL)

```bash
# 1. Clone repository
git clone https://github.com/your-username/roninclips.git
cd roninclips

# 2. Environment setup
cp .env.example .env
php artisan key:generate

# 3. Install dependencies
composer install
pip install -r processor/requirements.txt

# 4. Run database migrations
php artisan migrate

# 5. Start development server
php artisan serve
```

---

## 📄 License
Licensed under the [MIT License](LICENSE).
