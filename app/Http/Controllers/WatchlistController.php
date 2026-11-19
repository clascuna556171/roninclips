<?php

namespace App\Http\Controllers;

use App\Models\LongVideo;
use App\Models\VideoClip;
use App\Models\WatchChannel;
use App\Models\WatchVod;
use App\Support\Watcher;
use Illuminate\Http\Request;

class WatchlistController extends Controller
{
    public function index()
    {
        Watcher::ensureRunning();

        $channels = WatchChannel::withCount([
            'vods as done_count' => fn ($q) => $q->where('status', 'done'),
            'vods as queued_count' => fn ($q) => $q->whereIn('status', ['queued', 'processing']),
        ])->orderBy('login')->get();

        $vods = WatchVod::with(['channel', 'longVideo'])
            ->where('status', '!=', 'skipped')
            ->orderByRaw("CASE status WHEN 'processing' THEN 0 WHEN 'queued' THEN 1 ELSE 2 END")
            ->orderByDesc('updated_at')
            ->limit(30)
            ->get();

        $clips = $this->watchlistClips();
        $heartbeat = Watcher::heartbeat();
        $running = Watcher::isRunning($heartbeat);

        return view('watchlist', compact('channels', 'vods', 'clips', 'heartbeat', 'running'));
    }

    /** Small JSON the page polls; `fingerprint` changes whenever the page would look different. */
    public function status()
    {
        $heartbeat = Watcher::heartbeat();
        $latestVod = WatchVod::max('updated_at');
        $readyClips = VideoClip::whereIn('long_video_id', $this->watchlistVideoIds())->where('status', 'ready')->count();

        return response()->json([
            'running' => Watcher::isRunning($heartbeat),
            'state' => $heartbeat['state'] ?? null,
            'fingerprint' => md5(json_encode([$latestVod, $readyClips, $heartbeat['state'] ?? null,
                $heartbeat['current']['vod_id'] ?? null, $heartbeat['last_check_at'] ?? null])),
        ]);
    }

    public function storeChannel(Request $request)
    {
        $request->validate(['channel' => 'required|string|max:200']);
        $login = self::parseChannel($request->input('channel'));

        if (!$login) {
            return redirect()->route('watchlist')->with('error',
                'That isn\'t a Twitch channel. Paste a channel name like "kaicenat" or a link like twitch.tv/kaicenat.');
        }
        if (WatchChannel::where('login', $login)->exists()) {
            return redirect()->route('watchlist')->with('error', "You're already following {$login}.");
        }

        WatchChannel::create(['login' => $login]);
        Watcher::requestCheck();
        Watcher::ensureRunning();

        return redirect()->route('watchlist')->with('success',
            "Following {$login}. Its newest VOD will be checked within a minute; older VODs are skipped.");
    }

    public function toggleChannel(WatchChannel $channel)
    {
        $channel->enabled = !$channel->enabled;
        $channel->save();
        if ($channel->enabled) {
            Watcher::requestCheck();
            Watcher::ensureRunning();
        }

        return redirect()->route('watchlist')->with('success',
            $channel->enabled ? "Resumed {$channel->login}." : "Paused {$channel->login}. Its queued VODs wait until you resume it.");
    }

    public function destroyChannel(WatchChannel $channel)
    {
        $login = $channel->login;
        $channel->delete(); // its VOD history goes too; clips already made stay

        return redirect()->route('watchlist')->with('success', "Stopped following {$login}. Clips already made are kept.");
    }

    public function checkNow()
    {
        Watcher::requestCheck();
        $started = Watcher::ensureRunning();

        return redirect()->route('watchlist')->with('success',
            $started ? 'Watcher started. It checks every channel right away.' : 'Checking every channel now.');
    }

    public function retryVod(WatchVod $vod)
    {
        if ($vod->status !== 'failed') {
            return redirect()->route('watchlist')->with('error', 'Only failed VODs can be retried.');
        }
        $vod->update(['status' => 'queued', 'error' => null]);
        Watcher::ensureRunning();

        return redirect()->route('watchlist')->with('success', 'Queued again. It runs after anything already in progress.');
    }

    /**
     * "kaicenat", "@KaiCenat", "twitch.tv/kaicenat", "https://www.twitch.tv/kaicenat/videos" -> "kaicenat".
     * Mirrors LOGIN_RE in processor/watchlist.py.
     */
    public static function parseChannel(string $input): ?string
    {
        $input = trim($input);
        if (preg_match('~^(?:https?://)?(?:www\.|m\.)?twitch\.tv/([A-Za-z0-9_]+)~i', $input, $m)) {
            $input = $m[1];
        }
        $login = strtolower(ltrim($input, '@'));
        $reserved = ['videos', 'directory', 'settings', 'search', 'downloads', 'p', 'jobs', 'turbo'];
        if (!preg_match('/^[a-z0-9_]{3,25}$/', $login) || in_array($login, $reserved, true)) {
            return null;
        }
        return $login;
    }

    private function watchlistVideoIds()
    {
        return LongVideo::all(['id', 'processing_settings'])
            ->filter(fn ($v) => !empty($v->processing_settings['watchlist']))
            ->pluck('id');
    }

    private function watchlistClips()
    {
        return VideoClip::with('longVideo')
            ->whereIn('long_video_id', $this->watchlistVideoIds())
            ->where('status', 'ready')
            ->latest()
            ->limit(36)
            ->get();
    }
}
