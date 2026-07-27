<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RoninClips - Local Video Clipper</title>
    <link rel="stylesheet" href="{{ asset('css/app.css') }}?v={{ time() }}">
</head>
<body>
    <div class="app-layout">
        <!-- Sidebar: Form and Settings -->
        <aside class="app-sidebar">
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
            <p class="body-md">Run your video processing pipeline completely offline with <span class="body-strong">Groq AI</span> & <span class="body-strong">FFmpeg</span>.</p>
            </div>
            
            <div class="about-us-section">
                <div class="about-us-title">[ ABOUT US ]</div>
                <div class="about-us-content">
                    <p>I built RoninClips to have access to a premium clipping tool for myself, running completely locally and for free.</p>
                    <p class="about-creator">Created by <strong>Christian Lascuna</strong></p>
                </div>
            </div>

            @if(session('success'))
                <div class="alert alert-success">
                    {{ session('success') }}
                </div>
            @endif
            @if(session('error'))
                <div class="alert alert-error">
                    {{ session('error') }}
                </div>
            @endif

            <form action="{{ route('videos.store') }}" method="POST" id="pipeline-form">
                @csrf
                <div class="form-group">
                    <label for="video_path">Absolute Video File Path</label>
                    <input type="text" id="video_path" name="video_path" class="text-input" placeholder="C:\Users\Sebaz\Videos\podcast.mp4" required>
                </div>

                <!-- ─── Settings Panel ─── -->
                <div class="settings-panel">
                    <div class="settings-header">
                        <span class="settings-icon">[*]</span>
                        <span>Pipeline Settings</span>
                        <button type="button" class="settings-toggle" id="settings-toggle" aria-label="Toggle settings">
                            <span class="toggle-chevron rotated">[+]</span>
                        </button>
                    </div>

                    <div class="settings-body collapsed" id="settings-body">
                        <!-- Output Format -->
                        <div class="settings-section">
                            <div class="settings-section-title">OUTPUT FORMAT</div>
                            <div class="radio-group">
                                <label class="radio-label" for="format_vertical">
                                    <input type="radio" id="format_vertical" name="output_format" value="9:16" checked>
                                    <span class="radio-status"></span>
                                    <span class="radio-text">
                                        <strong>9:16 Vertical</strong>
                                        <small>TikTok / Shorts / Reels</small>
                                    </span>
                                </label>
                                <label class="radio-label" for="format_original">
                                    <input type="radio" id="format_original" name="output_format" value="original">
                                    <span class="radio-status"></span>
                                    <span class="radio-text">
                                        <strong>Original</strong>
                                        <small>Keep source aspect ratio</small>
                                    </span>
                                </label>
                            </div>
                        </div>

                        <!-- Effects Toggles -->
                        <div class="settings-section">
                            <div class="settings-section-title">EFFECTS</div>
                            <div class="toggle-group">
                                <label class="toggle-label" for="smart_crop">
                                    <input type="checkbox" id="smart_crop" name="smart_crop" value="1" checked class="toggle-checkbox">
                                    <span class="toggle-status"></span>
                                    <span class="toggle-text">
                                        <strong>Smart Face Tracking</strong>
                                        <small>Auto-center crop on the subject's face</small>
                                    </span>
                                </label>

                                <label class="toggle-label" for="auto_captions">
                                    <input type="checkbox" id="auto_captions" name="auto_captions" value="1" checked class="toggle-checkbox">
                                    <span class="toggle-status"></span>
                                    <span class="toggle-text">
                                        <strong>Auto Captions</strong>
                                        <small>Word-by-word highlight captions</small>
                                    </span>
                                </label>

                                <label class="toggle-label" for="punch_in_zoom">
                                    <input type="checkbox" id="punch_in_zoom" name="punch_in_zoom" value="1" class="toggle-checkbox">
                                    <span class="toggle-status"></span>
                                    <span class="toggle-text">
                                        <strong>Punch-In Zoom</strong>
                                        <small>Zoom in on loud / exciting moments</small>
                                    </span>
                                </label>

                                <label class="toggle-label" for="ken_burns">
                                    <input type="checkbox" id="ken_burns" name="ken_burns" value="1" class="toggle-checkbox">
                                    <span class="toggle-status"></span>
                                    <span class="toggle-text">
                                        <strong>Ken Burns</strong>
                                        <small>Subtle slow zoom for static shots</small>
                                    </span>
                                </label>
                                <label class="toggle-label" for="emoji_overlays">
                                    <input type="checkbox" id="emoji_overlays" name="emoji_overlays" value="1" class="toggle-checkbox">
                                    <span class="toggle-status"></span>
                                    <span class="toggle-text">
                                        <strong>Emoji Overlays</strong>
                                        <small>Pop contextual emojis based on what's being said</small>
                                    </span>
                                </label>

                                <label class="toggle-label" for="whip_pan_transitions">
                                    <input type="checkbox" id="whip_pan_transitions" name="whip_pan_transitions" value="1" class="toggle-checkbox">
                                    <span class="toggle-status"></span>
                                    <span class="toggle-text">
                                        <strong>Whip-Pan Transitions</strong>
                                        <small>Smooth motion-blur transitions between jump cuts</small>
                                    </span>
                                </label>

                                <label class="toggle-label" for="background_music">
                                    <input type="checkbox" id="background_music" name="background_music" value="1" class="toggle-checkbox">
                                    <span class="toggle-status"></span>
                                    <span class="toggle-text">
                                        <strong>Background Music</strong>
                                        <small>Add BGM with auto ducking</small>
                                    </span>
                                </label>

                                <div class="bgm-path-group" id="bgm-path-group" style="display: none;">
                                    <label for="bgm_path" class="bgm-path-label">[~] Background Music File Path</label>
                                    <input type="text" id="bgm_path" name="bgm_path" class="text-input bgm-path-input" placeholder="/path/to/lofi.mp3">
                                </div>

                                <label class="toggle-label" for="split_screen">
                                    <input type="checkbox" id="split_screen" name="split_screen" value="1" class="toggle-checkbox">
                                    <span class="toggle-status"></span>
                                    <span class="toggle-text">
                                        <strong>Split-Screen</strong>
                                        <small>Podcast mode: show each speaker in their own panel</small>
                                    </span>
                                </label>
                            </div>
                        </div>

                        <!-- Caption & Transition Styling -->
                        <div class="settings-section">
                            <div class="settings-section-title">CAPTION STYLING & TRANSITIONS</div>
                            <div class="form-group" style="margin-bottom: 12px;">
                                <label for="caption_style" style="font-size: 11px; font-weight: 600; text-transform: uppercase; color: var(--color-hairline-strong); margin-bottom: 4px; display: block;">Caption Highlight Style</label>
                                <select id="caption_style" name="caption_style" class="text-input" style="padding: 6px 10px; font-size: 12px;">
                                    <option value="yellow_pop" selected>🟡 Yellow Pop (Classic Opus yellow)</option>
                                    <option value="neon_cyan">🌐 Neon Cyan (Cyberpunk cyan)</option>
                                    <option value="bold_white">⚪ Bold White (Minimalist green pop)</option>
                                </select>
                            </div>
                            <div class="form-group" style="margin-bottom: 12px;">
                                <label for="caption_font" style="font-size: 11px; font-weight: 600; text-transform: uppercase; color: var(--color-hairline-strong); margin-bottom: 4px; display: block;">Font Family</label>
                                <select id="caption_font" name="caption_font" class="text-input" style="padding: 6px 10px; font-size: 12px;">
                                    <option value="Arial Black" selected>🔤 Arial Black (Ultra Bold)</option>
                                    <option value="Impact">💥 Impact (Heavy Viral)</option>
                                    <option value="Trebuchet MS">📐 Trebuchet MS (Clean Sans)</option>
                                    <option value="Verdana">📖 Verdana (High Legibility)</option>
                                    <option value="Montserrat">✨ Montserrat / System Sans</option>
                                </select>
                            </div>
                            <div class="form-group" style="margin-bottom: 12px;">
                                <label for="caption_position" style="font-size: 11px; font-weight: 600; text-transform: uppercase; color: var(--color-hairline-strong); margin-bottom: 4px; display: block;">Subtitle Position</label>
                                <select id="caption_position" name="caption_position" class="text-input" style="padding: 6px 10px; font-size: 12px;">
                                    <option value="bottom" selected>⬇️ Bottom (Safe Zone for TikTok/Reels UI)</option>
                                    <option value="center">🎯 Center (Eye-Level / Dynamic Focus)</option>
                                    <option value="top">⬆️ Top (Header Banner)</option>
                                </select>
                            </div>
                            <div class="form-group" style="margin-bottom: 12px;">
                                <label for="caption_layout" style="font-size: 11px; font-weight: 600; text-transform: uppercase; color: var(--color-hairline-strong); margin-bottom: 4px; display: block;">Subtitle Layout Mode</label>
                                <select id="caption_layout" name="caption_layout" class="text-input" style="padding: 6px 10px; font-size: 12px;">
                                    <option value="two_line" selected>💬 2-Line Block (Classic Opus/TikTok style)</option>
                                    <option value="single_word">⚡ Single Word Pop (1 Word at a time)</option>
                                    <option value="full_line">📜 Full Line (Multi-word phrase block)</option>
                                </select>
                            </div>
                            <div class="form-group" style="margin-bottom: 0;">
                                <label for="transition_speed" style="font-size: 11px; font-weight: 600; text-transform: uppercase; color: var(--color-hairline-strong); margin-bottom: 4px; display: block;">Transition Speed</label>
                                <select id="transition_speed" name="transition_speed" class="text-input" style="padding: 6px 10px; font-size: 12px;">
                                    <option value="0.15">⚡ Fast (0.15s snap cut)</option>
                                    <option value="0.25" selected>🌀 Normal (0.25s smooth whip-pan)</option>
                                    <option value="0.35">🎬 Dramatic (0.35s long motion-blur)</option>
                                </select>
                            </div>
                        </div>
                        <!-- Processing Mode -->
                        <div class="settings-section">
                            <div class="settings-section-title">PROCESSING MODE</div>
                            <div class="radio-group" style="flex-direction: column; gap: 8px;">
                                <label class="radio-label" for="mode_viral_clips">
                                    <input type="radio" id="mode_viral_clips" name="processing_mode" value="viral_clips" checked>
                                    <span class="radio-status"></span>
                                    <span class="radio-text">
                                        <strong>✂️ Viral Clips (AI Extraction)</strong>
                                        <small>Groq AI analyzes transcript and cuts top hook segments</small>
                                    </span>
                                </label>
                                <label class="radio-label" for="mode_full_video">
                                    <input type="radio" id="mode_full_video" name="processing_mode" value="full_video">
                                    <span class="radio-status"></span>
                                    <span class="radio-text">
                                        <strong>🎬 Full Video (No Clipping)</strong>
                                        <small>Process the entire video with subtitles & effects — no AI cutting</small>
                                    </span>
                                </label>
                            </div>

                            <!-- Clip Count (only visible in Viral Clips mode) -->
                            <div class="clip-count-group" id="clip-count-group" style="margin-top: 16px;">
                                <label for="target_clip_count" class="clip-count-label">How many clips should be made?</label>
                                <div class="number-input-wrapper">
                                    <input type="number" id="target_clip_count" name="target_clip_count" min="1" max="20" value="5" class="text-input number-input">
                                    <span class="input-suffix">clips max</span>
                                </div>
                                <small class="text-muted"><span class="highlight-icon">[*]</span> AI will prioritize extracting the most high-quality hooks and moments with the highest viral potential up to this count.</small>
                            </div>
                        </div>

                        <!-- Info note -->
                        <div class="settings-note">
                            <span>[!]</span>
                            <span>Punch-In Zoom and Ken Burns can't be combined. Split-Screen overrides Smart Crop. Emoji Overlays require Auto Captions to be enabled.</span>
                        </div>
                    </div>
                </div>

                <button type="submit" class="button-primary" style="width: 100%;">
                    [ RUN PIPELINE ]
                </button>
            </form>
        </aside>

        <!-- Main Content: Videos -->
        <main class="app-main">
            <!-- Top System Dashboard Header -->
            <header class="main-dashboard-header">
                <div class="header-title-block">
                    <div class="system-status-indicator">
                        <span class="pulse-dot"></span>
                        <span class="system-title">SYSTEM ONLINE</span>
                        <span class="engine-badge">GROQ AI • FASTER-WHISPER • FFMPEG</span>
                    </div>
                    <h2 class="dashboard-heading">Pipeline & Render Console</h2>
                </div>

                <!-- Metric Stat Cards -->
                <div class="stats-overview-grid">
                    <div class="stat-card">
                        <div class="stat-icon">📁</div>
                        <div class="stat-data">
                            <span class="stat-value">{{ $videos->count() }}</span>
                            <span class="stat-label">Videos Tracked</span>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon">✂️</div>
                        <div class="stat-data">
                            <span class="stat-value">{{ $videos->sum(fn($v) => $v->clips->count()) }}</span>
                            <span class="stat-label">Clips Extracted</span>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon">⚡</div>
                        <div class="stat-data">
                            <span class="stat-value text-accent">0% Fee</span>
                            <span class="stat-label">100% Offline / Local</span>
                        </div>
                    </div>
                </div>
            </header>

            @if($videos->isEmpty())
                <!-- Rich Interactive Welcome & Quick Start Banner -->
                <div class="welcome-guide-card">
                    <div class="welcome-header">
                        <span class="welcome-badge">[ QUICK START GUIDE ]</span>
                        <h3>Welcome to RoninClips</h3>
                        <p>Extract viral short-form clips directly from your local video files with zero cloud latency or subscription fees:</p>
                    </div>

                    <div class="steps-timeline-grid">
                        <div class="timeline-step">
                            <div class="step-num">01</div>
                            <div class="step-info">
                                <strong>Set Absolute File Path</strong>
                                <p>Paste the path to any <code>.mp4</code> file on your drive (e.g. <code>C:\Videos\podcast.mp4</code>).</p>
                            </div>
                        </div>
                        <div class="timeline-step">
                            <div class="step-num">02</div>
                            <div class="step-info">
                                <strong>Select Effects & Captions</strong>
                                <p>Choose 9:16 Smart Crop, Yellow Pop/Neon Cyan Captions, Whip-Pan Transitions, and Emoji Overlays.</p>
                            </div>
                        </div>
                        <div class="timeline-step">
                            <div class="step-num">03</div>
                            <div class="step-info">
                                <strong>Run AI Processing Engine</strong>
                                <p>Click <code>[ RUN PIPELINE ]</code>. Groq AI spots viral hooks, Whisper transcribes, and FFmpeg renders.</p>
                            </div>
                        </div>
                    </div>

                    <!-- Quick sample path fill helper -->
                    <div class="sample-fill-box">
                        <span class="sample-box-title">💡 Quick Fill Test Path Preset:</span>
                        <div class="sample-chips-row">
                            <button type="button" class="sample-chip-btn" onclick="fillSamplePath('C:\\RONINCLIPSTEST\\What really matters at the end of life  BJ Miller  TED.mp4')">
                                📋 TED Talk MP4 Sample
                            </button>
                            <button type="button" class="sample-chip-btn" onclick="fillSamplePath('C:\\RONINCLIPSTEST\\ishowspeedtest.mp4')">
                                📋 Gaming Stream MP4 Sample
                            </button>
                        </div>
                    </div>
                </div>
            @endif

            <div class="dashboard-grid">
            @foreach($videos as $video)
                <div class="video-card folder-card" data-video-id="{{ $video->id }}">
                    <div class="folder-header" onclick="toggleFolder(this)">
                        <div class="folder-title-group">
                            <span class="folder-icon">[+]</span>
                            <div class="video-title">
                                {{ $video->filename }}
                            </div>
                        </div>
                        <div class="folder-actions" style="display: flex; align-items: center; gap: 12px;">
                            <span class="step-text" style="font-size: 12px; color: var(--color-hairline-strong); margin-right: 12px;"></span>
                            <div class="status-badge status-{{ strtolower($video->status) }}">
                                @if(!in_array(strtolower($video->status), ['completed', 'failed']))
                                    <span class="spinner"></span>
                                @endif
                                <span class="status-text">{{ $video->status }}</span>
                            </div>
                            <form action="{{ route('videos.destroy', $video->id) }}" method="POST" onsubmit="return confirm('Are you sure you want to delete this folder and ALL its clips? This cannot be undone.');" style="margin: 0;" onclick="event.stopPropagation();">
                                @csrf
                                @method('DELETE')
                                <button type="submit" class="button-danger-sm" title="Remove Folder" style="padding: 4px 8px; font-size: 11px;">[DELETE]</button>
                            </form>
                        </div>
                    </div>

                    <div class="folder-content">
                    @php
                        $progress = 0;
                        switch(strtolower($video->status)) {
                            case 'pending': $progress = 5; break;
                            case 'transcribing': $progress = 30; break;
                            case 'analyzing': $progress = 60; break;
                            case 'processing': $progress = 85; break;
                            case 'completed': $progress = 100; break;
                            case 'failed': $progress = 100; break;
                        }
                        $settings = $video->processing_settings ?? [];
                    @endphp
                    <div class="progress-container">
                        <div class="progress-bar {{ strtolower($video->status) === 'failed' ? 'progress-failed' : 'progress-active' }}" style="width: {{ $progress }}%"></div>
                    </div>

                    @php
                        $logFile = storage_path('logs/engine_' . $video->id . '.log');
                        $initialLogs = file_exists($logFile) ? file_get_contents($logFile) : 'No log records yet.';
                    @endphp
                    <details class="log-viewer" style="margin-bottom: 16px;">
                        <summary style="font-family: var(--font-mono); font-size: 12px; color: var(--color-hairline-strong); cursor: pointer; user-select: none; display: flex; align-items: center; justify-content: space-between;">
                            <span>[ VIEW PIPELINE LOGS ]</span>
                            <button type="button" class="button-copy-log" onclick="copyLogText(this, {{ $video->id }}); event.preventDefault();" style="background: none; border: 1px solid var(--color-border); color: #a6e22e; padding: 2px 8px; font-family: var(--font-mono); font-size: 10px; cursor: pointer; border-radius: 3px;">📋 COPY LOGS</button>
                        </summary>
                        <pre class="console-log" id="log-pre-{{ $video->id }}" style="background: #110e0e; color: #a6e22e; padding: 12px; font-family: var(--font-mono); font-size: 11px; overflow-x: auto; max-height: 250px; overflow-y: auto; margin-top: 8px; border: 1px solid var(--color-border); white-space: pre-wrap; word-break: break-all;">{{ $initialLogs }}</pre>
                    </details>

                    @if(!empty($settings))
                        <div class="settings-tags">
                            @if($settings['output_format'] ?? '' === '9:16')
                                <span class="tag">[x] 9:16</span>
                            @endif
                            @if($settings['caption_style'] ?? false)
                                <span class="tag">[style] {{ $settings['caption_style'] }}</span>
                            @endif
                            @if($settings['smart_crop'] ?? false)
                                <span class="tag">[x] Face Track</span>
                            @endif
                            @if($settings['auto_captions'] ?? false)
                                <span class="tag">[x] Captions</span>
                            @endif
                            @if($settings['punch_in_zoom'] ?? false)
                                <span class="tag">[x] Punch-In</span>
                            @endif
                            @if($settings['ken_burns'] ?? false)
                                <span class="tag">[x] Ken Burns</span>
                            @endif
                            @if($settings['emoji_overlays'] ?? false)
                                <span class="tag">[x] Emojis</span>
                            @endif
                            @if($settings['whip_pan_transitions'] ?? false)
                                <span class="tag">[x] Whip-Pan</span>
                            @endif
                            @if($settings['background_music'] ?? false)
                                <span class="tag">[x] BGM</span>
                            @endif
                            @if($settings['split_screen'] ?? false)
                                <span class="tag">[x] Split</span>
                            @endif
                        </div>
                    @endif

                    @if($video->clips->count() > 0)
                        <div class="clips-grid">
                            @foreach($video->clips as $index => $clip)
                                <div class="clip-card">
                                    @if($clip->output_path && file_exists(base_path($clip->output_path)))
                                        <div class="clip-video-wrapper">
                                            <video class="clip-video" controls preload="metadata">
                                                <source src="{{ asset(str_replace('storage/app/public/', 'storage/', $clip->output_path)) }}" type="video/mp4">
                                            </video>
                                        </div>
                                    @endif
                                    
                                    <div class="clip-card-body">
                                        <div class="clip-header">
                                            <div style="display: flex; gap: 8px; align-items: center;">
                                                <div class="clip-badge">Clip #{{ $index + 1 }}</div>
                                                <div class="status-badge status-{{ strtolower($clip->status) }}">
                                                    @if(!in_array(strtolower($clip->status), ['ready', 'failed']))
                                                        <span class="spinner"></span>
                                                    @endif
                                                    {{ $clip->status }}
                                                </div>
                                            </div>
                                            <div style="display: flex; gap: 4px; align-items: center;">
                                                @if($clip->output_path)
                                                    <button type="button" class="button-copy-clip" onclick="copyClipPath('{{ base_path($clip->output_path) }}', this)" title="Copy Absolute File Path" style="background: none; border: 1px solid var(--color-border); color: #fff; padding: 2px 6px; font-family: var(--font-mono); font-size: 10px; cursor: pointer;">📋 PATH</button>
                                                @endif
                                                <form action="{{ route('clips.destroy', $clip->id) }}" method="POST" onsubmit="return confirm('Are you sure you want to delete this clip?');" style="margin:0;">
                                                    @csrf
                                                    @method('DELETE')
                                                    <button type="submit" class="button-danger-sm" title="Remove Clip">[X]</button>
                                                </form>
                                            </div>
                                        </div>

                                        <div class="clip-meta">
                                            <span class="icon">[T]</span> {{ $clip->start_time }} - {{ $clip->end_time }}
                                        </div>

                                        <div class="clip-viral-potential">
                                            <span class="viral-icon">[*]</span>
                                            <span class="viral-text">High Viral Potential</span>
                                        </div>

                                        <!-- Retention chart removed to reduce UI clutter -->

                                        <div class="clip-reason">
                                            "{{ $clip->hook_explanation }}"
                                        </div>
                                    </div>
                                </div>
                            @endforeach
                        </div>
                    @endif
                    </div> <!-- end folder-content -->
                </div>
            @endforeach
            </div>
        </main>
    </div>

    <script>
        // Toggle settings panel
        const toggleBtn = document.getElementById('settings-toggle');
        const settingsBody = document.getElementById('settings-body');
        const chevron = toggleBtn.querySelector('.toggle-chevron');

        toggleBtn.addEventListener('click', () => {
            settingsBody.classList.toggle('collapsed');
            chevron.classList.toggle('rotated');
            chevron.textContent = settingsBody.classList.contains('collapsed') ? '[+]' : '[-]';
        });

        // Mutual exclusion: Punch-In Zoom <-> Ken Burns
        const punchIn = document.getElementById('punch_in_zoom');
        const kenBurns = document.getElementById('ken_burns');

        punchIn.addEventListener('change', () => {
            if (punchIn.checked) kenBurns.checked = false;
        });

        kenBurns.addEventListener('change', () => {
            if (kenBurns.checked) punchIn.checked = false;
        });

        // Smart crop only works with 9:16
        const formatVertical = document.getElementById('format_vertical');
        const formatOriginal = document.getElementById('format_original');
        const smartCrop = document.getElementById('smart_crop');
        const splitScreen = document.getElementById('split_screen');

        formatOriginal.addEventListener('change', () => {
            if (formatOriginal.checked) {
                smartCrop.checked = false;
                smartCrop.disabled = true;
                splitScreen.checked = false;
                splitScreen.disabled = true;
            }
        });

        formatVertical.addEventListener('change', () => {
            if (formatVertical.checked) {
                smartCrop.disabled = false;
                smartCrop.checked = true;
                splitScreen.disabled = false;
            }
        });

        // Split-Screen <-> Smart Crop mutual exclusion

        splitScreen.addEventListener('change', () => {
            if (splitScreen.checked) {
                smartCrop.checked = false;
                smartCrop.disabled = true;
            } else {
                if (formatVertical.checked) {
                    smartCrop.disabled = false;
                    smartCrop.checked = true;
                }
            }
        });

        smartCrop.addEventListener('change', () => {
            if (smartCrop.checked) {
                splitScreen.checked = false;
            }
        });

        // Background Music path visibility
        const bgmToggle = document.getElementById('background_music');
        const bgmGroup = document.getElementById('bgm-path-group');

        bgmToggle.addEventListener('change', () => {
            bgmGroup.style.display = bgmToggle.checked ? 'flex' : 'none';
            if (bgmToggle.checked) {
                bgmGroup.classList.add('bgm-slide-in');
            }
        });

        // Emoji overlays require auto captions
        const emojiOverlays = document.getElementById('emoji_overlays');
        const autoCaptions = document.getElementById('auto_captions');

        emojiOverlays.addEventListener('change', () => {
            if (emojiOverlays.checked && !autoCaptions.checked) {
                autoCaptions.checked = true;
            }
        });

        autoCaptions.addEventListener('change', () => {
            if (!autoCaptions.checked && emojiOverlays.checked) {
                emojiOverlays.checked = false;
            }
        });

        // Detailed API polling for active video streams
        const activeVideos = @json($videos->filter(function ($video) {
            return !in_array($video->status, ['completed', 'failed']);
        })->pluck('id')->values());

        activeVideos.forEach(videoId => {
            pollVideoStatus(videoId);
        });

        function pollVideoStatus(videoId) {
            const interval = setInterval(async () => {
                try {
                    const response = await fetch(`/videos/${videoId}/logs`);
                    if (!response.ok) return;
                    const data = await response.json();
                    
                    const card = document.querySelector(`.video-card[data-video-id="${videoId}"]`);
                    if (!card) return;

                    // Update status badge
                    const badge = card.querySelector('.status-badge');
                    const statusText = card.querySelector('.status-text');
                    if (statusText) statusText.textContent = data.status;
                    
                    badge.className = 'status-badge status-' + data.status.toLowerCase();

                    // Remove spinner if complete/failed
                    const spinner = badge.querySelector('.spinner');
                    if (['completed', 'failed'].includes(data.status.toLowerCase()) && spinner) {
                        spinner.remove();
                    }

                    // Update step text
                    const stepSpan = card.querySelector('.step-text');
                    if (stepSpan) {
                        stepSpan.textContent = data.current_step;
                    }

                    // Update progress bar
                    const progressBar = card.querySelector('.progress-bar');
                    if (progressBar) {
                        let progress = 0;
                        switch(data.status.toLowerCase()) {
                            case 'pending': progress = 5; break;
                            case 'transcribing': progress = 30; break;
                            case 'analyzing': progress = 60; break;
                            case 'processing': progress = 85; break;
                            case 'completed': progress = 100; break;
                            case 'failed': progress = 100; break;
                        }
                        progressBar.className = 'progress-bar ' + (data.status.toLowerCase() === 'failed' ? 'progress-failed' : 'progress-active');
                        progressBar.style.width = progress + '%';
                    }

                    // Update console log
                    const pre = card.querySelector('.console-log');
                    if (pre) {
                        pre.textContent = data.logs;
                    }

                    // Stop condition
                    if (['completed', 'failed'].includes(data.status.toLowerCase())) {
                        clearInterval(interval);
                        if (data.status.toLowerCase() === 'completed') {
                            setTimeout(() => {
                                window.location.reload();
                            }, 2000);
                        }
                    }
                } catch (err) {
                    console.error('Failed to poll logs:', err);
                }
            }, 3000);
        }

        function toggleFolder(header) {
            const card = header.closest('.folder-card');
            const isOpen = card.classList.toggle('is-open');
            const icon = header.querySelector('.folder-icon');
            if (icon) {
                icon.textContent = isOpen ? '[-]' : '[+]';
            }
            const videoId = card.dataset.videoId;
            if (videoId) {
                localStorage.setItem('folder_state_' + videoId, isOpen);
            }
        }

        // Restore state on load (defaulting to closed unless saved as open)
        document.addEventListener('DOMContentLoaded', () => {
            document.querySelectorAll('.folder-card').forEach(card => {
                const videoId = card.dataset.videoId;
                const icon = card.querySelector('.folder-icon');
                if (videoId) {
                    const state = localStorage.getItem('folder_state_' + videoId);
                    if (state === 'true') {
                        card.classList.add('is-open');
                        if (icon) icon.textContent = '[-]';
                    } else {
                        card.classList.remove('is-open');
                        if (icon) icon.textContent = '[+]';
                    }
                }
            });
        });
        function copyLogText(btn, videoId) {
            const logPre = document.getElementById('log-pre-' + videoId);
            if (!logPre) return;
            navigator.clipboard.writeText(logPre.textContent).then(() => {
                const originalText = btn.textContent;
                btn.textContent = '✅ COPIED!';
                setTimeout(() => { btn.textContent = originalText; }, 2000);
            }).catch(err => {
                console.error('Copy failed:', err);
            });
        }

        function copyClipPath(path, btn) {
            navigator.clipboard.writeText(path).then(() => {
                const originalText = btn.textContent;
                btn.textContent = '✅ COPIED!';
                setTimeout(() => { btn.textContent = originalText; }, 2000);
            }).catch(err => {
                console.error('Copy path failed:', err);
            });
        }

        function fillSamplePath(path) {
            const input = document.getElementById('video_path');
            if (input) {
                input.value = path;
                input.focus();
                input.style.borderColor = '#30d158';
                input.style.boxShadow = '0 0 10px rgba(48, 209, 88, 0.4)';
                setTimeout(() => {
                    input.style.borderColor = '';
                    input.style.boxShadow = '';
                }, 1500);
            }
        }

        // Processing Mode Toggle — hide clip count when Full Video is selected
        document.querySelectorAll('input[name="processing_mode"]').forEach(radio => {
            radio.addEventListener('change', function() {
                const clipGroup = document.getElementById('clip-count-group');
                if (clipGroup) {
                    if (this.value === 'full_video') {
                        clipGroup.style.opacity = '0.35';
                        clipGroup.style.pointerEvents = 'none';
                        clipGroup.querySelector('input').disabled = true;
                    } else {
                        clipGroup.style.opacity = '1';
                        clipGroup.style.pointerEvents = 'auto';
                        clipGroup.querySelector('input').disabled = false;
                    }
                }
            });
        });
    </script>
</body>
</html>
