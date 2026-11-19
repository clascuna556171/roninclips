<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Twitch Watchlist — RoninClips</title>
    <link rel="stylesheet" href="{{ asset('css/app.css') }}?v={{ file_exists(public_path('css/app.css')) ? filemtime(public_path('css/app.css')) : 1 }}">
    <script src="{{ asset('js/lucide.min.js') }}"></script>
    <link rel="icon" href="{{ asset('favicon.ico') }}" sizes="any">
    <link rel="icon" type="image/svg+xml" href="{{ asset('favicon.svg') }}">
    <link rel="apple-touch-icon" href="{{ asset('apple-touch-icon.png') }}">
</head>
<body class="wl-page">
@php
    $state = $heartbeat['state'] ?? null;
    $current = $heartbeat['current'] ?? null;
    $nextCheck = $heartbeat['next_check_at'] ?? null;
    $lastCheck = $heartbeat['last_check_at'] ?? null;
    $badge = ['queued' => 'status-pending', 'processing' => 'status-processing', 'done' => 'status-completed', 'failed' => 'status-failed'];
    $vodLabel = ['queued' => 'Queued', 'processing' => 'Clipping', 'done' => 'Done', 'failed' => 'Failed'];
@endphp

<div class="studio-workspace">

    <!-- ─── Sidebar: watcher status + followed channels ─── -->
    <aside class="studio-sidebar">
        <a href="{{ route('dashboard') }}" class="nav-link-row nav-link-back">
            <i data-lucide="arrow-left" class="icon-sm"></i>
            <span>[ BACK TO DASHBOARD ]</span>
        </a>

        <div>
            <h1 class="wl-title"><i data-lucide="radio-tower" class="icon-md"></i> Twitch Watchlist</h1>
            <p class="wl-lead">While RoninClips is open, it checks the channels below every hour and clips the 3 best moments of each new VOD. VODs from while your PC was off are caught up, newest first (Twitch keeps them at least 7 days).</p>
        </div>

        <!-- Watcher status -->
        <div class="wl-status {{ $running ? ($state === 'db_offline' ? 'is-warn' : 'is-on') : 'is-off' }}" role="status">
            <div class="wl-status-line">
                @if(!$running)
                    <i data-lucide="pause" class="icon-sm"></i> <strong>Watcher not running</strong>
                @elseif($state === 'processing')
                    <span class="spinner" style="width: 9px; height: 9px;"></span> <strong>Clipping {{ $current['channel'] ?? '' }}</strong>
                @elseif($state === 'checking' || $state === 'starting')
                    <span class="spinner" style="width: 9px; height: 9px;"></span> <strong>Checking channels…</strong>
                @elseif($state === 'db_offline')
                    <i data-lucide="triangle-alert" class="icon-sm"></i> <strong>Waiting for the database</strong>
                @else
                    <i data-lucide="radio-tower" class="icon-sm"></i> <strong>Watching</strong>
                @endif
            </div>
            <div class="wl-status-detail">
                @if(!$running)
                    @if($channels->where('enabled', true)->isEmpty())
                        Follow a channel to start it.
                    @else
                        It normally starts by itself when you open RoninClips. Press Check now to start it.
                    @endif
                @elseif($state === 'processing' && $current)
                    {{ \Illuminate\Support\Str::limit($current['title'] ?? 'Twitch VOD ' . ($current['vod_id'] ?? ''), 70) }}
                    @if(!empty($current['long_video_id']))
                        · <a href="{{ route('dashboard', ['video' => $current['long_video_id']]) }}">live progress</a>
                    @endif
                @elseif($state === 'db_offline')
                    {{ $heartbeat['message'] ?? 'The database is offline.' }}
                @else
                    @if($lastCheck) Last check {{ \Carbon\Carbon::createFromTimestamp($lastCheck)->diffForHumans() }}. @endif
                    @if($nextCheck && $nextCheck > time()) Next in {{ max(1, (int) ceil(($nextCheck - time()) / 60)) }} min. @endif
                @endif
            </div>
            <form action="{{ route('watchlist.check') }}" method="POST" style="margin: 8px 0 0;">
                @csrf
                <button type="submit" class="btn-input-action" @if($channels->where('enabled', true)->isEmpty()) disabled @endif>
                    <i data-lucide="refresh-cw" class="icon-sm"></i> CHECK NOW
                </button>
            </form>
        </div>

        @if(session('success'))
            <div class="wl-flash wl-flash-ok" role="status">{{ session('success') }}</div>
        @endif
        @if(session('error'))
            <div class="wl-flash wl-flash-err" role="alert">{{ session('error') }}</div>
        @endif

        <!-- Add a channel -->
        <form action="{{ route('watchlist.channels.store') }}" method="POST" class="settings-panel wl-add">
            @csrf
            <label for="channel" class="wl-label">[ FOLLOW A CHANNEL ]</label>
            <div class="api-key-input-row">
                <input type="text" id="channel" name="channel" class="text-input" required maxlength="200"
                       placeholder="kaicenat or twitch.tv/kaicenat" autocomplete="off" spellcheck="false" autocapitalize="off"
                       value="{{ old('channel') }}">
                <button type="submit" class="btn-input-action btn-browse"><i data-lucide="plus" class="icon-sm"></i> FOLLOW</button>
            </div>
            <p class="wl-hint">Only its newest VOD is clipped now. Older VODs are skipped, and every new one after that is clipped.</p>
        </form>

        <!-- Followed channels -->
        <div>
            <div class="wl-label" style="margin-bottom: 8px;">[ FOLLOWING ] <span class="wl-muted">{{ $channels->count() }}</span></div>
            @forelse($channels as $ch)
                <div class="wl-channel {{ $ch->enabled ? '' : 'is-paused' }}">
                    <div class="wl-channel-main">
                        <a href="{{ $ch->url() }}" target="_blank" rel="noopener noreferrer" class="wl-channel-name">{{ $ch->login }}</a>
                        <div class="wl-channel-meta">
                            @if(!$ch->enabled)
                                Paused
                            @elseif($ch->last_checked_at)
                                Checked {{ $ch->last_checked_at->diffForHumans() }}
                            @else
                                Not checked yet
                            @endif
                            · {{ $ch->done_count }} clipped @if($ch->queued_count) · {{ $ch->queued_count }} in queue @endif
                        </div>
                        @if($ch->last_error)
                            <div class="wl-channel-error">{{ $ch->last_error }}</div>
                        @endif
                    </div>
                    <div class="wl-channel-actions">
                        <form action="{{ route('watchlist.channels.toggle', $ch) }}" method="POST">
                            @csrf
                            <button type="submit" class="btn-input-action" aria-label="{{ $ch->enabled ? 'Pause' : 'Resume' }} {{ $ch->login }}" title="{{ $ch->enabled ? 'Pause' : 'Resume' }}">
                                <i data-lucide="{{ $ch->enabled ? 'pause' : 'play' }}" class="icon-sm"></i>
                            </button>
                        </form>
                        <form action="{{ route('watchlist.channels.destroy', $ch) }}" method="POST" onsubmit="return confirm('Stop following {{ $ch->login }}? Clips already made are kept.');">
                            @csrf
                            @method('DELETE')
                            <button type="submit" class="btn-input-action" aria-label="Stop following {{ $ch->login }}" title="Stop following">
                                <i data-lucide="trash-2" class="icon-sm"></i>
                            </button>
                        </form>
                    </div>
                </div>
            @empty
                <p class="wl-hint">Not following anyone yet.</p>
            @endforelse
        </div>
    </aside>

    <!-- ─── Main: queue + clips ─── -->
    <main class="studio-canvas">

        <section aria-labelledby="queue-title">
            <div class="canvas-section-header">
                <h2 class="canvas-section-title" id="queue-title"><i data-lucide="list-video" class="icon-sm"></i> [ VODS ]</h2>
            </div>
            @if($vods->isEmpty())
                <div class="wl-empty">No VODs yet. After you follow a channel, its newest VOD shows up here within a minute or two.</div>
            @else
                <div class="wl-vods">
                    @foreach($vods as $vod)
                        @php $clipCount = $vod->longVideo ? $vod->longVideo->clips()->where('status', 'ready')->count() : 0; @endphp
                        <div class="wl-vod">
                            <span class="status-badge {{ $badge[$vod->status] ?? 'status-pending' }}">
                                @if($vod->status === 'processing')<span class="spinner"></span>@endif
                                {{ $vodLabel[$vod->status] ?? $vod->status }}
                            </span>
                            <div class="wl-vod-main">
                                <div class="wl-vod-title">
                                    <span class="wl-vod-channel">{{ $vod->channel->login ?? '?' }}</span>
                                    <a href="{{ $vod->url() }}" target="_blank" rel="noopener noreferrer">{{ $vod->title ?: 'Twitch VOD ' . $vod->vod_id }}</a>
                                </div>
                                <div class="wl-vod-meta">
                                    @if($vod->durationLabel()) {{ $vod->durationLabel() }} · @endif
                                    {{ $vod->updated_at?->diffForHumans() }}
                                    @if($vod->status === 'done') · {{ $clipCount }} {{ \Illuminate\Support\Str::plural('clip', $clipCount) }} @endif
                                </div>
                                @if($vod->status === 'failed' && $vod->error)
                                    <div class="wl-channel-error">{{ $vod->error }}</div>
                                @endif
                            </div>
                            <div class="wl-vod-actions">
                                @if($vod->long_video_id && in_array($vod->status, ['processing', 'done', 'failed']))
                                    <a class="btn-input-action" href="{{ route('dashboard', ['video' => $vod->long_video_id]) }}">
                                        {{ $vod->status === 'processing' ? 'PROGRESS' : ($vod->status === 'done' ? 'EDIT' : 'LOG') }}
                                    </a>
                                @endif
                                @if($vod->status === 'failed')
                                    <form action="{{ route('watchlist.vods.retry', $vod) }}" method="POST">
                                        @csrf
                                        <button type="submit" class="btn-input-action"><i data-lucide="rotate-cw" class="icon-sm"></i> RETRY</button>
                                    </form>
                                @endif
                            </div>
                        </div>
                    @endforeach
                </div>
            @endif
        </section>

        <section aria-labelledby="clips-title">
            <div class="canvas-section-header">
                <h2 class="canvas-section-title" id="clips-title"><i data-lucide="film" class="icon-sm"></i> [ CLIPS ] <span class="wl-muted">{{ $clips->count() }}</span></h2>
            </div>
            @if($clips->isEmpty())
                <div class="wl-empty">Finished clips show up here, newest first. Open one in the editor to fix subtitles or the facecam.</div>
            @else
                <div class="clips-grid">
                    @foreach($clips as $clip)
                        @php
                            $hasVideo = $clip->output_path && file_exists(base_path($clip->output_path));
                            $ver = $clip->updated_at ? $clip->updated_at->timestamp : 1;
                            $src = $hasVideo ? asset(str_replace('storage/app/public/', 'storage/', $clip->output_path)) . '?v=' . $ver : '';
                            $channel = $clip->longVideo->processing_settings['watch_channel'] ?? null;
                            $signal = $clip->metadata['signal_summary'] ?? null;
                        @endphp
                        <article class="clip-card">
                            @if($hasVideo)
                                <div class="clip-video-wrapper">
                                    <video class="clip-video" controls preload="metadata" playsinline>
                                        <source src="{{ $src }}" type="video/mp4">
                                    </video>
                                </div>
                            @endif
                            <div class="clip-card-body wl-clip-body">
                                <h3 class="wl-clip-title">{{ $clip->title }}</h3>
                                <div class="wl-vod-meta">
                                    @if($channel)<span class="wl-vod-channel">{{ $channel }}</span>@endif
                                    {{ $clip->start_time }} – {{ $clip->end_time }} · {{ $clip->created_at?->diffForHumans() }}
                                </div>
                                @if($signal)
                                    <div class="wl-vod-meta"><i data-lucide="activity" class="icon-sm"></i> {{ $signal }}</div>
                                @endif
                                <div class="wl-clip-actions">
                                    @if($hasVideo)
                                        <a class="btn-input-action" href="{{ $src }}" download="{{ \Illuminate\Support\Str::slug(($channel ?? 'clip') . ' ' . $clip->title) }}.mp4">
                                            <i data-lucide="download" class="icon-sm"></i> DOWNLOAD
                                        </a>
                                    @endif
                                    <a class="btn-input-action" href="{{ route('dashboard', ['video' => $clip->long_video_id]) }}">
                                        <i data-lucide="pencil" class="icon-sm"></i> EDIT
                                    </a>
                                </div>
                            </div>
                        </article>
                    @endforeach
                </div>
            @endif
        </section>
    </main>
</div>

<script>
    if (window.lucide) lucide.createIcons();

    // Refresh when the watcher's state changes, but never while you're typing or watching a clip.
    (function () {
        let fingerprint = null;
        const busy = () => {
            const a = document.activeElement;
            if (a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA')) return true;
            return [...document.querySelectorAll('video')].some(v => !v.paused);
        };
        async function poll() {
            try {
                const res = await fetch(@json(route('watchlist.status')), { headers: { 'Accept': 'application/json' } });
                if (!res.ok) return;
                const data = await res.json();
                if (fingerprint !== null && data.fingerprint !== fingerprint && !busy()) {
                    location.reload();
                    return;
                }
                if (fingerprint === null || !busy()) fingerprint = data.fingerprint;
            } catch (e) { /* app restarting; try again next tick */ }
        }
        poll();
        setInterval(poll, 15000);
    })();
</script>
</body>
</html>
