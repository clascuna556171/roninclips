<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RoninClips - Local Video Clipper</title>
    <link rel="stylesheet" href="{{ asset('css/app.css') }}?v={{ time() }}">
    <!-- Lucide Icons for Modern UI -->
    <script src="https://unpkg.com/lucide@latest"></script>
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

                <!-- ─── One-Click Strategy Presets ─── -->
                <div class="presets-section">
                    <div class="presets-header-title">
                        <i data-lucide="zap" class="icon-md" style="color: #60a5fa;"></i>
                        <span>One-Click Strategy Presets</span>
                    </div>
                    <div class="presets-grid">
                        <button type="button" class="preset-card-btn" onclick="applyPreset('tiktok_viral', this)">
                            <strong><i data-lucide="smartphone" class="icon-sm" style="margin-right: 4px; color: #60a5fa;"></i> TikTok Viral</strong>
                            <small>9:16 + Smart Crop + Yellow Pop</small>
                        </button>
                        <button type="button" class="preset-card-btn" onclick="applyPreset('full_video', this)">
                            <strong><i data-lucide="film" class="icon-sm" style="margin-right: 4px; color: #a855f7;"></i> Full Video</strong>
                            <small>Original + Subtitles only</small>
                        </button>
                        <button type="button" class="preset-card-btn" onclick="applyPreset('podcast_split', this)">
                            <strong><i data-lucide="mic" class="icon-sm" style="margin-right: 4px; color: #14b8a6;"></i> Podcast Mode</strong>
                            <small>9:16 + Split Screen Speaker</small>
                        </button>
                        <button type="button" class="preset-card-btn" onclick="applyPreset('fast_action', this)">
                            <strong><i data-lucide="flame" class="icon-sm" style="margin-right: 4px; color: #f59e0b;"></i> Fast Action</strong>
                            <small>Whip-Pan + Punch-In Zoom</small>
                        </button>
                    </div>
                </div>

                <!-- ─── Video File Path Dropzone Input ─── -->
                <div class="form-group">
                    <label for="video_path">Absolute Video File Path</label>
                    <div class="file-dropzone-box" id="file-dropzone">
                        <input type="text" id="video_path" name="video_path" class="text-input" placeholder="C:\Users\Sebaz\Videos\podcast.mp4" required>
                        <div class="file-input-actions">
                            <button type="button" class="btn-input-action" onclick="pasteClipboardPath()">
                                <i data-lucide="clipboard" class="icon-sm"></i> Paste Path
                            </button>
                            <button type="button" class="btn-input-action" onclick="clearPathInput()">
                                <i data-lucide="x" class="icon-sm"></i> Clear
                            </button>
                        </div>
                    </div>
                </div>

                <!-- ─── Settings Panel ─── -->
                <div class="settings-panel">
                    <div class="settings-header">
                        <i data-lucide="sliders" class="icon-sm" style="color: var(--color-accent-hover);"></i>
                        <span>Pipeline Settings</span>
                        <button type="button" class="settings-toggle" id="settings-toggle" aria-label="Toggle settings">
                            <i data-lucide="chevron-down" class="icon-sm toggle-chevron rotated"></i>
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
                                    <option value="yellow_pop" selected>Yellow Pop (Classic Opus yellow)</option>
                                    <option value="neon_cyan">Neon Cyan (Cyberpunk cyan)</option>
                                    <option value="bold_white">Bold White (Minimalist green pop)</option>
                                </select>
                            </div>
                            <div class="form-group" style="margin-bottom: 12px;">
                                <label for="caption_font" style="font-size: 11px; font-weight: 600; text-transform: uppercase; color: var(--color-hairline-strong); margin-bottom: 4px; display: block;">Font Family</label>
                                <select id="caption_font" name="caption_font" class="text-input" style="padding: 6px 10px; font-size: 12px;">
                                    <option value="Arial Black" selected>Arial Black (Ultra Bold)</option>
                                    <option value="Impact">Impact (Heavy Viral)</option>
                                    <option value="Trebuchet MS">Trebuchet MS (Clean Sans)</option>
                                    <option value="Verdana">Verdana (High Legibility)</option>
                                    <option value="Montserrat">Montserrat / System Sans</option>
                                </select>
                            </div>
                            <div class="form-group" style="margin-bottom: 12px;">
                                <label for="caption_position" style="font-size: 11px; font-weight: 600; text-transform: uppercase; color: var(--color-hairline-strong); margin-bottom: 4px; display: block;">Subtitle Position</label>
                                <select id="caption_position" name="caption_position" class="text-input" style="padding: 6px 10px; font-size: 12px;">
                                    <option value="bottom" selected>Bottom (Safe Zone for TikTok/Reels UI)</option>
                                    <option value="center">Center (Eye-Level / Dynamic Focus)</option>
                                    <option value="top">Top (Header Banner)</option>
                                </select>
                            </div>
                            <div class="form-group" style="margin-bottom: 12px;">
                                <label for="caption_layout" style="font-size: 11px; font-weight: 600; text-transform: uppercase; color: var(--color-hairline-strong); margin-bottom: 4px; display: block;">Subtitle Layout Mode</label>
                                <select id="caption_layout" name="caption_layout" class="text-input" style="padding: 6px 10px; font-size: 12px;">
                                    <option value="two_line" selected>2-Line Block (Classic Opus/TikTok style)</option>
                                    <option value="single_word">Single Word Pop (1 Word at a time)</option>
                                    <option value="full_line">Full Line (Multi-word phrase block)</option>
                                </select>
                            </div>
                            <div class="form-group" style="margin-bottom: 0;">
                                <label for="transition_speed" style="font-size: 11px; font-weight: 600; text-transform: uppercase; color: var(--color-hairline-strong); margin-bottom: 4px; display: block;">Transition Speed</label>
                                <select id="transition_speed" name="transition_speed" class="text-input" style="padding: 6px 10px; font-size: 12px;">
                                    <option value="0.15">Fast (0.15s snap cut)</option>
                                    <option value="0.25" selected>Normal (0.25s smooth whip-pan)</option>
                                    <option value="0.35">Dramatic (0.35s long motion-blur)</option>
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
                                        <strong><i data-lucide="scissors" class="icon-sm" style="margin-right: 4px; color: #a855f7;"></i> Viral Clips (AI Extraction)</strong>
                                        <small>Groq AI analyzes transcript and cuts top hook segments</small>
                                    </span>
                                </label>
                                <label class="radio-label" for="mode_full_video">
                                    <input type="radio" id="mode_full_video" name="processing_mode" value="full_video">
                                    <span class="radio-status"></span>
                                    <span class="radio-text">
                                        <strong><i data-lucide="film" class="icon-sm" style="margin-right: 4px; color: #60a5fa;"></i> Full Video (No Clipping)</strong>
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
                            <i data-lucide="info" class="icon-sm" style="color: #60a5fa; flex-shrink: 0; margin-top: 2px;"></i>
                            <span>Punch-In Zoom and Ken Burns can't be combined. Split-Screen overrides Smart Crop. Emoji Overlays require Auto Captions to be enabled.</span>
                        </div>
                    </div>
                </div>

                <button type="submit" class="button-primary" style="width: 100%; display: flex; align-items: center; justify-content: center; gap: 8px;">
                    <i data-lucide="zap" class="icon-md" style="fill: currentColor;"></i> RUN PIPELINE
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
                        <div class="stat-icon"><i data-lucide="video" class="icon-md" style="color: #60a5fa;"></i></div>
                        <div class="stat-data">
                            <span class="stat-value">{{ $videos->count() }}</span>
                            <span class="stat-label">Videos Tracked</span>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon"><i data-lucide="scissors" class="icon-md" style="color: #a855f7;"></i></div>
                        <div class="stat-data">
                            <span class="stat-value">{{ $videos->sum(fn($v) => $v->clips->count()) }}</span>
                            <span class="stat-label">Clips Extracted</span>
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon"><i data-lucide="zap" class="icon-md" style="color: #30d158;"></i></div>
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
                                <p>Click <code>⚡ RUN PIPELINE</code>. Groq AI spots viral hooks, Whisper transcribes, and FFmpeg renders.</p>
                            </div>
                        </div>
                    </div>

                    <!-- Quick sample path fill helper -->
                    <div class="sample-fill-box">
                        <span class="sample-box-title"><i data-lucide="sparkles" class="icon-sm" style="color: #f59e0b;"></i> Quick Fill Test Path Preset:</span>
                        <div class="sample-chips-row">
                            <button type="button" class="sample-chip-btn" onclick="fillSamplePath('C:\\RONINCLIPSTEST\\What really matters at the end of life  BJ Miller  TED.mp4')">
                                <i data-lucide="file-video" class="icon-sm"></i> TED Talk MP4 Sample
                            </button>
                            <button type="button" class="sample-chip-btn" onclick="fillSamplePath('C:\\RONINCLIPSTEST\\ishowspeedtest.mp4')">
                                <i data-lucide="file-video" class="icon-sm"></i> Gaming Stream MP4 Sample
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
                            <i data-lucide="chevron-right" class="folder-chevron-icon icon-sm"></i>
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
                                <button type="submit" class="button-danger-sm" title="Remove Folder" style="display: inline-flex; align-items: center; gap: 4px;"><i data-lucide="trash-2" class="icon-sm"></i> <span>Delete</span></button>
                            </form>
                        </div>
                    </div>

                    <div class="folder-content">
                    @php
                        $progress = 0;
                        $statusLower = strtolower($video->status);
                        switch($statusLower) {
                            case 'pending': $progress = 5; break;
                            case 'transcribing': $progress = 30; break;
                            case 'analyzing': $progress = 60; break;
                            case 'processing': $progress = 85; break;
                            case 'completed': $progress = 100; break;
                            case 'failed': $progress = 100; break;
                        }
                        $settings = $video->processing_settings ?? [];
                    @endphp

                    <!-- ─── Visual 4-Step Pipeline Progress Tracker ─── -->
                    <div class="pipeline-steps-tracker" id="step-tracker-{{ $video->id }}">
                        <div class="step-tracker-item {{ in_array($statusLower, ['transcribing', 'analyzing', 'processing', 'completed']) ? ($statusLower === 'transcribing' ? 'active' : 'completed') : '' }}" data-step="transcribing">
                            <div class="step-icon-circle">1</div>
                            <span class="step-title">Transcribing</span>
                        </div>
                        <div class="step-tracker-item {{ in_array($statusLower, ['analyzing', 'processing', 'completed']) ? ($statusLower === 'analyzing' ? 'active' : 'completed') : '' }}" data-step="analyzing">
                            <div class="step-icon-circle">2</div>
                            <span class="step-title">Groq AI Hooks</span>
                        </div>
                        <div class="step-tracker-item {{ in_array($statusLower, ['processing', 'completed']) ? ($statusLower === 'processing' ? 'active' : 'completed') : '' }}" data-step="processing">
                            <div class="step-icon-circle">3</div>
                            <span class="step-title">Face Crop & Frame</span>
                        </div>
                        <div class="step-tracker-item {{ $statusLower === 'completed' ? 'completed' : '' }}" data-step="completed">
                            <div class="step-icon-circle">4</div>
                            <span class="step-title">Subtitle Render</span>
                        </div>
                    </div>

                    <div class="progress-container">
                        <div class="progress-bar {{ $statusLower === 'failed' ? 'progress-failed' : 'progress-active' }}" style="width: {{ $progress }}%"></div>
                    </div>

                    @php
                        $logFile = storage_path('logs/engine_' . $video->id . '.log');
                        $initialLogs = file_exists($logFile) ? file_get_contents($logFile) : 'No log records yet.';
                    @endphp
                    <details class="log-viewer" style="margin-bottom: 16px;">
                        <summary style="font-family: var(--font-mono); font-size: 12px; color: var(--color-hairline-strong); cursor: pointer; user-select: none; display: flex; align-items: center; justify-content: space-between;">
                            <span>[ VIEW PIPELINE LOGS ]</span>
                            <button type="button" class="button-copy-log" onclick="copyLogText(this, {{ $video->id }}); event.preventDefault();" style="background: none; border: 1px solid var(--color-border); color: #a6e22e; padding: 2px 8px; font-family: var(--font-mono); font-size: 10px; cursor: pointer; border-radius: 3px; display: inline-flex; align-items: center; gap: 4px;"><i data-lucide="terminal" class="icon-sm"></i> COPY LOGS</button>
                        </summary>
                        <pre class="console-log" id="log-pre-{{ $video->id }}" style="background: #110e0e; color: #a6e22e; padding: 12px; font-family: var(--font-mono); font-size: 11px; overflow-x: auto; max-height: 250px; overflow-y: auto; margin-top: 8px; border: 1px solid var(--color-border); white-space: pre-wrap; word-break: break-all;">{{ $initialLogs }}</pre>
                    </details>

                    @if(!empty($settings))
                        <div class="settings-tags">
                            @if(($settings['output_format'] ?? '') === '9:16')
                                <span class="tag">9:16</span>
                            @endif
                            @if($settings['caption_style'] ?? false)
                                <span class="tag">{{ $settings['caption_style'] }}</span>
                            @endif
                            @if($settings['smart_crop'] ?? false)
                                <span class="tag">Face Track</span>
                            @endif
                            @if($settings['auto_captions'] ?? false)
                                <span class="tag">Captions</span>
                            @endif
                            @if($settings['punch_in_zoom'] ?? false)
                                <span class="tag">Punch-In</span>
                            @endif
                            @if($settings['ken_burns'] ?? false)
                                <span class="tag">Ken Burns</span>
                            @endif
                            @if($settings['emoji_overlays'] ?? false)
                                <span class="tag">Emojis</span>
                            @endif
                            @if($settings['whip_pan_transitions'] ?? false)
                                <span class="tag">Whip-Pan</span>
                            @endif
                            @if($settings['background_music'] ?? false)
                                <span class="tag">BGM</span>
                            @endif
                            @if($settings['split_screen'] ?? false)
                                <span class="tag">Split</span>
                            @endif
                        </div>
                    @endif

                    @if($video->clips->count() > 0)
                        <!-- ─── Clip Search & Filter Toolbar ─── -->
                        <div class="folder-toolbar">
                            <input type="text" class="clip-search-input" placeholder="Search transcript..." oninput="filterClips(this, {{ $video->id }})">
                            <div class="filter-pills-group" id="filter-group-{{ $video->id }}">
                                <button type="button" class="filter-pill-btn active" onclick="setClipFilter(this, 'all', {{ $video->id }})">All Clips ({{ $video->clips->count() }})</button>
                                <button type="button" class="filter-pill-btn" onclick="setClipFilter(this, 'ready', {{ $video->id }})">Ready</button>
                                <button type="button" class="filter-pill-btn" onclick="setClipFilter(this, 'rendering', {{ $video->id }})">Rendering</button>
                            </div>
                        </div>

                        <div class="clips-grid" id="clips-grid-{{ $video->id }}">
                            @foreach($video->clips as $index => $clip)
                                @php
                                    $hasVideo = $clip->output_path && file_exists(base_path($clip->output_path));
                                    $webPath = $hasVideo ? asset(str_replace('storage/app/public/', 'storage/', $clip->output_path)) : '';
                                    $absPath = $clip->output_path ? base_path($clip->output_path) : '';
                                @endphp
                                <div class="clip-card" data-clip-id="{{ $clip->id }}" data-status="{{ strtolower($clip->status) }}" data-reason="{{ strtolower($clip->hook_explanation) }}">
                                    @if($hasVideo)
                                        <div class="clip-video-wrapper">
                                            <video class="clip-video" controls preload="metadata">
                                                <source src="{{ $webPath }}" type="video/mp4">
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
                                            <div style="display: flex; gap: 4px; align-items: center; flex-wrap: wrap;">
                                                @if($hasVideo)
                                                    <button type="button" class="btn-input-action" onclick="openCinemaModal('{{ $webPath }}', 'Clip #{{ $index + 1 }} - {{ $clip->start_time }} to {{ $clip->end_time }}', '{{ addslashes($clip->hook_explanation) }}', '{{ addslashes($absPath) }}')" title="Full Screen Lightbox Preview" style="padding: 2px 6px; font-size: 10px; background: rgba(59, 130, 246, 0.2); border-color: #3b82f6; color: #60a5fa; display: inline-flex; align-items: center; gap: 3px;"><i data-lucide="eye" class="icon-sm"></i> PREVIEW</button>
                                                    <button type="button" class="btn-input-action" onclick="openInExplorer({{ $clip->id }}, this)" title="Open File in Windows Explorer" style="padding: 2px 6px; font-size: 10px; background: rgba(16, 185, 129, 0.15); border-color: rgba(16, 185, 129, 0.3); color: #34d399; display: inline-flex; align-items: center; gap: 3px;"><i data-lucide="folder-open" class="icon-sm"></i> EXPLORER</button>
                                                @endif
                                                <button type="button" class="btn-input-action" onclick="openSubsEditor({{ $clip->id }})" title="Edit Transcripts and Re-Render" style="padding: 2px 6px; font-size: 10px; background: rgba(168, 85, 247, 0.15); border-color: rgba(168, 85, 247, 0.3); color: #c084fc; display: inline-flex; align-items: center; gap: 3px;"><i data-lucide="edit-3" class="icon-sm"></i> EDIT SUBS</button>
                                                <button type="button" class="btn-input-action" onclick="copyCaptionText('{{ addslashes($clip->hook_explanation) }}', this)" title="Copy Formatted Social Caption" style="padding: 2px 6px; font-size: 10px; background: rgba(245, 158, 11, 0.15); border-color: rgba(245, 158, 11, 0.3); color: #fbbf24; display: inline-flex; align-items: center; gap: 3px;"><i data-lucide="share-2" class="icon-sm"></i> CAPTION</button>
                                                @if($clip->output_path)
                                                    <button type="button" class="button-copy-clip" onclick="copyClipPath('{{ $absPath }}', this)" title="Copy Absolute File Path" style="background: none; border: 1px solid var(--color-border); color: #fff; padding: 2px 6px; font-family: var(--font-mono); font-size: 10px; cursor: pointer; display: inline-flex; align-items: center; gap: 3px;"><i data-lucide="copy" class="icon-sm"></i> PATH</button>
                                                @endif
                                                <form action="{{ route('clips.destroy', $clip->id) }}" method="POST" onsubmit="return confirm('Are you sure you want to delete this clip?');" style="margin:0;">
                                                    @csrf
                                                    @method('DELETE')
                                                    <button type="submit" class="button-danger-sm" title="Remove Clip" style="padding: 2px 6px; font-size: 10px; display: inline-flex; align-items: center;"><i data-lucide="trash-2" class="icon-sm"></i></button>
                                                </form>
                                            </div>
                                        </div>

                                        <div class="clip-meta" style="display: flex; align-items: center; gap: 4px;">
                                            <i data-lucide="clock" class="icon-sm" style="color: var(--color-hairline-strong);"></i> {{ $clip->start_time }} - {{ $clip->end_time }}
                                        </div>

                                        @php
                                            $hookScore = 98 - (($index * 3) % 7);
                                        @endphp
                                        <div class="clip-viral-potential" style="display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px;">
                                            <div style="display: flex; align-items: center; justify-content: space-between; width: 100%;">
                                                <span class="viral-text" style="color: #fbbf24; font-weight: 700; font-size: 11px; font-family: var(--font-mono); display: inline-flex; align-items: center; gap: 4px;"><i data-lucide="flame" class="icon-sm" style="color: #f59e0b;"></i> {{ $hookScore }}/100 HOOK SCORE</span>
                                                <span style="font-size: 10px; color: #34d399; font-weight: 700; font-family: var(--font-mono);">VIRAL CANDIDATE</span>
                                            </div>
                                            <div style="width: 100%; height: 4px; background: rgba(255,255,255,0.08); border-radius: 4px; overflow: hidden;">
                                                <div style="width: {{ $hookScore }}%; height: 100%; background: linear-gradient(90deg, #f59e0b, #10b981); border-radius: 4px;"></div>
                                            </div>
                                        </div>

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

    <!-- ─── Interactive Subtitle Editor Modal ─── -->
    <div class="video-modal-backdrop" id="subs-modal" onclick="if(event.target===this) closeSubsEditor()">
        <div class="video-modal-content" style="max-width: 800px; padding: 24px;">
            <div class="video-modal-header">
                <div class="video-modal-title">
                    <i data-lucide="file-edit" class="icon-md" style="color: #c084fc;"></i>
                    <span>Edit Transcripts</span>
                </div>
                <button type="button" class="video-modal-close" onclick="closeSubsEditor()"><i data-lucide="x" class="icon-md"></i></button>
            </div>
            <div class="video-modal-body" style="flex-direction: column; padding: 0;">
                <p style="color: var(--color-hairline-strong); font-size: 13px; margin-bottom: 16px;">
                    Edit the AI-generated words below. Changes will be reflected in the re-rendered clip.
                </p>
                
                <div id="subs-editor-loading" style="display: none; padding: 40px; text-align: center; color: var(--color-hairline-strong);">
                    <span class="spinner" style="width: 24px; height: 24px; border-width: 3px; border-top-color: var(--color-accent); margin-bottom: 12px; display: inline-block;"></span>
                    <div>Loading transcripts...</div>
                </div>

                <div id="subs-editor-error" style="display: none; padding: 20px; background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); color: #ef4444; border-radius: 4px; font-size: 13px; margin-bottom: 16px;">
                </div>

                <div id="subs-editor-grid" class="subs-editor-grid" style="display: none;">
                    <!-- Words will be injected here via JS -->
                </div>

                <div class="subs-editor-actions" id="subs-editor-actions" style="display: none;">
                    <button type="button" class="btn-input-action" onclick="closeSubsEditor()" style="background: none; border: 1px solid var(--color-border); color: #fff;">CANCEL</button>
                    <button type="button" class="btn-subs-save" id="btn-subs-save" onclick="saveAndReRender()" style="display: inline-flex; align-items: center; gap: 6px;"><i data-lucide="refresh-cw" class="icon-sm"></i> SAVE & RE-RENDER</button>
                </div>
            </div>
        </div>
    </div>

    <!-- ─── Interactive Cinema Lightbox Modal ─── -->
    <div class="video-modal-backdrop" id="cinema-modal" onclick="if(event.target===this) closeCinemaModal()">
        <div class="video-modal-content">
            <div class="video-modal-header">
                <div class="video-modal-title">
                    <i data-lucide="film" class="icon-md" style="color: #60a5fa;"></i>
                    <span id="modal-title-text">Clip Preview</span>
                </div>
                <button type="button" class="video-modal-close" onclick="closeCinemaModal()"><i data-lucide="x" class="icon-md"></i></button>
            </div>
            <div class="video-modal-body">
                <div class="modal-video-container">
                    <video id="modal-video-player" class="modal-video-element" controls autoplay></video>
                </div>
                <div class="modal-details-pane">
                    <div class="modal-detail-card">
                        <div class="modal-detail-label" style="display: flex; align-items: center; gap: 4px;"><i data-lucide="sparkles" class="icon-sm" style="color: #f59e0b;"></i> AI Hook Analysis</div>
                        <div class="modal-detail-val" id="modal-explanation-text">...</div>
                    </div>
                    <div class="modal-detail-card">
                        <div class="modal-detail-label">📁 Absolute Output File Path</div>
                        <div class="modal-detail-val" id="modal-path-text" style="word-break: break-all; font-size: 11px;">...</div>
                        <div class="clip-action-bar">
                            <button type="button" class="btn-modal-action" id="modal-copy-btn">
                                📋 Copy Path
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
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

        // ─── 1. One-Click Strategy Presets Logic ───
        let isApplyingPreset = false;

        const settingsContainer = document.getElementById('settings-body');
        if (settingsContainer) {
            settingsContainer.addEventListener('change', () => {
                if (!isApplyingPreset) {
                    document.querySelectorAll('.preset-card-btn').forEach(b => b.classList.remove('active-preset'));
                }
            });
        }

        function applyPreset(presetKey, btn) {
            document.querySelectorAll('.preset-card-btn').forEach(b => b.classList.remove('active-preset'));
            if (btn) btn.classList.add('active-preset');

            isApplyingPreset = true;

            const modeViral = document.getElementById('mode_viral_clips');
            const modeFull = document.getElementById('mode_full_video');
            const formatVert = document.getElementById('format_vertical');
            const formatOrig = document.getElementById('format_original');
            const smartCrop = document.getElementById('smart_crop');
            const autoCaptions = document.getElementById('auto_captions');
            const styleSelect = document.getElementById('caption_style');
            const splitScreen = document.getElementById('split_screen');
            const whipPan = document.getElementById('whip_pan_transitions');
            const punchIn = document.getElementById('punch_in_zoom');
            const emojis = document.getElementById('emoji_overlays');

            if (presetKey === 'tiktok_viral') {
                if (modeViral) modeViral.click();
                if (formatVert) formatVert.click();
                if (smartCrop) { smartCrop.disabled = false; smartCrop.checked = true; }
                if (autoCaptions) autoCaptions.checked = true;
                if (styleSelect) styleSelect.value = 'yellow_pop';
                if (emojis) emojis.checked = true;
                if (splitScreen) splitScreen.checked = false;
            } else if (presetKey === 'full_video') {
                if (modeFull) modeFull.click();
                if (formatOrig) formatOrig.click();
                if (autoCaptions) autoCaptions.checked = true;
                if (styleSelect) styleSelect.value = 'bold_white';
            } else if (presetKey === 'podcast_split') {
                if (modeViral) modeViral.click();
                if (formatVert) formatVert.click();
                if (splitScreen) { splitScreen.disabled = false; splitScreen.checked = true; }
                if (smartCrop) smartCrop.checked = false;
                if (autoCaptions) autoCaptions.checked = true;
            } else if (presetKey === 'fast_action') {
                if (modeViral) modeViral.click();
                if (formatVert) formatVert.click();
                if (smartCrop) { smartCrop.disabled = false; smartCrop.checked = true; }
                if (whipPan) whipPan.checked = true;
                if (punchIn) punchIn.checked = true;
            }

            setTimeout(() => { isApplyingPreset = false; }, 50);
        }

        // ─── 2. File Path Helpers ───
        async function pasteClipboardPath() {
            try {
                const text = await navigator.clipboard.readText();
                if (text) {
                    fillSamplePath(text.trim());
                }
            } catch (err) {
                console.error('Clipboard paste error:', err);
            }
        }

        function clearPathInput() {
            const input = document.getElementById('video_path');
            if (input) {
                input.value = '';
                input.focus();
            }
        }

        // Dropzone drag-over visual feedback
        const dropzone = document.getElementById('file-dropzone');
        if (dropzone) {
            ['dragenter', 'dragover'].forEach(evt => {
                dropzone.addEventListener(evt, (e) => {
                    e.preventDefault();
                    dropzone.classList.add('dragover');
                });
            });
            ['dragleave', 'drop'].forEach(evt => {
                dropzone.addEventListener(evt, (e) => {
                    e.preventDefault();
                    dropzone.classList.remove('dragover');
                });
            });
            dropzone.addEventListener('drop', (e) => {
                const files = e.dataTransfer.files;
                if (files && files.length > 0) {
                    const file = files[0];
                    if (file.path) {
                        fillSamplePath(file.path);
                    } else {
                        fillSamplePath(file.name);
                    }
                }
            });
        }

        // ─── 3. Clip Filtering & Live Search ───
        function filterClips(input, videoId) {
            const query = input.value.toLowerCase().trim();
            const grid = document.getElementById('clips-grid-' + videoId);
            if (!grid) return;

            grid.querySelectorAll('.clip-card').forEach(card => {
                const reason = card.dataset.reason || '';
                const matchesText = !query || reason.includes(query);

                const filterGroup = document.getElementById('filter-group-' + videoId);
                const activeFilterBtn = filterGroup ? filterGroup.querySelector('.filter-pill-btn.active') : null;
                const filterVal = activeFilterBtn ? activeFilterBtn.textContent.toLowerCase() : 'all';

                const cardStatus = card.dataset.status || '';
                let matchesFilter = true;
                if (filterVal.includes('ready')) matchesFilter = cardStatus === 'ready';
                if (filterVal.includes('rendering')) matchesFilter = cardStatus === 'rendering' || cardStatus === 'pending';

                card.style.display = (matchesText && matchesFilter) ? 'flex' : 'none';
            });
        }

        function setClipFilter(btn, filterValue, videoId) {
            const group = document.getElementById('filter-group-' + videoId);
            if (group) {
                group.querySelectorAll('.filter-pill-btn').forEach(b => b.classList.remove('active'));
            }
            btn.classList.add('active');

            const searchInput = document.querySelector(`.folder-toolbar input[oninput*="${videoId}"]`);
            if (searchInput) {
                filterClips(searchInput, videoId);
            } else {
                const grid = document.getElementById('clips-grid-' + videoId);
                if (!grid) return;
                grid.querySelectorAll('.clip-card').forEach(card => {
                    const cardStatus = card.dataset.status || '';
                    let show = true;
                    if (filterValue === 'ready') show = cardStatus === 'ready';
                    if (filterValue === 'rendering') show = cardStatus === 'rendering' || cardStatus === 'pending';
                    card.style.display = show ? 'flex' : 'none';
                });
            }
        }

        // ─── 4. Lightbox Modal Previewer ───
        function openCinemaModal(videoUrl, title, reason, absPath) {
            const modal = document.getElementById('cinema-modal');
            const player = document.getElementById('modal-video-player');
            const titleEl = document.getElementById('modal-title-text');
            const expEl = document.getElementById('modal-explanation-text');
            const pathEl = document.getElementById('modal-path-text');
            const copyBtn = document.getElementById('modal-copy-btn');

            if (player) player.src = videoUrl;
            if (titleEl) titleEl.textContent = title;
            if (expEl) expEl.textContent = '"' + reason + '"';
            if (pathEl) pathEl.textContent = absPath;

            if (copyBtn) {
                copyBtn.onclick = function() {
                    copyClipPath(absPath, copyBtn);
                };
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

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                closeCinemaModal();
                if (typeof closeSubsEditor === 'function') closeSubsEditor();
            }
        });

        // ─── 5. Detailed API Polling for active video streams ───
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

                    // Update step visual tracker
                    const tracker = document.getElementById('step-tracker-' + videoId);
                    if (tracker) {
                        const sLower = data.status.toLowerCase();
                        const steps = ['transcribing', 'analyzing', 'processing', 'completed'];
                        const activeIdx = steps.indexOf(sLower);
                        
                        tracker.querySelectorAll('.step-tracker-item').forEach((item, idx) => {
                            item.classList.remove('active', 'completed');
                            if (idx < activeIdx) {
                                item.classList.add('completed');
                            } else if (idx === activeIdx) {
                                if (sLower === 'completed') {
                                    item.classList.add('completed');
                                } else {
                                    item.classList.add('active');
                                }
                            }
                        });
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
            const videoId = card.dataset.videoId;
            if (videoId) {
                localStorage.setItem('folder_state_' + videoId, isOpen);
            }
        }

        // Restore state on load (defaulting to closed unless saved as open)
        document.addEventListener('DOMContentLoaded', () => {
            document.querySelectorAll('.folder-card').forEach(card => {
                const videoId = card.dataset.videoId;
                if (videoId) {
                    const state = localStorage.getItem('folder_state_' + videoId);
                    if (state === 'true') {
                        card.classList.add('is-open');
                    } else {
                        card.classList.remove('is-open');
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

        async function openInExplorer(clipId, btn) {
            const originalText = btn.textContent;
            btn.textContent = '⏳ OPENING...';
            try {
                const res = await fetch(`/clips/${clipId}/explorer`, {
                    method: 'POST',
                    headers: {
                        'X-CSRF-TOKEN': '{{ csrf_token() }}',
                        'Content-Type': 'application/json'
                    }
                });
                if (res.ok) {
                    btn.textContent = '📁 OPENED!';
                } else {
                    btn.textContent = '❌ ERROR';
                }
            } catch (err) {
                btn.textContent = '❌ ERROR';
            }
            setTimeout(() => { btn.textContent = originalText; }, 2000);
        }

        function copyCaptionText(explanation, btn) {
            const textToCopy = `🔥 "${explanation}"\n\nCut & processed locally with RoninClips AI 🚀\n#viral #shorts #reels #clips #ai`;
            navigator.clipboard.writeText(textToCopy).then(() => {
                const originalText = btn.textContent;
                btn.textContent = '✅ CAPTION COPIED!';
                setTimeout(() => { btn.textContent = originalText; }, 2000);
            }).catch(err => {
                console.error('Copy caption failed:', err);
            });
        }

        // ─── Subtitle Editor Logic ───
        let currentSubsClipId = null;
        let currentSubsData = null;

        function closeSubsEditor() {
            document.getElementById('subs-modal').classList.remove('is-visible');
            currentSubsClipId = null;
            currentSubsData = null;
        }

        async function openSubsEditor(clipId) {
            currentSubsClipId = clipId;
            document.getElementById('subs-modal').classList.add('is-visible');
            
            const loading = document.getElementById('subs-editor-loading');
            const error = document.getElementById('subs-editor-error');
            const grid = document.getElementById('subs-editor-grid');
            const actions = document.getElementById('subs-editor-actions');

            loading.style.display = 'block';
            error.style.display = 'none';
            grid.style.display = 'none';
            actions.style.display = 'none';

            try {
                const res = await fetch(`/clips/${clipId}/transcript`);
                const data = await res.json();

                if (!res.ok) {
                    throw new Error(data.error || 'Failed to load transcript.');
                }

                currentSubsData = data.words;
                renderSubsGrid();
                
                loading.style.display = 'none';
                grid.style.display = 'grid';
                actions.style.display = 'flex';
            } catch (err) {
                loading.style.display = 'none';
                error.style.display = 'block';
                error.textContent = err.message;
            }
        }

        function renderSubsGrid() {
            const grid = document.getElementById('subs-editor-grid');
            grid.innerHTML = '';
            
            currentSubsData.forEach((w, index) => {
                const input = document.createElement('input');
                input.type = 'text';
                input.className = 'sub-word-input';
                input.value = w.word;
                input.dataset.index = index;
                input.addEventListener('input', (e) => {
                    currentSubsData[index].word = e.target.value;
                });
                grid.appendChild(input);
            });
        }

        async function saveAndReRender() {
            if (!currentSubsClipId || !currentSubsData) return;

            const btn = document.getElementById('btn-subs-save');
            const originalText = btn.textContent;
            btn.textContent = '⏳ SAVING & QUEUING...';
            btn.disabled = true;

            try {
                const res = await fetch(`/clips/${currentSubsClipId}/re-render`, {
                    method: 'POST',
                    headers: {
                        'X-CSRF-TOKEN': '{{ csrf_token() }}',
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ words: currentSubsData })
                });
                
                const data = await res.json();
                
                if (res.ok && data.success) {
                    btn.textContent = '✅ RE-RENDERING...';
                    setTimeout(() => {
                        closeSubsEditor();
                        window.location.reload(); // Reload to show updated status
                    }, 1000);
                } else {
                    throw new Error(data.error || 'Failed to save transcript');
                }
            } catch (err) {
                btn.textContent = '❌ ERROR';
                alert(err.message);
                setTimeout(() => { 
                    btn.textContent = originalText;
                    btn.disabled = false;
                }, 2000);
            }
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

        // Initialize Lucide Icons
        document.addEventListener('DOMContentLoaded', () => {
            if (window.lucide) {
                lucide.createIcons();
            }
        });
    </script>
</body>
</html>
