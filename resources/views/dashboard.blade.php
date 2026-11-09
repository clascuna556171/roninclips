<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RoninClips — Local AI Video Clipper</title>
    <link rel="stylesheet" href="{{ asset('css/app.css') }}?v={{ file_exists(public_path('css/app.css')) ? filemtime(public_path('css/app.css')) : 1 }}">
    <!-- Local Lucide Icons Bundle (100% Offline Ready) -->
    <script src="{{ asset('js/lucide.min.js') }}"></script>
</head>
<body>

    <!-- ─── Main Two-Column Workspace (No Top Navbar) ─── -->
    <div class="studio-workspace">

        <!-- ─── Left Sidebar: Ingestion & Pipeline Controls ─── -->
        <aside class="studio-sidebar">
            
            <!-- ASCII Hero Wordmark & TUI Mockup -->
            <div class="hero-tui-mockup">
                <div class="tui-ascii">
 ____             _        ____ _ _           
|  _ \ ___  _ __ (_)_ __  / ___| (_)_ __  ___ 
| |_) / _ \| '_ \| | '_ \| |   | | | '_ \/ __|
|  _ < (_) | | | | | | | | |___| | | |_) \__ \
|_| \_\___/|_| |_|_|_| |_|\____|_|_| .__/|___/
                                   |_|        
                </div>
                <h1 class="display-xl">Extract Viral Hooks Locally.</h1>
                <p class="body-md">Run your video processing pipeline completely offline with <span class="body-strong">Groq AI</span> & <span class="body-strong">CUDA FFmpeg</span>.</p>
            </div>

            <!-- Developer Attribution Box -->
            <div class="about-us-section">
                <div class="about-us-title">[ ABOUT US ]</div>
                <div class="about-us-content">
                    <p>I built RoninClips to have access to a premium clipping tool for myself, running completely locally and for free.</p>
                    <p class="about-creator">Created by <strong>Christian Lascuna</strong></p>
                </div>
            </div>

            <!-- Real-Time Hardware & Model System Status Badges -->
            <div class="sidebar-hud-row">
                <div class="hud-pill hud-pill-cuda" title="Acceleration Engine">
                    <i data-lucide="cpu" class="icon-sm"></i>
                    <span>{{ $hwBadge ?? 'CUDA GPU' }}</span>
                </div>
                <div class="hud-pill hud-pill-llm" title="Active Groq LLM Model">
                    <i data-lucide="bot" class="icon-sm"></i>
                    <span>{{ $groqModel ?? 'openai/gpt-oss-120b' }}</span>
                </div>
                <div class="hud-pill hud-pill-db" title="Database Driver">
                    <i data-lucide="database" class="icon-sm"></i>
                    <span>DB: {{ strtoupper($dbDriver ?? 'sqlite') }}</span>
                </div>
                @if(($activeJobsCount ?? 0) > 0)
                    <div class="hud-pill hud-pill-jobs" title="Videos currently in pipeline">
                        <span class="spinner" style="width: 8px; height: 8px;"></span>
                        <span>{{ $activeJobsCount }} ACTIVE</span>
                    </div>
                @endif
            </div>

            @if(session('success'))
                <div style="background: rgba(48, 209, 88, 0.15); border: 1px solid rgba(48, 209, 88, 0.4); color: #30d158; padding: 8px 10px; border-radius: 4px; font-size: 11px;">
                    {{ session('success') }}
                </div>
            @endif
            @if(session('error'))
                <div style="background: rgba(255, 59, 48, 0.15); border: 1px solid rgba(255, 59, 48, 0.4); color: #ff3b30; padding: 8px 10px; border-radius: 4px; font-size: 11px;">
                    {{ session('error') }}
                </div>
            @endif

            <form action="{{ route('videos.store') }}" method="POST" id="pipeline-form">
                @csrf

                <!-- One-Click Presets -->
                <div class="presets-section">
                    <div class="presets-header-title">
                        <span>[ STRATEGY PRESETS ]</span>
                    </div>
                    <div class="presets-grid">
                        <button type="button" class="preset-card-btn" onclick="applyPreset('tiktok_viral', this)">
                            <strong><i data-lucide="smartphone" class="icon-sm" style="margin-right: 4px; color: #38bdf8;"></i> TikTok Viral</strong>
                            <small>9:16 + Smart Crop + Yellow Pop</small>
                        </button>
                        <button type="button" class="preset-card-btn" onclick="applyPreset('full_video', this)">
                            <strong><i data-lucide="film" class="icon-sm" style="margin-right: 4px; color: #bf5af2;"></i> Full Video</strong>
                            <small>Original + Subtitles only</small>
                        </button>
                        <button type="button" class="preset-card-btn" onclick="applyPreset('podcast_split', this)">
                            <strong><i data-lucide="mic" class="icon-sm" style="margin-right: 4px; color: #30d158;"></i> Podcast Mode</strong>
                            <small>9:16 + Split Screen Speaker</small>
                        </button>
                        <button type="button" class="preset-card-btn" onclick="applyPreset('fast_action', this)">
                            <strong><i data-lucide="flame" class="icon-sm" style="margin-right: 4px; color: #ff9f0a;"></i> Fast Action</strong>
                            <small>Whip-Pan + Punch-In Zoom</small>
                        </button>
                    </div>
                </div>

                <!-- Video File Path Input / Dropzone -->
                <div class="form-group" style="margin-top: 14px;">
                    <label for="video_path">[ SOURCE VIDEO FILE ]</label>
                    <div class="file-dropzone-box" id="file-dropzone">
                        <input type="text" id="video_path" name="video_path" class="text-input" placeholder="C:\Users\...\podcast.mp4" required>
                        <div class="file-input-actions">
                            <button type="button" class="btn-input-action btn-browse" onclick="triggerBrowseFile(this)" id="btn-browse-file" title="Pick file using native file explorer">
                                <i data-lucide="folder-open" class="icon-sm"></i> BROWSE FILE...
                            </button>
                            <button type="button" class="btn-input-action" onclick="pasteClipboardPath()">
                                <i data-lucide="clipboard" class="icon-sm"></i> PASTE
                            </button>
                            <button type="button" class="btn-input-action" onclick="clearPathInput()">
                                <i data-lucide="x" class="icon-sm"></i> CLEAR
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Pipeline Settings Accordion -->
                <div class="settings-panel">
                    <div class="settings-header" id="settings-toggle" role="button" tabindex="0" aria-expanded="true" aria-controls="settings-body" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();this.click();}">
                        <div style="display: flex; align-items: center; gap: 6px;">
                            <i data-lucide="sliders" class="icon-sm" style="color: #38bdf8;"></i>
                            <span>[ PIPELINE SETTINGS ]</span>
                        </div>
                        <span class="toggle-chevron" id="settings-chevron">[-]</span>
                    </div>

                    <div class="settings-body" id="settings-body">

                        <!-- Aspect Ratio & Processing Mode -->
                        <div>
                            <div class="settings-section-title">VIDEO FORMAT & CLIPS</div>
                            <div class="form-group">
                                <label>Aspect Ratio</label>
                                <div class="radio-group">
                                    <label class="radio-label">
                                        <input type="radio" name="output_format" value="9:16" checked id="format_vertical">
                                        <span>9:16 Vertical</span>
                                    </label>
                                    <label class="radio-label">
                                        <input type="radio" name="output_format" value="original" id="format_original">
                                        <span>Original Ratio</span>
                                    </label>
                                </div>
                            </div>
                            <div class="form-group">
                                <label>Processing Pipeline</label>
                                <div class="radio-group">
                                    <label class="radio-label">
                                        <input type="radio" name="processing_mode" value="viral_hooks" checked id="mode_hooks">
                                        <span>AI Viral Hooks</span>
                                    </label>
                                    <label class="radio-label">
                                        <input type="radio" name="processing_mode" value="full_video" id="mode_full">
                                        <span>Full Video</span>
                                    </label>
                                </div>
                            </div>
                            <div class="form-group" id="clip-count-group">
                                <label for="target_clip_count">Target Clip Count</label>
                                <input type="number" id="target_clip_count" name="target_clip_count" min="1" max="10" value="3" class="text-input" style="padding: 5px 8px;">
                            </div>
                        </div>

                        <!-- Language & Local Translation -->
                        <div>
                            <div class="settings-section-title">LANGUAGE & LOCAL TRANSLATION</div>
                            <div class="form-group">
                                <label for="language_mode">Language Mode</label>
                                <select id="language_mode" name="language_mode" class="text-input" style="padding: 5px 8px;">
                                    <option value="auto" selected>🌐 Auto-Detect (Original Audio Language)</option>
                                    <option value="translate_en">🇺🇸 Auto-Translate to English Subtitles (Offline)</option>
                                </select>
                            </div>
                        </div>

                        <!-- Caption Styling & Live Preview Simulator -->
                        <div>
                            <div class="settings-section-title">CAPTIONS & LIVE SIMULATOR</div>
                            <div class="form-group">
                                <label for="caption_style">Caption Highlight Style</label>
                                <select id="caption_style" name="caption_style" class="text-input" style="padding: 5px 8px;">
                                    <option value="yellow_pop" selected>🟡 Yellow Pop (Classic Opus Yellow on White)</option>
                                    <option value="neon_cyan">🔵 Neon Cyan (Cyberpunk Cyan on Off-White)</option>
                                    <option value="bold_white">🟢 Bold White (Minimalist Green Pop)</option>
                                    <option value="hormozi_box">🔴 Hormozi Style (High-Contrast Red / Warm Gold)</option>
                                    <option value="karaoke_green">⚡ Karaoke Lime (MrBeast Vibrant Lime Pop)</option>
                                    <option value="cyber_pink">🟣 Cyber Pink (Electric Magenta & Neon Yellow)</option>
                                    <option value="fire_gold">🔥 Fire Gold (Red-Orange Pop with Gold)</option>
                                    <option value="electric_violet">⚡ Electric Violet (Neon Purple & Crisp White)</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <label for="caption_font">Font Family</label>
                                <select id="caption_font" name="caption_font" class="text-input" style="padding: 5px 8px;">
                                    <option value="Arial Black" selected>Arial Black (Ultra Bold)</option>
                                    <option value="Impact">Impact (Heavy Viral)</option>
                                    <option value="Trebuchet MS">Trebuchet MS (Clean Sans)</option>
                                    <option value="Verdana">Verdana (High Legibility)</option>
                                    <option value="Montserrat">Montserrat / System Sans</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <label for="caption_position">Position</label>
                                <select id="caption_position" name="caption_position" class="text-input" style="padding: 5px 8px;">
                                    <option value="bottom" selected>Bottom (Safe Zone for TikTok/Reels UI)</option>
                                    <option value="center">Center (Eye-Level / Dynamic Focus)</option>
                                    <option value="top">Top (Header Banner)</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <label for="caption_layout">Layout Chunk Size</label>
                                <select id="caption_layout" name="caption_layout" class="text-input" style="padding: 5px 8px;">
                                    <option value="two_line" selected>2-Line Block (Classic Opus/TikTok style)</option>
                                    <option value="single_word">Single Word Pop (1 Word at a time)</option>
                                    <option value="full_line">Full Line (Multi-word phrase block)</option>
                                </select>
                            </div>

                            <!-- Live Visual Subtitle Preview Simulator -->
                            <div class="subs-preview-container">
                                <div class="subs-preview-header">
                                    <span>[ LIVE CAPTION SIMULATOR ]</span>
                                </div>
                                <div class="subs-simulator-screen" id="subs-simulator-screen">
                                    <div class="subs-sim-notch"></div>
                                    <div class="subs-sim-content pos-bottom" id="subs-sim-content">
                                        <span class="sim-word" id="sim-word-1">THIS</span>
                                        <span class="sim-word active-word" id="sim-word-2">HOOK</span>
                                        <span class="sim-word" id="sim-word-3">WILL</span>
                                        <span class="sim-word" id="sim-word-4">GO VIRAL</span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Creative Effects -->
                        <div>
                            <div class="settings-section-title">CREATIVE EFFECTS & AUDIO</div>
                            <div class="toggles-grid">
                                <label class="toggle-label" for="smart_crop">
                                    <input type="checkbox" id="smart_crop" name="smart_crop" value="1" checked class="toggle-checkbox">
                                    <span class="toggle-status"></span>
                                    <span class="toggle-text">
                                        <strong>Face Tracking Smart Crop</strong>
                                        <small>Auto-centers active speaker in 9:16</small>
                                    </span>
                                </label>
                                <label class="toggle-label" for="auto_captions">
                                    <input type="checkbox" id="auto_captions" name="auto_captions" value="1" checked class="toggle-checkbox">
                                    <span class="toggle-status"></span>
                                    <span class="toggle-text">
                                        <strong>Animated Captions</strong>
                                        <small>Word-by-word synchronized subtitles</small>
                                    </span>
                                </label>
                                <label class="toggle-label" for="punch_in_zoom">
                                    <input type="checkbox" id="punch_in_zoom" name="punch_in_zoom" value="1" class="toggle-checkbox">
                                    <span class="toggle-status"></span>
                                    <span class="toggle-text">
                                        <strong>Punch-In Dynamic Zoom</strong>
                                        <small>1.15x cut on audio volume spikes</small>
                                    </span>
                                </label>
                                <label class="toggle-label" for="ken_burns">
                                    <input type="checkbox" id="ken_burns" name="ken_burns" value="1" class="toggle-checkbox">
                                    <span class="toggle-status"></span>
                                    <span class="toggle-text">
                                        <strong>Ken Burns Slow Zoom</strong>
                                        <small>Continuous subtle zoom (1.0x to 1.05x)</small>
                                    </span>
                                </label>
                                <label class="toggle-label" for="emoji_overlays">
                                    <input type="checkbox" id="emoji_overlays" name="emoji_overlays" value="1" class="toggle-checkbox">
                                    <span class="toggle-status"></span>
                                    <span class="toggle-text">
                                        <strong>Emoji Overlays</strong>
                                        <small>Auto-detect keywords & display emojis</small>
                                    </span>
                                </label>
                                <label class="toggle-label" for="whip_pan_transitions">
                                    <input type="checkbox" id="whip_pan_transitions" name="whip_pan_transitions" value="1" class="toggle-checkbox">
                                    <span class="toggle-status"></span>
                                    <span class="toggle-text">
                                        <strong>Whip-Pan Transitions</strong>
                                        <small>Motion-blur scene change cuts</small>
                                    </span>
                                </label>
                                <div class="form-group" id="transition-speed-group" style="display: none; margin: 2px 0 6px 22px;">
                                    <label for="transition_speed" style="font-size: 10px;">Transition Speed</label>
                                    <select id="transition_speed" name="transition_speed" class="text-input" style="padding: 4px 8px;">
                                        <option value="0.15">⚡ 0.15s (Snap Whip)</option>
                                        <option value="0.25" selected>🎬 0.25s (Balanced)</option>
                                        <option value="0.35">🌊 0.35s (Smooth Slide)</option>
                                    </select>
                                </div>
                                <label class="toggle-label" for="background_music">
                                    <input type="checkbox" id="background_music" name="background_music" value="1" class="toggle-checkbox">
                                    <span class="toggle-status"></span>
                                    <span class="toggle-text">
                                        <strong>BGM Auto-Ducking</strong>
                                        <small>Ducks music when speaker talks</small>
                                    </span>
                                </label>
                                <div class="form-group" id="bgm-path-group" style="display: none; margin: 2px 0 6px 22px;">
                                    <label for="bgm_path" style="font-size: 10px;">Background Music File (.mp3/.wav)</label>
                                    <div style="display: flex; gap: 4px;">
                                        <input type="text" id="bgm_path" name="bgm_path" class="text-input" placeholder="C:\Users\...\music.mp3" style="padding: 4px 8px;">
                                        <button type="button" class="btn-input-action btn-browse" onclick="triggerBrowseFile(this, 'bgm_path', 'audio')" title="Browse audio file">
                                            <i data-lucide="music" class="icon-sm"></i> BROWSE
                                        </button>
                                    </div>
                                </div>
                                <label class="toggle-label" for="split_screen">
                                    <input type="checkbox" id="split_screen" name="split_screen" value="1" class="toggle-checkbox">
                                    <span class="toggle-status"></span>
                                    <span class="toggle-text">
                                        <strong>Podcast Split-Screen</strong>
                                        <small>Shows both speakers in stacked panels</small>
                                    </span>
                                </label>
                            </div>
                        </div>

                        <!-- GPU & Whisper Model Tier -->
                        <div>
                            <div class="settings-section-title">PERFORMANCE & GPU</div>
                            <div class="form-group">
                                <label for="hardware_accel">Hardware Acceleration</label>
                                <select id="hardware_accel" name="hardware_accel" class="text-input" style="padding: 5px 8px;">
                                    <option value="auto" selected>⚡ Auto (CUDA GPU & Hardware Encoders)</option>
                                    <option value="cpu">🐢 Force CPU Only (libx264)</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <label for="whisper_model">Whisper Model Tier</label>
                                <select id="whisper_model" name="whisper_model" class="text-input" style="padding: 5px 8px;">
                                    <option value="tiny">Tiny (Ultra Fast ~5s)</option>
                                    <option value="base">Base (Fast Transcription)</option>
                                    <option value="small" selected>Small (Balanced - Recommended)</option>
                                    <option value="medium">Medium (Maximum Accuracy)</option>
                                    <option value="large-v3">Large-v3 (Studio Grade)</option>
                                </select>
                            </div>
                        </div>

                    </div>
                </div>

                <button type="submit" class="button-primary" style="margin-top: 14px;">
                    <i data-lucide="sparkles" class="icon-sm"></i>
                    <span>[ PROCESS VIDEO ]</span>
                </button>
            </form>

            <div style="font-size: 11px; color: var(--color-text-muted); border-top: 1px solid var(--color-border); padding-top: 10px; display: flex; align-items: center; justify-content: space-between;">
                <span>RoninClips v2.4</span>
                <span>By Christian Lascuna</span>
            </div>
        </aside>

        <!-- ─── Right Main Canvas ─── -->
        <main class="studio-canvas">

            @if($videos->isEmpty())
                <div class="empty-state-box">
                    <i data-lucide="video" class="empty-icon"></i>
                    <h3 style="font-size: 15px; font-weight: 800; color: #fff;">[ NO VIDEOS INGESTED YET ]</h3>
                    <p style="font-size: 12px; max-width: 420px; line-height: 1.4;">Select or paste a video path in the left sidebar to extract viral clips and generate animated captions completely offline.</p>
                </div>
            @endif

            <!-- ─── Active Processing Queue ─── -->
            @php
                $activeQueue = $videos->filter(fn($v) => !in_array(strtolower($v->status), ['completed', 'failed']));
            @endphp

            @if($activeQueue->count() > 0)
                <div>
                    <div class="canvas-section-header">
                        <div class="canvas-section-title">
                            <span class="spinner" style="width: 12px; height: 12px; border-top-color: #38bdf8;"></span>
                            <span>[ ACTIVE PROCESSING PIPELINE ]</span>
                            <span style="font-size: 11px; color: #ff9f0a; font-weight: 700;">({{ $activeQueue->count() }} active)</span>
                        </div>
                    </div>

                    @foreach($activeQueue as $video)
                        <div class="video-card" data-video-id="{{ $video->id }}">
                            <div class="folder-header">
                                <div class="folder-title">
                                    <i data-lucide="film" class="icon-sm" style="color: #38bdf8;"></i>
                                    <span>{{ $video->filename }}</span>
                                </div>
                                <div class="folder-meta-group">
                                    <span class="status-badge status-{{ strtolower($video->status) }}">
                                        <span class="spinner"></span>
                                        <span class="status-text">{{ $video->status }}</span>
                                    </span>
                                </div>
                            </div>

                            <div class="folder-content">
                                <!-- Multi-Step Live Progress Tracker -->
                                <div class="step-tracker-container" id="step-tracker-{{ $video->id }}">
                                    @php
                                        $sLower = strtolower($video->status);
                                        $steps = ['transcribing', 'analyzing', 'processing', 'completed'];
                                        $activeIdx = array_search($sLower, $steps);
                                        if ($activeIdx === false) $activeIdx = ($sLower === 'pending' ? -1 : 0);
                                        $initialPercent = match($sLower) {
                                            'pending' => 10,
                                            'transcribing' => 25,
                                            'analyzing' => 50,
                                            'processing' => 75,
                                            'completed' => 100,
                                            default => 15
                                        };
                                    @endphp
                                    <div class="step-tracker-item {{ $activeIdx > 0 ? 'completed' : ($activeIdx === 0 ? 'active' : '') }}">
                                        <span>[1] Transcribe</span>
                                    </div>
                                    <div class="step-tracker-item {{ $activeIdx > 1 ? 'completed' : ($activeIdx === 1 ? 'active' : '') }}">
                                        <span>[2] Analyze</span>
                                    </div>
                                    <div class="step-tracker-item {{ $activeIdx > 2 ? 'completed' : ($activeIdx === 2 ? 'active' : '') }}">
                                        <span>[3] Render</span>
                                    </div>
                                    <div class="step-tracker-item {{ $sLower === 'completed' ? 'completed' : '' }}">
                                        <span>[4] Ready</span>
                                    </div>
                                </div>

                                <!-- Progress Bar -->
                                <div class="progress-track">
                                    <div class="progress-bar progress-active" id="progress-bar-{{ $video->id }}" style="width: {{ $initialPercent }}%;"></div>
                                </div>

                                <!-- Dynamic Live Step & Progress Label -->
                                <div class="current-step-label" id="current-step-label-{{ $video->id }}" style="font-size: 11px; color: #38bdf8; font-weight: 700; margin-top: 6px; letter-spacing: 0.3px;">
                                    ▶ Processing: {{ ucfirst($video->status) }} ({{ $initialPercent }}%)
                                </div>

                                <!-- Collapsible Terminal Logs -->
                                <details style="background: #110f0f; border: 1px solid var(--color-border); border-radius: 4px; padding: 6px 10px; margin-top: 8px;" open>
                                    <summary style="font-size: 10px; font-weight: 700; color: var(--color-text-secondary); cursor: pointer;">
                                        [ CONSOLE OUTPUT STREAM ]
                                    </summary>
                                    <pre class="console-log" id="console-log-{{ $video->id }}" style="margin-top: 6px; max-height: 200px; overflow-y: auto;">Waiting for pipeline output...</pre>
                                </details>
                            </div>
                        </div>
                    @endforeach
                </div>
            @endif

            <!-- ─── Master Video & Clip Gallery with Master Fold Controls ─── -->
            <div>
                <div class="gallery-master-header">
                    <div class="gallery-master-title">
                        <i data-lucide="layout-grid" class="icon-sm"></i>
                        <span>[ PROCESSED VIDEOS & CLIPS ]</span>
                        <span style="font-size: 11px; color: var(--color-text-muted); font-weight: 400;">({{ $videos->count() }} videos, {{ $totalClipsCount }} clips)</span>
                    </div>

                    <div class="gallery-master-actions">
                        <!-- Global Instant Search -->
                        <input type="text" id="global-search-input" class="text-input" style="width: 220px; padding: 4px 8px; font-size: 11px;" placeholder="Search all clips/transcripts..." oninput="handleGlobalSearch(this.value)">

                        <!-- Master Fold / Expand All Buttons -->
                        <button type="button" class="btn-input-action" onclick="toggleAllFolders(false)" title="Collapse all video folders">
                            <i data-lucide="chevrons-down-up" class="icon-sm"></i> FOLD ALL
                        </button>
                        <button type="button" class="btn-input-action" onclick="toggleAllFolders(true)" title="Expand all video folders">
                            <i data-lucide="chevrons-up-down" class="icon-sm"></i> EXPAND ALL
                        </button>
                    </div>
                </div>

                <div style="display: flex; flex-direction: column; gap: 14px; margin-top: 14px;">
                    @foreach($videos as $index => $video)
                        @php
                            $isFirst = ($index === 0 && $video->clips->count() > 0);
                            $topScore = $video->clips->max('virality_score') ?? ($video->clips->count() ? 92 : null);
                            $allPostsText = $video->clips->map(function($c, $i) {
                                return "─── CLIP #" . ($i + 1) . " ───\n" . $c->full_post_text;
                            })->implode("\n\n" . str_repeat("=", 32) . "\n\n");
                        @endphp
                        <div class="video-card" data-video-id="{{ $video->id }}">
                            <div class="folder-header" role="button" tabindex="0" aria-expanded="{{ $isFirst ? 'true' : 'false' }}" onclick="toggleFolder({{ $video->id }})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();toggleFolder({{ $video->id }});}">
                                <div class="folder-title">
                                    <i data-lucide="folder" class="icon-sm" style="color: #ff9f0a;"></i>
                                    <span>{{ $video->filename }}</span>
                                </div>
                                <div class="folder-meta-group" onclick="event.stopPropagation()" onkeydown="event.stopPropagation()">
                                    <span class="status-badge status-{{ strtolower($video->status) }}">
                                        {{ $video->status }}
                                    </span>
                                    <span class="folder-glance-badge">
                                        {{ $video->clips->count() }} CLIPS
                                    </span>
                                    @if($topScore)
                                        <span class="folder-glance-badge viral" title="Top AI Virality Score">
                                            <i data-lucide="flame" class="icon-sm"></i> TOP: {{ $topScore }}/100
                                        </span>
                                    @endif
                                    @if(strtolower($video->status) === 'failed')
                                        <form action="{{ route('videos.retry', $video->id) }}" method="POST" style="margin:0;">
                                            @csrf
                                            <button type="submit" class="btn-input-action" title="Retry processing this video with saved settings" style="color: #38bdf8; border-color: rgba(56, 189, 248, 0.4);">
                                                <i data-lucide="rotate-cw" class="icon-sm"></i> RETRY
                                            </button>
                                        </form>
                                    @endif
                                    @if($video->clips->count() > 0)
                                        <button type="button" class="btn-input-action" onclick="copyPostText({{ json_encode($allPostsText) }}, this)" title="Copy Social Media Posts for ALL Clips in this Video" style="color: #ff9f0a; border-color: rgba(255, 159, 10, 0.4);">
                                            <i data-lucide="copy" class="icon-sm"></i> COPY ALL POSTS
                                        </button>
                                    @endif
                                    <form action="{{ route('videos.destroy', $video->id) }}" method="POST" onsubmit="return confirm('Delete this video and all associated clips?');" style="margin:0;">
                                        @csrf
                                        @method('DELETE')
                                        <button type="submit" class="button-danger-sm" title="Delete Video & Clips" aria-label="Delete Video {{ $video->filename }}">
                                            <i data-lucide="trash-2" class="icon-sm"></i>
                                        </button>
                                    </form>
                                    <!-- Auto-folded by default with [+] -->
                                    <span class="toggle-chevron" id="chevron-{{ $video->id }}">{{ $isFirst ? '[-]' : '[+]' }}</span>
                                </div>
                            </div>

                            <!-- Folded / Collapsed by default (except newest) -->
                            <div class="folder-content @if(!$isFirst) collapsed @endif" id="folder-{{ $video->id }}">
                                @if($video->clips->count() > 0)
                                    <!-- Filter Toolbar -->
                                    <div class="folder-toolbar">
                                        <input type="text" class="clip-search-input" placeholder="Filter clips in this video..." oninput="filterClips(this, {{ $video->id }})">
                                        <div class="filter-pills-group" id="filter-group-{{ $video->id }}">
                                            <button type="button" class="filter-pill-btn active" onclick="setClipFilter(this, 'all', {{ $video->id }})">All ({{ $video->clips->count() }})</button>
                                            <button type="button" class="filter-pill-btn" onclick="setClipFilter(this, 'ready', {{ $video->id }})">Ready</button>
                                        </div>
                                    </div>

                                    <!-- Clips Grid -->
                                    <div class="clips-grid" id="clips-grid-{{ $video->id }}">
                                        @foreach($video->clips as $cIndex => $clip)
                                            @php
                                                $hasVideo = $clip->output_path && file_exists(base_path($clip->output_path));
                                                $clipVer = $clip->updated_at ? $clip->updated_at->timestamp : 1;
                                                $webPath = $hasVideo ? (asset(str_replace('storage/app/public/', 'storage/', $clip->output_path)) . '?v=' . $clipVer) : '';
                                                $absPath = $clip->output_path ? base_path($clip->output_path) : '';
                                                $meta = $clip->metadata;
                                                $vScore = $clip->virality_score;
                                            @endphp
                                            <div class="clip-card @if($vScore >= 92) clip-card-highlight @endif" data-clip-id="{{ $clip->id }}" data-status="{{ strtolower($clip->status) }}" data-reason="{{ strtolower($clip->reason . ' ' . $clip->title) }}">
                                                @if($hasVideo)
                                                    <div class="clip-video-wrapper">
                                                        <!-- Hover-to-Play Video Preview with Muted Audio -->
                                                        <video class="clip-video" muted preload="metadata" loop onmouseenter="this.play()" onmouseleave="this.pause()">
                                                            <source src="{{ $webPath }}" type="video/mp4">
                                                        </video>
                                                        <div class="hover-play-hint">
                                                            <i data-lucide="play" class="icon-sm"></i> HOVER TO PREVIEW
                                                        </div>
                                                    </div>
                                                @endif

                                                <div class="clip-card-body">
                                                    <div class="clip-header">
                                                        <div class="clip-badge">CLIP #{{ $cIndex + 1 }}</div>
                                                        <div class="status-badge status-{{ strtolower($clip->status) }}" style="font-size: 9px; padding: 1px 5px;">
                                                            {{ $clip->status }}
                                                        </div>
                                                    </div>

                                                    <div class="clip-title-bar">
                                                        <div class="clip-title-text">{{ $clip->title }}</div>
                                                        <span class="clip-timestamp-badge"><i data-lucide="clock" class="icon-sm"></i> {{ $clip->start_time }} - {{ $clip->end_time }}</span>
                                                    </div>

                                                    <!-- AI Virality Score & 3-Bar Metric Breakdown -->
                                                    <div class="clip-virality-card">
                                                        <div class="virality-header">
                                                            <span class="virality-badge @if($vScore >= 90) score-super @elseif($vScore >= 80) score-high @else score-mid @endif">
                                                                <i data-lucide="flame" class="icon-sm"></i> {{ $vScore }}/100
                                                            </span>
                                                            <span class="virality-tag">
                                                                @if($vScore >= 92) 🔥 MEGA VIRAL @elseif($vScore >= 85) ⚡ HIGH RETENTION @else 📈 SOLID @endif
                                                            </span>
                                                        </div>
                                                        <div class="metric-bars-row">
                                                            <div class="mini-metric" title="Hook Strength">
                                                                <span class="metric-label">HOOK</span>
                                                                <div class="mini-bar-track"><div class="mini-bar-fill" style="width: {{ $clip->hook_strength }}%;"></div></div>
                                                                <span class="metric-val">{{ $clip->hook_strength }}%</span>
                                                            </div>
                                                            <div class="mini-metric" title="Pacing Flow">
                                                                <span class="metric-label">PACE</span>
                                                                <div class="mini-bar-track"><div class="mini-bar-fill pace" style="width: {{ $clip->pacing_energy }}%;"></div></div>
                                                                <span class="metric-val">{{ $clip->pacing_energy }}%</span>
                                                            </div>
                                                            <div class="mini-metric" title="Shareability">
                                                                <span class="metric-label">SHARE</span>
                                                                <div class="mini-bar-track"><div class="mini-bar-fill share" style="width: {{ $clip->shareability }}%;"></div></div>
                                                                <span class="metric-val">{{ $clip->shareability }}%</span>
                                                            </div>
                                                        </div>
                                                    </div>

                                                    <div class="clip-reason">
                                                        "{{ $clip->reason }}"
                                                    </div>

                                                    <!-- Primary Actions: Preview & Download -->
                                                    <div class="clip-action-bar-row">
                                                        @if($hasVideo)
                                                            <button type="button" class="btn-card-action primary" onclick="openCinemaModal({{ json_encode($webPath) }}, {{ json_encode('Clip #' . ($cIndex + 1) . ' - ' . $clip->title) }}, {{ json_encode($clip->reason) }}, {{ json_encode($absPath) }}, {{ json_encode($meta) }})">
                                                                <i data-lucide="eye" class="icon-sm"></i> PREVIEW
                                                            </button>
                                                            <a href="{{ $webPath }}" download="Clip_{{ $clip->id }}_{{ \Illuminate\Support\Str::slug($clip->title) }}.mp4" class="btn-card-action">
                                                                <i data-lucide="download" class="icon-sm"></i> DOWNLOAD
                                                            </a>
                                                        @endif
                                                    </div>

                                                    <!-- Auxiliary Toolbar -->
                                                    <div class="clip-aux-actions">
                                                        <button type="button" class="btn-input-action" onclick="copyPostText({{ json_encode($clip->full_post_text) }}, this)" title="1-Click Copy Post Text">
                                                            <i data-lucide="copy" class="icon-sm"></i> COPY POST
                                                        </button>
                                                        <button type="button" class="btn-input-action" onclick="openSubsEditor({{ $clip->id }})" title="Edit Subtitle Transcripts">
                                                            <i data-lucide="edit-3" class="icon-sm"></i> SUBS
                                                        </button>
                                                        @if($hasVideo)
                                                            <button type="button" class="btn-input-action" onclick="openInExplorer({{ $clip->id }}, this)" title="Reveal in Windows Explorer">
                                                                <i data-lucide="folder-open" class="icon-sm"></i> EXPLORER
                                                            </button>
                                                        @endif
                                                        <form action="{{ route('clips.destroy', $clip->id) }}" method="POST" onsubmit="return confirm('Delete this clip?');" style="margin:0;">
                                                            @csrf
                                                            @method('DELETE')
                                                            <button type="submit" class="button-danger-sm" title="Delete Clip" aria-label="Delete Clip #{{ $cIndex + 1 }}">
                                                                <i data-lucide="trash-2" class="icon-sm"></i>
                                                            </button>
                                                        </form>
                                                    </div>
                                                </div>
                                            </div>
                                        @endforeach
                                    </div>
                                @else
                                    <div style="font-size: 11px; color: var(--color-text-muted); padding: 10px; text-align: center;">
                                        No clips extracted for this video yet.
                                    </div>
                                @endif
                            </div>
                        </div>
                    @endforeach
                </div>
            </div>

        </main>
    </div>

    <!-- ─── Interactive Cinema Lightbox Modal ─── -->
    <div class="video-modal-backdrop" id="cinema-modal" onclick="if(event.target===this) closeCinemaModal()">
        <div class="video-modal-content">
            <div class="video-modal-header">
                <div class="video-modal-title">
                    <i data-lucide="film" class="icon-md" style="color: #38bdf8;"></i>
                    <span id="modal-title-text">[ CLIP PREVIEW ]</span>
                </div>
                <div class="safe-zone-guide-bar">
                    <span class="safe-zone-label">[ SAFE-ZONE: ]</span>
                    <div class="safe-zone-btn-group">
                        <button type="button" class="safe-zone-btn active" onclick="setSafeZoneGuide('none', this)">OFF</button>
                        <button type="button" class="safe-zone-btn" onclick="setSafeZoneGuide('tiktok', this)">TikTok</button>
                        <button type="button" class="safe-zone-btn" onclick="setSafeZoneGuide('reels', this)">Reels</button>
                        <button type="button" class="safe-zone-btn" onclick="setSafeZoneGuide('shorts', this)">Shorts</button>
                    </div>
                </div>
                <button type="button" class="video-modal-close" onclick="closeCinemaModal()" aria-label="Close clip preview modal"><i data-lucide="x" class="icon-md"></i></button>
            </div>
            <div class="video-modal-body">
                <div class="modal-video-container">
                    <video id="modal-video-player" class="modal-video-element" controls autoplay></video>
                    <div class="safe-zone-overlay safe-zone-none" id="safe-zone-overlay"></div>
                </div>
                <div class="modal-details-pane">
                    <!-- Social Media Posting Kit Card -->
                    <div class="modal-detail-card">
                        <div class="modal-detail-label" style="display: flex; align-items: center; justify-content: space-between;">
                            <span style="display: flex; align-items: center; gap: 4px;"><i data-lucide="share-2" class="icon-sm" style="color: #38bdf8;"></i> [ SOCIAL MEDIA POSTING KIT ]</span>
                            <span id="modal-virality-badge" class="virality-badge score-super" style="font-size: 10px; padding: 2px 6px;">95/100</span>
                        </div>
                        <div style="margin-top: 6px;">
                            <div style="font-size: 12px; font-weight: 800; color: #fff; margin-bottom: 4px;" id="modal-post-title">Viral Hook Title</div>
                            <div style="font-size: 11px; color: var(--color-hairline-strong); white-space: pre-wrap; background: #000; padding: 8px; border-radius: 2px; border: 1px solid var(--color-border); max-height: 80px; overflow-y: auto;" id="modal-post-caption">Caption text...</div>
                            <div style="font-size: 10px; color: #38bdf8; margin-top: 4px; font-weight: 700;" id="modal-post-hashtags">#viral #shorts</div>
                        </div>
                        <div class="clip-action-bar" style="margin-top: 8px; gap: 6px; display: flex; flex-wrap: wrap;">
                            <button type="button" class="btn-modal-action" id="modal-copy-post-btn" style="border-color: rgba(56, 189, 248, 0.4); color: #38bdf8;">
                                📋 COPY TIKTOK / REELS POST
                            </button>
                            <button type="button" class="btn-modal-action" id="modal-copy-shorts-btn" style="border-color: rgba(255, 59, 48, 0.4); color: #ff3b30;">
                                📋 COPY SHORTS DESCRIPTION
                            </button>
                        </div>
                    </div>

                    <div class="modal-detail-card">
                        <div class="modal-detail-label" style="display: flex; align-items: center; gap: 4px;"><i data-lucide="sparkles" class="icon-sm" style="color: #ff9f0a;"></i> [ AI HOOK & VIRALITY ANALYSIS ]</div>
                        <div class="modal-detail-val" id="modal-explanation-text">...</div>
                    </div>
                    <div class="modal-detail-card">
                        <div class="modal-detail-label">[ OUTPUT FILE PATH ]</div>
                        <div class="modal-detail-val" id="modal-path-text" style="word-break: break-all; font-size: 10px;">...</div>
                        <div style="margin-top: 6px;">
                            <button type="button" class="btn-modal-action" id="modal-copy-btn">
                                📋 COPY PATH
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- ─── Interactive Subtitle Editor Modal ─── -->
    <div class="video-modal-backdrop" id="subs-modal" onclick="if(event.target===this) closeSubsEditor()">
        <div class="video-modal-content" style="max-width: 820px;">
            <div class="video-modal-header">
                <div class="video-modal-title">
                    <i data-lucide="file-edit" class="icon-md" style="color: #bf5af2;"></i>
                    <span>[ WORD-LEVEL TRANSCRIPT & SUBTITLE EDITOR ]</span>
                </div>
                <button type="button" class="video-modal-close" onclick="closeSubsEditor()" aria-label="Close subtitle editor modal"><i data-lucide="x" class="icon-md"></i></button>
            </div>
            <div class="video-modal-body" style="flex-direction: column; padding: 14px;">
                <p style="color: var(--color-text-secondary); font-size: 11px; margin-bottom: 8px;">
                    Edit words, adjust exact timestamps, delete filler words, or switch subtitle presets. ASS subtitle scripts and face tracking will re-generate seamlessly.
                </p>

                <!-- Subtitle Editor Toolbar: Style Presets, Position, Add Word -->
                <div class="sub-editor-toolbar" id="subs-editor-toolbar" style="display: none;">
                    <div class="sub-editor-toolbar-group">
                        <label style="font-size: 10px; color: var(--color-text-muted); font-weight: 700;">STYLE:</label>
                        <select id="modal-subs-style" class="sub-editor-select">
                            <option value="yellow_pop">🟡 Yellow Pop</option>
                            <option value="neon_cyan">🔵 Neon Cyan</option>
                            <option value="bold_white">🟢 Bold White</option>
                            <option value="hormozi_box">🔴 Hormozi Style</option>
                            <option value="karaoke_green">⚡ Karaoke Lime</option>
                            <option value="cyber_pink">🟣 Cyber Pink</option>
                            <option value="fire_gold">🔥 Fire Gold</option>
                            <option value="electric_violet">⚡ Electric Violet</option>
                        </select>
                    </div>

                    <div class="sub-editor-toolbar-group">
                        <label style="font-size: 10px; color: var(--color-text-muted); font-weight: 700;">POSITION:</label>
                        <select id="modal-subs-pos" class="sub-editor-select">
                            <option value="bottom">Bottom (Safe Zone)</option>
                            <option value="center">Center (Eye-Level)</option>
                            <option value="top">Top (Banner)</option>
                        </select>
                    </div>

                    <div class="sub-editor-toolbar-group">
                        <span id="subs-word-count-badge" style="font-size: 10px; color: #38bdf8; font-weight: 700; margin-right: 6px;">0 words</span>
                        <button type="button" class="btn-input-action" onclick="addWordToTranscript()" style="background: rgba(56, 189, 248, 0.15); border-color: rgba(56, 189, 248, 0.4); color: #38bdf8; display: inline-flex; align-items: center; gap: 4px;">
                            <i data-lucide="plus" class="icon-sm"></i> ADD WORD
                        </button>
                    </div>
                </div>

                <div id="subs-editor-loading" style="display: none; padding: 24px; text-align: center; color: var(--color-text-secondary);">
                    <span class="spinner" style="width: 18px; height: 18px; margin-bottom: 6px; display: inline-block;"></span>
                    <div>Loading transcript words...</div>
                </div>
                <div id="subs-editor-error" style="display: none; padding: 10px; background: rgba(255, 59, 48, 0.1); border: 1px solid rgba(255, 59, 48, 0.3); color: #ff3b30; border-radius: 2px; font-size: 11px; margin-bottom: 10px;"></div>
                <div id="subs-editor-grid" class="subs-editor-grid" style="display: none;"></div>
                <div class="subs-editor-actions" id="subs-editor-actions" style="display: none;">
                    <button type="button" class="btn-input-action" onclick="closeSubsEditor()">CANCEL</button>
                    <button type="button" class="btn-subs-save" id="btn-subs-save" onclick="saveAndReRender()" style="display: inline-flex; align-items: center; gap: 5px;">
                        <i data-lucide="refresh-cw" class="icon-sm"></i> SAVE & RE-RENDER
                    </button>
                </div>
            </div>
        </div>
    </div>

    <!-- ─── Toast Notification Container ─── -->
    <div id="ronin-toast" class="ronin-toast">
        <i data-lucide="check-circle" class="icon-sm" style="color: #30d158;"></i>
        <span id="ronin-toast-text">Copied to clipboard!</span>
    </div>

    <!-- ─── JavaScript Application Logic ─── -->
    <script>
        // ─── 1. Settings Panel Toggle ───
        const toggleBtn = document.getElementById('settings-toggle');
        const settingsBody = document.getElementById('settings-body');
        const chevron = document.getElementById('settings-chevron');

        if (toggleBtn && settingsBody) {
            toggleBtn.addEventListener('click', () => {
                settingsBody.classList.toggle('collapsed');
                if (chevron) {
                    chevron.textContent = settingsBody.classList.contains('collapsed') ? '[+]' : '[-]';
                }
            });
        }

        // Mutual exclusion: Punch-In Zoom <-> Ken Burns
        const punchIn = document.getElementById('punch_in_zoom');
        const kenBurns = document.getElementById('ken_burns');
        if (punchIn && kenBurns) {
            punchIn.addEventListener('change', () => { if (punchIn.checked) kenBurns.checked = false; });
            kenBurns.addEventListener('change', () => { if (kenBurns.checked) punchIn.checked = false; });
        }

        // Toggle conditional sub-inputs for Whip-Pan Speed & BGM Path
        const whipPanToggle = document.getElementById('whip_pan_transitions');
        const transitionSpeedGroup = document.getElementById('transition-speed-group');
        const bgmToggle = document.getElementById('background_music');
        const bgmPathGroup = document.getElementById('bgm-path-group');

        function syncConditionalSettings() {
            if (whipPanToggle && transitionSpeedGroup) {
                transitionSpeedGroup.style.display = whipPanToggle.checked ? 'flex' : 'none';
            }
            if (bgmToggle && bgmPathGroup) {
                bgmPathGroup.style.display = bgmToggle.checked ? 'flex' : 'none';
            }
        }
        if (whipPanToggle) whipPanToggle.addEventListener('change', syncConditionalSettings);
        if (bgmToggle) bgmToggle.addEventListener('change', syncConditionalSettings);

        // ─── 2. Presets Manager ───
        function applyPreset(preset, btn) {
            document.querySelectorAll('.preset-card-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const vert = document.getElementById('format_vertical');
            const orig = document.getElementById('format_original');
            const hooks = document.getElementById('mode_hooks');
            const full = document.getElementById('mode_full');
            const smartCrop = document.getElementById('smart_crop');
            const autoCaptions = document.getElementById('auto_captions');
            const punchIn = document.getElementById('punch_in_zoom');
            const kenBurns = document.getElementById('ken_burns');
            const whipPan = document.getElementById('whip_pan_transitions');
            const splitScreen = document.getElementById('split_screen');
            const captionStyle = document.getElementById('caption_style');

            if (preset === 'tiktok_viral') {
                if (vert) vert.checked = true;
                if (hooks) hooks.checked = true;
                if (smartCrop) smartCrop.checked = true;
                if (autoCaptions) autoCaptions.checked = true;
                if (punchIn) punchIn.checked = false;
                if (kenBurns) kenBurns.checked = false;
                if (whipPan) whipPan.checked = false;
                if (splitScreen) splitScreen.checked = false;
                if (captionStyle) captionStyle.value = 'yellow_pop';
            } else if (preset === 'full_video') {
                if (orig) orig.checked = true;
                if (full) full.checked = true;
                if (smartCrop) smartCrop.checked = false;
                if (autoCaptions) autoCaptions.checked = true;
                if (punchIn) punchIn.checked = false;
                if (kenBurns) kenBurns.checked = false;
                if (whipPan) whipPan.checked = false;
                if (splitScreen) splitScreen.checked = false;
                if (captionStyle) captionStyle.value = 'bold_white';
            } else if (preset === 'podcast_split') {
                if (vert) vert.checked = true;
                if (hooks) hooks.checked = true;
                if (smartCrop) smartCrop.checked = false;
                if (splitScreen) splitScreen.checked = true;
                if (autoCaptions) autoCaptions.checked = true;
                if (captionStyle) captionStyle.value = 'neon_cyan';
            } else if (preset === 'fast_action') {
                if (vert) vert.checked = true;
                if (hooks) hooks.checked = true;
                if (smartCrop) smartCrop.checked = true;
                if (punchIn) punchIn.checked = true;
                if (kenBurns) kenBurns.checked = false;
                if (whipPan) whipPan.checked = true;
                if (autoCaptions) autoCaptions.checked = true;
                if (captionStyle) captionStyle.value = 'hormozi_box';
            }

            if (typeof syncConditionalSettings === 'function') syncConditionalSettings();
            if (typeof updateSubtitleSimulator === 'function') updateSubtitleSimulator();
        }

        // ─── 3. Folder Collapsing & Master Fold Controls ───
        function toggleFolder(videoId) {
            const folder = document.getElementById('folder-' + videoId);
            const chev = document.getElementById('chevron-' + videoId);
            if (folder) {
                folder.classList.toggle('collapsed');
                if (chev) chev.textContent = folder.classList.contains('collapsed') ? '[+]' : '[-]';
            }
        }

        function toggleAllFolders(expand) {
            document.querySelectorAll('.video-card').forEach(card => {
                const videoId = card.dataset.videoId;
                const folder = document.getElementById('folder-' + videoId);
                const chev = document.getElementById('chevron-' + videoId);
                if (folder) {
                    if (expand) {
                        folder.classList.remove('collapsed');
                        if (chev) chev.textContent = '[-]';
                    } else {
                        folder.classList.add('collapsed');
                        if (chev) chev.textContent = '[+]';
                    }
                }
            });
            showToast(expand ? '📂 Expanded all video folders' : '📁 Folded all video folders');
        }

        function filterClips(input, videoId) {
            const query = input.value.toLowerCase().trim();
            const grid = document.getElementById('clips-grid-' + videoId);
            if (!grid) return;
            grid.querySelectorAll('.clip-card').forEach(card => {
                const reason = card.dataset.reason || '';
                card.style.display = reason.includes(query) ? 'flex' : 'none';
            });
        }

        function setClipFilter(btn, filterValue, videoId) {
            const group = document.getElementById('filter-group-' + videoId);
            if (group) group.querySelectorAll('.filter-pill-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const grid = document.getElementById('clips-grid-' + videoId);
            if (!grid) return;
            grid.querySelectorAll('.clip-card').forEach(card => {
                const cardStatus = card.dataset.status || '';
                let show = true;
                if (filterValue === 'ready') show = cardStatus === 'ready';
                card.style.display = show ? 'flex' : 'none';
            });
        }

        // Global Nav Search
        function handleGlobalSearch(query) {
            const q = query.toLowerCase().trim();
            document.querySelectorAll('.clip-card').forEach(card => {
                const reason = card.dataset.reason || '';
                card.style.display = (q === '' || reason.includes(q)) ? 'flex' : 'none';
            });
            // If searching, auto-expand all folders
            if (q !== '') {
                document.querySelectorAll('.folder-content').forEach(f => f.classList.remove('collapsed'));
                document.querySelectorAll('.toggle-chevron').forEach(c => c.textContent = '[-]');
            }
        }

        // ─── 4. Native File Picker & Clipboard ───
        async function triggerBrowseFile(btn, targetInputId = 'video_path', fileType = 'video') {
            const originalHtml = btn.innerHTML;
            btn.innerHTML = '<i data-lucide="loader" class="icon-sm" style="animation: spin 1s linear infinite;"></i> OPENING...';
            if (window.lucide) lucide.createIcons();
            try {
                const response = await fetch("{{ route('videos.browse') }}", {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-TOKEN': '{{ csrf_token() }}'
                    },
                    body: JSON.stringify({ type: fileType })
                });
                const data = await response.json();
                if (data.success && data.file_path) {
                    const input = document.getElementById(targetInputId);
                    if (input) {
                        input.value = data.file_path;
                        input.focus();
                        showToast('📁 Selected: ' + data.file_path.split(/[\\\\/]/).pop());
                    }
                }
            } catch (err) {
                console.error("Browse failed:", err);
            } finally {
                btn.innerHTML = originalHtml;
                if (window.lucide) lucide.createIcons();
            }
        }

        async function pasteClipboardPath() {
            try {
                const text = await navigator.clipboard.readText();
                if (text) {
                    const input = document.getElementById('video_path');
                    if (input) {
                        input.value = text.trim();
                        input.focus();
                        showToast('📋 Pasted file path!');
                    }
                }
            } catch (e) {
                console.error("Clipboard paste error", e);
            }
        }

        function clearPathInput() {
            const input = document.getElementById('video_path');
            if (input) {
                input.value = '';
                input.focus();
            }
        }

        function copyClipPath(path, btn) {
            navigator.clipboard.writeText(path).then(() => {
                showToast('📁 Absolute path copied!');
            });
        }

        function copyPostText(text, btn) {
            if (!navigator.clipboard) {
                const el = document.createElement('textarea');
                el.value = text;
                document.body.appendChild(el);
                el.select();
                document.execCommand('copy');
                document.body.removeChild(el);
            } else {
                navigator.clipboard.writeText(text);
            }
            showToast('📋 Copied formatted social post!');
        }

        function showToast(msg) {
            const toast = document.getElementById('ronin-toast');
            const text = document.getElementById('ronin-toast-text');
            if (toast && text) {
                text.textContent = msg;
                toast.classList.add('show');
                setTimeout(() => toast.classList.remove('show'), 2400);
            }
        }

        async function openInExplorer(clipId, btn) {
            try {
                const res = await fetch(`/clips/${clipId}/explorer`, {
                    method: 'POST',
                    headers: { 'X-CSRF-TOKEN': '{{ csrf_token() }}' }
                });
                const data = await res.json();
                if (data.success) {
                    showToast('📁 Revealed in Windows Explorer');
                }
            } catch (err) {
                console.error(err);
            }
        }

        // ─── 5. Cinema Lightbox Modal & Safe Zone HUD ───
        function openCinemaModal(videoUrl, title, reason, absPath, meta) {
            const modal = document.getElementById('cinema-modal');
            const player = document.getElementById('modal-video-player');
            const titleEl = document.getElementById('modal-title-text');
            const expEl = document.getElementById('modal-explanation-text');
            const pathEl = document.getElementById('modal-path-text');
            const copyBtn = document.getElementById('modal-copy-btn');

            const viralityBadge = document.getElementById('modal-virality-badge');
            const postTitleEl = document.getElementById('modal-post-title');
            const postCaptionEl = document.getElementById('modal-post-caption');
            const postHashtagsEl = document.getElementById('modal-post-hashtags');
            const copyPostBtn = document.getElementById('modal-copy-post-btn');
            const copyShortsBtn = document.getElementById('modal-copy-shorts-btn');

            if (player) player.src = videoUrl;
            if (titleEl) titleEl.textContent = title;
            if (expEl) expEl.textContent = '"' + reason + '"';
            if (pathEl) pathEl.textContent = absPath;

            if (meta) {
                const vScore = meta.virality_score || 88;
                if (viralityBadge) {
                    viralityBadge.textContent = vScore + '/100 VIRALITY';
                    viralityBadge.className = 'virality-badge ' + (vScore >= 90 ? 'score-super' : (vScore >= 80 ? 'score-high' : 'score-mid'));
                }
                if (postTitleEl) postTitleEl.textContent = '🚀 ' + (meta.title || title);
                if (postCaptionEl) postCaptionEl.textContent = meta.social_caption || reason;
                if (postHashtagsEl) postHashtagsEl.textContent = meta.hashtags || '#viral #shorts';

                if (copyPostBtn) {
                    const fullPost = `🚀 ${meta.title || title}\n\n${meta.social_caption || reason}\n\n${meta.hashtags || '#viral #shorts'}`;
                    copyPostBtn.onclick = function() { copyPostText(fullPost, copyPostBtn); };
                }

                if (copyShortsBtn) {
                    const shortsDesc = `${meta.title || title}\n\n${meta.shorts_description || meta.social_caption || reason}\n\n${meta.hashtags || '#viral #shorts'}`;
                    copyShortsBtn.onclick = function() { copyPostText(shortsDesc, copyShortsBtn); };
                }
            }

            if (copyBtn) {
                copyBtn.onclick = function() { copyClipPath(absPath, copyBtn); };
            }

            if (modal) modal.classList.add('is-visible');
        }

        function closeCinemaModal() {
            const modal = document.getElementById('cinema-modal');
            const player = document.getElementById('modal-video-player');
            if (player) {
                player.pause();
                player.src = '';
            }
            if (modal) modal.classList.remove('is-visible');
        }

        function setSafeZoneGuide(platform, btn) {
            document.querySelectorAll('.safe-zone-btn').forEach(b => b.classList.remove('active'));
            if (btn) btn.classList.add('active');

            const overlay = document.getElementById('safe-zone-overlay');
            if (!overlay) return;

            overlay.className = 'safe-zone-overlay safe-zone-' + platform;

            if (platform === 'none') {
                overlay.innerHTML = '';
                return;
            }

            let hudHtml = '';
            if (platform === 'tiktok') {
                hudHtml = `
                    <div class="safe-boundary-box"><div class="safe-zone-tag">TIKTOK SAFE ZONE</div></div>
                    <div class="hud-top-bar"><span>LIVE</span><span class="hud-tabs">Following | <b>For You</b></span><i data-lucide="search" class="icon-sm"></i></div>
                    <div class="hud-right-actions">
                        <div class="hud-avatar">👤<span class="hud-plus">+</span></div>
                        <div class="hud-action-item"><i data-lucide="heart" class="icon-md"></i><span>124K</span></div>
                        <div class="hud-action-item"><i data-lucide="message-circle" class="icon-md"></i><span>3.8K</span></div>
                        <div class="hud-action-item"><i data-lucide="bookmark" class="icon-md"></i><span>18K</span></div>
                        <div class="hud-action-item"><i data-lucide="share-2" class="icon-md"></i><span>4.9K</span></div>
                        <div class="hud-disc">🎵</div>
                    </div>
                    <div class="hud-bottom-info">
                        <div class="hud-username">@roninclips.ai</div>
                        <div class="hud-caption">Extracting viral moments locally 100% free... #viral #ai</div>
                    </div>
                `;
            } else if (platform === 'reels') {
                hudHtml = `
                    <div class="safe-boundary-box"><div class="safe-zone-tag">REELS SAFE ZONE</div></div>
                    <div class="hud-top-bar"><span style="font-weight: 700;">Reels</span><i data-lucide="camera" class="icon-sm"></i></div>
                    <div class="hud-right-actions">
                        <div class="hud-action-item"><i data-lucide="heart" class="icon-md"></i><span>89K</span></div>
                        <div class="hud-action-item"><i data-lucide="message-circle" class="icon-md"></i><span>1.4K</span></div>
                        <div class="hud-action-item"><i data-lucide="send" class="icon-md"></i><span>Share</span></div>
                    </div>
                    <div class="hud-bottom-info">
                        <div class="hud-username">roninclips • Follow</div>
                        <div class="hud-caption">Word-by-word subtitle generator offline.</div>
                    </div>
                `;
            } else if (platform === 'shorts') {
                hudHtml = `
                    <div class="safe-boundary-box"><div class="safe-zone-tag">SHORTS SAFE ZONE</div></div>
                    <div class="hud-right-actions">
                        <div class="hud-action-item"><i data-lucide="thumbs-up" class="icon-md"></i><span>240K</span></div>
                        <div class="hud-action-item"><i data-lucide="thumbs-down" class="icon-md"></i><span>Dislike</span></div>
                        <div class="hud-action-item"><i data-lucide="message-square" class="icon-md"></i><span>980</span></div>
                        <div class="hud-action-item"><i data-lucide="share" class="icon-md"></i><span>Share</span></div>
                    </div>
                    <div class="hud-bottom-info">
                        <div class="hud-username">@RoninClips • Subscribe</div>
                        <div class="hud-caption">Best AI video clipper engine</div>
                    </div>
                `;
            }

            overlay.innerHTML = hudHtml;
            if (window.lucide) lucide.createIcons();
        }

        // ─── 6. Subtitle Live Simulator ───
        const captionStyleSelect = document.getElementById('caption_style');
        const captionFontSelect = document.getElementById('caption_font');
        const captionPosSelect = document.getElementById('caption_position');
        const captionLayoutSelect = document.getElementById('caption_layout');
        const simContent = document.getElementById('subs-sim-content');

        const styleColors = {
            'yellow_pop': { active: '#ffff00', inactive: '#ffffff', stroke: '#000000' },
            'neon_cyan': { active: '#00ffff', inactive: '#eeeeee', stroke: '#000000' },
            'bold_white': { active: '#00ff00', inactive: '#ffffff', stroke: '#000000' },
            'hormozi_box': { active: '#ffd700', inactive: '#ffffff', stroke: '#ff0000' },
            'karaoke_green': { active: '#66ff00', inactive: '#ffffff', stroke: '#003300' },
            'cyber_pink': { active: '#ff00ff', inactive: '#ffff00', stroke: '#330033' },
            'fire_gold': { active: '#ff4500', inactive: '#ffd700', stroke: '#000000' },
            'electric_violet': { active: '#a855f7', inactive: '#ffffff', stroke: '#2e0854' }
        };

        function updateSubtitleSimulator() {
            if (!simContent) return;
            const styleKey = captionStyleSelect ? captionStyleSelect.value : 'yellow_pop';
            const fontName = captionFontSelect ? captionFontSelect.value : 'Arial Black';
            const posVal = captionPosSelect ? captionPosSelect.value : 'bottom';
            const layoutVal = captionLayoutSelect ? captionLayoutSelect.value : 'two_line';

            const cfg = styleColors[styleKey] || styleColors['yellow_pop'];
            simContent.style.fontFamily = `"${fontName}", sans-serif`;
            simContent.className = 'subs-sim-content pos-' + posVal;

            document.querySelectorAll('.subs-sim-content .sim-word').forEach(el => {
                if (el.classList.contains('active-word')) {
                    el.style.color = cfg.active;
                    el.style.textShadow = `0 0 8px ${cfg.active}, -2px -2px 0 ${cfg.stroke}, 2px -2px 0 ${cfg.stroke}, -2px 2px 0 ${cfg.stroke}, 2px 2px 0 ${cfg.stroke}`;
                    el.style.transform = 'scale(1.15)';
                } else {
                    el.style.color = cfg.inactive;
                    el.style.textShadow = `-2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 2px 2px 0 #000`;
                    el.style.transform = 'scale(1.0)';
                }
            });

            if (layoutVal === 'single_word') {
                document.getElementById('sim-word-1').style.display = 'none';
                document.getElementById('sim-word-2').style.display = 'inline-block';
                document.getElementById('sim-word-3').style.display = 'none';
                document.getElementById('sim-word-4').style.display = 'none';
            } else {
                document.getElementById('sim-word-1').style.display = 'inline';
                document.getElementById('sim-word-2').style.display = 'inline';
                document.getElementById('sim-word-3').style.display = 'inline';
                document.getElementById('sim-word-4').style.display = 'inline';
            }
        }

        [captionStyleSelect, captionFontSelect, captionPosSelect, captionLayoutSelect].forEach(el => {
            if (el) el.addEventListener('change', updateSubtitleSimulator);
        });

        let simActiveIdx = 1;
        setInterval(() => {
            const words = ['sim-word-1', 'sim-word-2', 'sim-word-3', 'sim-word-4'];
            words.forEach((id, idx) => {
                const el = document.getElementById(id);
                if (el) {
                    if (idx === simActiveIdx) el.classList.add('active-word');
                    else el.classList.remove('active-word');
                }
            });
            simActiveIdx = (simActiveIdx + 1) % words.length;
            updateSubtitleSimulator();
        }, 1200);

        // ─── 7. Subtitle Word Editor Modal ───
        let currentClipId = null;
        let currentSubsData = [];

        async function openSubsEditor(clipId) {
            currentClipId = clipId;
            const modal = document.getElementById('subs-modal');
            const loading = document.getElementById('subs-editor-loading');
            const error = document.getElementById('subs-editor-error');
            const grid = document.getElementById('subs-editor-grid');
            const toolbar = document.getElementById('subs-editor-toolbar');
            const actions = document.getElementById('subs-editor-actions');

            modal.classList.add('is-visible');
            loading.style.display = 'block';
            error.style.display = 'none';
            grid.style.display = 'none';
            if (toolbar) toolbar.style.display = 'none';
            actions.style.display = 'none';
            grid.innerHTML = '';

            try {
                const res = await fetch(`/clips/${clipId}/transcript`);
                if (!res.ok) throw new Error('Failed to load transcript data');
                const data = await res.json();
                currentSubsData = data.words || [];

                if (currentSubsData.length === 0) {
                    throw new Error('No words found in transcript for this clip.');
                }

                renderSubsEditorGrid();

                loading.style.display = 'none';
                if (toolbar) toolbar.style.display = 'flex';
                grid.style.display = 'grid';
                actions.style.display = 'flex';
                if (window.lucide) lucide.createIcons();
            } catch (err) {
                loading.style.display = 'none';
                error.textContent = err.message;
                error.style.display = 'block';
            }
        }

        function renderSubsEditorGrid() {
            const grid = document.getElementById('subs-editor-grid');
            const countBadge = document.getElementById('subs-word-count-badge');
            if (!grid) return;

            grid.innerHTML = '';
            if (countBadge) countBadge.textContent = `${currentSubsData.length} words`;

            currentSubsData.forEach((w, idx) => {
                const card = document.createElement('div');
                card.className = 'sub-word-card';
                card.innerHTML = `
                    <div class="sub-word-card-header">
                        <div class="sub-time-inputs" title="Adjust start & end timings">
                            <input type="number" step="0.05" min="0" class="sub-time-input" value="${Number(w.start).toFixed(2)}" onchange="updateWordStart(${idx}, this.value)">
                            <span style="font-size: 8px; color: var(--color-text-muted);">➔</span>
                            <input type="number" step="0.05" min="0" class="sub-time-input" value="${Number(w.end).toFixed(2)}" onchange="updateWordEnd(${idx}, this.value)">
                        </div>
                        <button type="button" class="btn-word-delete" onclick="deleteWord(${idx})" title="Delete this word">&times;</button>
                    </div>
                    <input type="text" class="sub-word-input" value="${(w.word || '').replace(/"/g, '&quot;')}" oninput="updateWordData(${idx}, this.value)">
                `;
                grid.appendChild(card);
            });
        }

        function updateWordData(index, newWord) {
            if (currentSubsData[index]) {
                currentSubsData[index].word = newWord;
            }
        }

        function updateWordStart(index, newStart) {
            if (currentSubsData[index]) {
                currentSubsData[index].start = parseFloat(newStart) || 0;
            }
        }

        function updateWordEnd(index, newEnd) {
            if (currentSubsData[index]) {
                currentSubsData[index].end = parseFloat(newEnd) || 0;
            }
        }

        function deleteWord(index) {
            if (currentSubsData[index]) {
                currentSubsData.splice(index, 1);
                renderSubsEditorGrid();
            }
        }

        function addWordToTranscript() {
            const lastWord = currentSubsData.length > 0 ? currentSubsData[currentSubsData.length - 1] : null;
            const newStart = lastWord ? (Number(lastWord.end) + 0.05) : 0.0;
            const newEnd = Number((newStart + 0.45).toFixed(2));
            currentSubsData.push({
                word: 'NEW',
                start: Number(newStart.toFixed(2)),
                end: newEnd
            });
            renderSubsEditorGrid();
            const grid = document.getElementById('subs-editor-grid');
            if (grid) grid.scrollTop = grid.scrollHeight;
        }

        function closeSubsEditor() {
            const modal = document.getElementById('subs-modal');
            if (modal) modal.classList.remove('is-visible');
        }

        async function saveAndReRender() {
            if (!currentClipId) return;
            const btn = document.getElementById('btn-subs-save');
            const originalText = btn.innerHTML;
            btn.innerHTML = '<i data-lucide="loader" class="icon-sm" style="animation: spin 1s linear infinite;"></i> SAVING...';
            btn.disabled = true;

            const styleVal = document.getElementById('modal-subs-style') ? document.getElementById('modal-subs-style').value : '';
            const posVal = document.getElementById('modal-subs-pos') ? document.getElementById('modal-subs-pos').value : '';

            try {
                const res = await fetch(`/clips/${currentClipId}/re-render`, {
                    method: 'POST',
                    headers: {
                        'X-CSRF-TOKEN': '{{ csrf_token() }}',
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        words: currentSubsData,
                        caption_style: styleVal,
                        caption_position: posVal
                    })
                });
                const data = await res.json();
                if (res.ok && data.success) {
                    btn.innerHTML = '⏳ RE-RENDERING SUBTITLES...';
                    pollClipReRender(currentClipId);
                } else {
                    throw new Error(data.error || 'Failed to save transcript');
                }
            } catch (err) {
                btn.innerHTML = '❌ ERROR';
                alert(err.message);
                setTimeout(() => { 
                    btn.innerHTML = originalText;
                    btn.disabled = false;
                }, 2000);
            }
        }

        function pollClipReRender(clipId) {
            let attempts = 0;
            const poll = setInterval(async () => {
                attempts++;
                try {
                    const res = await fetch(`/clips/${clipId}/status`);
                    if (res.ok) {
                        const statusData = await res.json();
                        if (String(statusData.status).toLowerCase() === 'ready') {
                            clearInterval(poll);
                            closeSubsEditor();
                            showToast('✅ Subtitles re-rendered! Reloading...');
                            setTimeout(() => window.location.reload(), 600);
                            return;
                        }
                    }
                } catch (e) {
                    console.error("Clip status poll error:", e);
                }
                if (attempts > 90) {
                    clearInterval(poll);
                    window.location.reload();
                }
            }, 1200);
        }

        // ─── 8. Background Polling for Active Video Streams ───
        const activeVideos = @json($videos->filter(fn($v) => !in_array(strtolower($v->status), ['completed', 'failed']))->pluck('id')->values());
        activeVideos.forEach(videoId => pollVideoStatus(videoId));

        const renderingClips = @json($videos->flatMap->clips->filter(fn($c) => strtolower($c->status) === 'rendering')->pluck('id')->values());
        renderingClips.forEach(clipId => pollClipReRender(clipId));

        function pollVideoStatus(videoId) {
            const interval = setInterval(async () => {
                try {
                    const response = await fetch(`/videos/${videoId}/logs`);
                    if (!response.ok) return;
                    const data = await response.json();
                    
                    const card = document.querySelector(`.video-card[data-video-id="${videoId}"]`);
                    if (!card) return;

                    // 1. Update status badge & text
                    const statusBadge = card.querySelector('.status-badge');
                    const statusText = card.querySelector('.status-text');
                    if (statusText) statusText.textContent = data.status;
                    if (statusBadge) statusBadge.className = 'status-badge status-' + data.status.toLowerCase();

                    // 2. Update step tracker items dynamically
                    const tracker = card.querySelector('.step-tracker-container');
                    if (tracker) {
                        const stepItems = tracker.querySelectorAll('.step-tracker-item');
                        const sIdx = (data.step_index !== undefined) ? data.step_index : 0;
                        stepItems.forEach((item, idx) => {
                            item.classList.remove('active', 'completed');
                            const stepNum = idx + 1;
                            if (sIdx > stepNum) {
                                item.classList.add('completed');
                            } else if (sIdx === stepNum) {
                                item.classList.add('active');
                            }
                        });
                    }

                    // 3. Update Progress Bar width
                    const pBar = card.querySelector('.progress-bar');
                    if (pBar && data.progress_percent !== undefined) {
                        pBar.style.width = data.progress_percent + '%';
                    }

                    // 4. Update Current Step label
                    const stepLabel = card.querySelector('.current-step-label');
                    if (stepLabel && data.current_step) {
                        stepLabel.textContent = `▶ ${data.current_step} (${data.progress_percent || 0}%)`;
                    }

                    // 5. Update and auto-scroll console logs
                    const pre = card.querySelector('.console-log');
                    if (pre) {
                        const wasNearBottom = (pre.scrollHeight - pre.scrollTop - pre.clientHeight) < 80;
                        pre.textContent = data.logs;
                        if (wasNearBottom) {
                            pre.scrollTop = pre.scrollHeight;
                        }
                    }

                    // 6. Reload on complete or failure
                    if (['completed', 'failed'].includes(data.status.toLowerCase())) {
                        clearInterval(interval);
                        setTimeout(() => window.location.reload(), 1500);
                    }
                } catch (e) {
                    console.error("Polling error:", e);
                }
            }, 2000);
        }

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                closeCinemaModal();
                closeSubsEditor();
            }
        });

        // Initialize Lucide Icons & Simulator on Load
        document.addEventListener('DOMContentLoaded', () => {
            if (window.lucide) lucide.createIcons();
            updateSubtitleSimulator();
        });
    </script>
</body>
</html>
