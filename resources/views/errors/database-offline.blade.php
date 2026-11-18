<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RoninClips · Database offline</title>
    <link rel="stylesheet" href="{{ asset('css/app.css') }}">
    <style>
        body { min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 24px 16px; background: var(--color-bg); }
        .db-card { width: 100%; max-width: 640px; background: var(--color-card); border: 1px solid var(--color-border); border-radius: var(--radius-sm); padding: 22px; font-size: 12px; line-height: 1.6; color: var(--color-text-secondary); }
        .db-card h1 { font-size: 15px; color: #fff; margin: 0 0 4px; }
        .db-problem { color: var(--color-warning); margin: 0 0 16px; }
        .db-fix { border-top: 1px solid var(--color-hairline); padding-top: 14px; margin-top: 14px; }
        .db-fix h2 { font-size: 11px; font-weight: 800; color: #fff; margin: 0 0 6px; letter-spacing: 0.04em; }
        .db-fix ol { margin: 0; padding-left: 18px; }
        .db-card code, .db-card pre { font-family: var(--font-mono); color: #fff; }
        .db-card pre { background: #110f0f; border: 1px solid var(--color-border); border-radius: var(--radius-xs); padding: 8px 10px; margin: 6px 0; white-space: pre-wrap; word-break: break-all; }
        .db-note { color: var(--color-text-muted); font-size: 11px; }
        .db-actions { margin-top: 18px; display: flex; gap: 8px; align-items: center; }
        .db-retry { background: #110f0f; border: 1px solid rgba(56, 189, 248, 0.4); color: #38bdf8; border-radius: var(--radius-xs); font: inherit; font-size: 11px; font-weight: 700; padding: 6px 12px; cursor: pointer; }
        .db-retry:hover, .db-retry:focus-visible { background: var(--color-surface-hover); }
        details.db-detail { margin-top: 14px; color: var(--color-text-muted); font-size: 11px; }
        details.db-detail summary { cursor: pointer; }
    </style>
</head>
<body>
    <main class="db-card" role="main">
        <h1>[ DATABASE OFFLINE ]</h1>
        <p class="db-problem">{{ $problem }}</p>

        @if($kind === 'not_running')
            <div class="db-fix">
                <h2>FIX A · START MYSQL</h2>
                <ol>
                    <li>Open the <strong>XAMPP Control Panel</strong> and click <strong>Start</strong> next to MySQL.</li>
                    <li>Wait until it turns green, then press <strong>Retry</strong> below.</li>
                </ol>
            </div>
        @elseif($kind === 'bad_login')
            <div class="db-fix">
                <h2>FIX A · CORRECT THE LOGIN</h2>
                <p>Check <code>DB_USERNAME</code> and <code>DB_PASSWORD</code> in <code>.env</code> (XAMPP's default is user <code>root</code> with an empty password).</p>
            </div>
        @elseif($kind === 'no_database')
            <div class="db-fix">
                <h2>FIX A · CREATE THE DATABASE</h2>
                <p>Run this in the RoninClips folder. Laravel offers to create the database for you:</p>
                <pre>php artisan migrate</pre>
            </div>
        @elseif($kind === 'not_migrated')
            <div class="db-fix">
                <h2>FIX · CREATE THE TABLES</h2>
                <p>Run this in the RoninClips folder, then press Retry:</p>
                <pre>php artisan migrate</pre>
            </div>
        @elseif($kind === 'missing_file')
            <div class="db-fix">
                <h2>FIX · CREATE THE SQLITE FILE</h2>
                <p>Run <code>setup.bat</code> again, or run this in the RoninClips folder (it offers to create the file):</p>
                <pre>php artisan migrate</pre>
            </div>
        @endif

        @if($driver === 'mysql')
            <div class="db-fix">
                <h2>FIX B · USE SQLITE (NO XAMPP NEEDED)</h2>
                <p>RoninClips has a built-in database that needs no server. In <code>.env</code>, change the database line to:</p>
                <pre>DB_CONNECTION=sqlite</pre>
                <p>and put a <code>#</code> in front of the other <code>DB_</code> lines (<code>DB_HOST</code>, <code>DB_DATABASE</code>, …). Then run:</p>
                <pre>php artisan migrate</pre>
                <p class="db-note">SQLite starts empty. Your videos and clips already in MySQL stay there and come back if you switch back.</p>
            </div>
        @endif

        <div class="db-actions">
            <button type="button" class="db-retry" onclick="location.reload()">RETRY</button>
            <span class="db-note">Clip files on disk are not affected.</span>
        </div>

        <details class="db-detail">
            <summary>Technical details</summary>
            <pre>{{ $detail }}</pre>
        </details>
    </main>
</body>
</html>
