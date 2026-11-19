<?php

use App\Http\Controllers\WatchlistController;
use App\Models\LongVideo;
use App\Models\VideoClip;
use App\Models\WatchChannel;
use App\Models\WatchVod;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\File;

uses(RefreshDatabase::class);

// Never touch the real storage/app/watchlist (heartbeat / check_now) from tests.
beforeEach(function () {
    $this->tmpStorage = sys_get_temp_dir() . DIRECTORY_SEPARATOR . 'rc_wl_' . uniqid();
    File::ensureDirectoryExists($this->tmpStorage . '/logs');
    $this->app->useStoragePath($this->tmpStorage);
});

afterEach(function () {
    File::deleteDirectory($this->tmpStorage);
});

function watchJob(string $channel = 'kaicenat', string $status = 'completed'): LongVideo
{
    return LongVideo::create([
        'filename' => "{$channel} · Big Stream",
        'storage_path' => '',
        'status' => $status,
        'processing_settings' => ['watchlist' => true, 'watch_channel' => $channel, 'stream_moments' => true,
            'sparse_download' => true, 'source_url' => 'https://www.twitch.tv/videos/2932305259'],
    ]);
}

it('parses channel names and links', function (string $input, ?string $expected) {
    expect(WatchlistController::parseChannel($input))->toBe($expected);
})->with([
    ['kaicenat', 'kaicenat'],
    ['  @KaiCenat ', 'kaicenat'],
    ['twitch.tv/jasontheween', 'jasontheween'],
    ['https://www.twitch.tv/ishowspeed/videos?filter=archives', 'ishowspeed'],
    ['https://m.twitch.tv/Jynxzi', 'jynxzi'],
    ['https://www.twitch.tv/videos/2932305259', null],
    ['ab', null],
    ['not a channel!', null],
    ['https://youtube.com/@speed', null],
]);

it('shows the empty page', function () {
    $this->get('/watchlist')
        ->assertOk()
        ->assertSee('Twitch Watchlist')
        ->assertSee('Not following anyone yet.')
        ->assertSee('Watcher not running')
        ->assertSee('Follow a channel to start it.');
});

it('follows a channel and asks the watcher to check now', function () {
    $this->post('/watchlist/channels', ['channel' => 'https://www.twitch.tv/KaiCenat'])
        ->assertRedirect('/watchlist')
        ->assertSessionHas('success');

    expect(WatchChannel::pluck('login')->all())->toBe(['kaicenat']);
    expect(file_exists(storage_path('app/watchlist/check_now')))->toBeTrue();
});

it('rejects duplicates and non-channels', function () {
    WatchChannel::create(['login' => 'kaicenat']);

    $this->post('/watchlist/channels', ['channel' => '@KAICENAT'])->assertSessionHas('error');
    $this->post('/watchlist/channels', ['channel' => 'twitch.tv/videos/123'])->assertSessionHas('error');
    expect(WatchChannel::count())->toBe(1);
});

it('pauses, resumes and unfollows while keeping clips', function () {
    $ch = WatchChannel::create(['login' => 'kaicenat']);
    $job = watchJob();
    WatchVod::create(['watch_channel_id' => $ch->id, 'vod_id' => '1', 'status' => 'done', 'long_video_id' => $job->id]);

    $this->post("/watchlist/channels/{$ch->id}/toggle")->assertRedirect('/watchlist');
    expect($ch->fresh()->enabled)->toBeFalse();
    $this->post("/watchlist/channels/{$ch->id}/toggle");
    expect($ch->fresh()->enabled)->toBeTrue();

    $this->delete("/watchlist/channels/{$ch->id}")->assertRedirect('/watchlist');
    expect(WatchChannel::count())->toBe(0)
        ->and(WatchVod::count())->toBe(0)
        ->and(LongVideo::find($job->id))->not->toBeNull();
});

it('retries only failed VODs', function () {
    $ch = WatchChannel::create(['login' => 'kaicenat']);
    $failed = WatchVod::create(['watch_channel_id' => $ch->id, 'vod_id' => '1', 'status' => 'failed', 'error' => 'x']);
    $done = WatchVod::create(['watch_channel_id' => $ch->id, 'vod_id' => '2', 'status' => 'done']);

    $this->post("/watchlist/vods/{$failed->id}/retry")->assertSessionHas('success');
    $this->post("/watchlist/vods/{$done->id}/retry")->assertSessionHas('error');

    expect($failed->fresh()->only('status', 'error'))->toBe(['status' => 'queued', 'error' => null])
        ->and($done->fresh()->status)->toBe('done');
});

it('lists VODs and ready clips with an editor link', function () {
    $ch = WatchChannel::create(['login' => 'kaicenat']);
    $job = watchJob();
    WatchVod::create(['watch_channel_id' => $ch->id, 'vod_id' => '2932305259', 'title' => 'PLAYING GTA 6',
        'duration_s' => 57825, 'status' => 'done', 'long_video_id' => $job->id]);
    WatchVod::create(['watch_channel_id' => $ch->id, 'vod_id' => '99', 'title' => 'Old one', 'status' => 'skipped']);
    WatchVod::create(['watch_channel_id' => $ch->id, 'vod_id' => '98', 'title' => 'Broken one', 'status' => 'failed',
        'error' => 'This Twitch VOD is subscriber-only.']);
    VideoClip::create(['long_video_id' => $job->id, 'start_time' => '01:00:00', 'end_time' => '01:00:45', 'status' => 'ready',
        'hook_explanation' => json_encode(['title' => 'Kai loses it', 'signal_summary' => 'Chat spiked 8x'])]);

    $this->get('/watchlist')
        ->assertOk()
        ->assertSee('PLAYING GTA 6')
        ->assertSee('16h 03m')
        ->assertDontSee('Old one')
        ->assertSee('This Twitch VOD is subscriber-only.')
        ->assertSee('Kai loses it')
        ->assertSee('Chat spiked 8x')
        ->assertSee(route('dashboard', ['video' => $job->id]), false);
});

it('keeps watchlist jobs off the dashboard unless one is opened', function () {
    $mine = LongVideo::create(['filename' => 'my_podcast.mp4', 'storage_path' => 'C:/x.mp4', 'status' => 'completed',
        'processing_settings' => ['stream_moments' => false]]);
    $job = watchJob();

    $this->get('/')->assertOk()->assertSee('my_podcast.mp4')->assertDontSee('kaicenat · Big Stream');

    $this->get('/?video=' . $job->id)
        ->assertOk()
        ->assertSee('kaicenat · Big Stream')
        ->assertDontSee('my_podcast.mp4')
        ->assertSee('Back to Watchlist');
});

it('reports watcher status from the heartbeat', function () {
    $this->getJson('/watchlist/status')->assertOk()->assertJson(['running' => false]);

    File::ensureDirectoryExists(storage_path('app/watchlist'));
    file_put_contents(storage_path('app/watchlist/heartbeat.json'),
        json_encode(['updated_at' => time(), 'state' => 'idle', 'last_check_at' => time() - 60, 'next_check_at' => time() + 3540]));

    $this->getJson('/watchlist/status')->assertJson(['running' => true, 'state' => 'idle']);
    WatchChannel::create(['login' => 'kaicenat']);
    $this->get('/watchlist')->assertSee('Watching')->assertSee('Next in 59 min.');

    file_put_contents(storage_path('app/watchlist/heartbeat.json'), json_encode(['updated_at' => time() - 600, 'state' => 'idle']));
    $this->getJson('/watchlist/status')->assertJson(['running' => false]);
});

it('shows audio download progress for sparse imports', function () {
    $job = watchJob('kaicenat', 'pending');
    File::ensureDirectoryExists(storage_path('logs'));
    file_put_contents(storage_path("logs/engine_{$job->id}.log"),
        "Importing Twitch VOD 1 (sparse)...\nDownloading audio: 50.0% of 1.47GiB at 5MiB/s, ETA 02:30\n");

    $this->getJson("/videos/{$job->id}/logs")
        ->assertJson(['progress_percent' => 11])
        ->assertJsonPath('current_step', 'Downloading audio for the moment scan: 50.0% of 1.47GiB at 5MiB/s, ETA 02:30');
});
