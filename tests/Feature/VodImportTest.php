<?php

use App\Http\Controllers\VideoController;
use App\Models\LongVideo;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\File;

uses(RefreshDatabase::class);

// The in-memory DB reuses ids 1, 2, … so never touch the real storage/app/vods/{id} or engine logs.
beforeEach(function () {
    $this->tmpStorage = sys_get_temp_dir() . DIRECTORY_SEPARATOR . 'rc_storage_' . uniqid();
    File::ensureDirectoryExists($this->tmpStorage . '/logs');
    $this->app->useStoragePath($this->tmpStorage);
});

afterEach(function () {
    File::deleteDirectory($this->tmpStorage);
});

function importVideo(array $settings = [], string $status = 'pending'): LongVideo
{
    return LongVideo::create([
        'filename' => 'Twitch VOD 2612345678',
        'storage_path' => '',
        'status' => $status,
        'processing_settings' => array_merge([
            'source_url' => 'https://www.twitch.tv/videos/2612345678',
            'source_platform' => 'twitch',
            'source_vod_id' => '2612345678',
        ], $settings),
    ]);
}

function writeEngineLog(LongVideo $video, string $text): string
{
    $path = storage_path('logs/engine_' . $video->id . '.log');
    File::ensureDirectoryExists(dirname($path));
    file_put_contents($path, $text);
    return $path;
}

test('vod url parser recognises twitch and kick links and rejects others', function () {
    expect(VideoController::parseVodUrl('https://www.twitch.tv/videos/2612345678'))
        ->toBe(['platform' => 'twitch', 'vod_id' => '2612345678']);
    expect(VideoController::parseVodUrl('  https://m.twitch.tv/videos/42?t=1h2m  '))
        ->toBe(['platform' => 'twitch', 'vod_id' => '42']);
    expect(VideoController::parseVodUrl('https://kick.com/somechannel/videos/1A2B3C4D-0000-1111-2222-333344445555'))
        ->toBe(['platform' => 'kick', 'vod_id' => '1a2b3c4d-0000-1111-2222-333344445555']);
    expect(VideoController::parseVodUrl('https://kick.com/video/1a2b3c4d-0000-1111-2222-333344445555'))
        ->toBeNull(); // yt-dlp only supports kick.com/<channel>/videos/<uuid>
    expect(VideoController::parseVodUrl('https://www.twitch.tv/somechannel'))->toBeNull();
    expect(VideoController::parseVodUrl('https://www.youtube.com/watch?v=abc'))->toBeNull();
    expect(VideoController::parseVodUrl('C:\\videos\\stream.mp4'))->toBeNull();
});

test('storing a twitch vod link queues an import with source settings', function () {
    $this->post('/videos', [
        'video_path' => 'https://www.twitch.tv/videos/2612345678',
        'gaming_layout' => '1',
    ])->assertRedirect()->assertSessionHas('success', fn ($msg) => str_contains($msg, 'video + chat'));

    $video = LongVideo::sole();
    expect($video->status)->toBe('pending')
        ->and($video->filename)->toBe('Twitch VOD 2612345678')
        ->and($video->storage_path)->toBe('')
        ->and($video->processing_settings['source_url'])->toBe('https://www.twitch.tv/videos/2612345678')
        ->and($video->processing_settings['source_platform'])->toBe('twitch')
        ->and($video->processing_settings['source_vod_id'])->toBe('2612345678')
        ->and($video->processing_settings['gaming_layout'])->toBeTrue();
});

test('storing a kick vod link says chat is not imported', function () {
    $this->post('/videos', [
        'video_path' => 'https://kick.com/somechannel/videos/1a2b3c4d-0000-1111-2222-333344445555',
    ])->assertSessionHas('success', fn ($msg) => str_contains($msg, "Kick chat can't be fetched"));

    expect(LongVideo::sole()->processing_settings['source_platform'])->toBe('kick');
});

test('unsupported links are rejected with a clear message', function () {
    $this->post('/videos', ['video_path' => 'https://www.youtube.com/watch?v=abc'])
        ->assertSessionHas('error', fn ($msg) => str_contains($msg, 'Unsupported link'));

    expect(LongVideo::count())->toBe(0);
});

test('local file imports still work exactly as before', function () {
    $file = tempnam(sys_get_temp_dir(), 'rc') . '.mp4';
    file_put_contents($file, 'x');

    try {
        $this->post('/videos', ['video_path' => $file])
            ->assertSessionHas('success', 'Processing started for ' . basename($file));

        $video = LongVideo::sole();
        expect($video->storage_path)->toBe($file)
            ->and($video->filename)->toBe(basename($file))
            ->and($video->processing_settings)->not->toHaveKey('source_url');
    } finally {
        @unlink($file);
    }
});

test('logs endpoint reports download progress during an import', function () {
    $video = importVideo();
    $log = writeEngineLog($video, "Importing Twitch VOD 2612345678: reading info...\n");

    $this->getJson("/videos/{$video->id}/logs")
        ->assertJson(['progress_percent' => 2, 'current_step' => 'Reading VOD info']);

    file_put_contents($log, "Importing Twitch VOD 2612345678: reading info...\nDownloading VOD: 0.0%\nDownloading VOD: 50.0% of 3.20GiB at 5.00MiB/s, ETA 00:05:00\n");

    try {
        $this->getJson("/videos/{$video->id}/logs")
            ->assertOk()
            ->assertJson([
                'status' => 'pending',
                'step_index' => 0,
                'progress_percent' => 11,
                'current_step' => 'Downloading VOD: 50.0% of 3.20GiB at 5.00MiB/s, ETA 00:05:00',
            ]);

        file_put_contents($log, "Downloading VOD: 100.0% done (3.21 GB)\nDownloading chat log from Twitch...\n");
        $this->getJson("/videos/{$video->id}/logs")
            ->assertJson(['progress_percent' => 20, 'current_step' => 'Downloading Twitch chat log']);
    } finally {
        @unlink($log);
    }
});

test('logs endpoint shows the friendly import error instead of a generic failure', function () {
    $video = importVideo(['import_error' => 'This Twitch VOD is subscriber-only. RoninClips can only import public VODs.'], 'failed');

    $this->getJson("/videos/{$video->id}/logs")
        ->assertJson([
            'status' => 'failed',
            'current_step' => 'Import failed: This Twitch VOD is subscriber-only. RoninClips can only import public VODs.',
        ]);
});

test('dashboard shows import badge, kick video-only note and import error', function () {
    importVideo(['chat_status' => 'saved', 'chat_count' => 12345], 'completed');
    LongVideo::create([
        'filename' => 'Kick VOD ok', 'storage_path' => 'C:\\x.mp4', 'status' => 'completed',
        'processing_settings' => [
            'source_url' => 'https://kick.com/a/videos/1a2b3c4d-0000-1111-2222-333344445555',
            'source_platform' => 'kick',
            'chat_status' => 'unavailable',
        ],
    ]);
    importVideo(['import_error' => "This Twitch VOD wasn't found. It may have been deleted or expired, or the link is wrong."], 'failed');

    $this->get('/')
        ->assertOk()
        ->assertSee('SOURCE VIDEO FILE OR VOD LINK')
        ->assertSee('TWITCH · CHAT 12,345 MSGS')
        ->assertSee('KICK · VIDEO ONLY')
        ->assertSee('TWITCH · NOT IMPORTED')
        ->assertSee('IMPORT FAILED:')
        ->assertSee("This Twitch VOD wasn&#039;t found", false);
});

test('retrying a failed import is allowed even though no file exists yet', function () {
    $video = importVideo(['import_error' => 'Network error'], 'failed');

    $this->post("/videos/{$video->id}/retry")
        ->assertSessionHas('success');

    expect($video->fresh()->status)->toBe('pending');
});

test('retrying a local video with a missing file is still refused', function () {
    $video = LongVideo::create([
        'filename' => 'gone.mp4', 'storage_path' => 'C:\\nope\\gone.mp4', 'status' => 'failed',
    ]);

    $this->post("/videos/{$video->id}/retry")->assertSessionHas('error');
});

test('deleting an imported video removes its downloaded vod folder', function () {
    $video = importVideo([], 'completed');
    $dir = storage_path('app/vods/' . $video->id);
    File::ensureDirectoryExists($dir);
    file_put_contents($dir . '/vod.mp4', 'x');
    file_put_contents($dir . '/chat.jsonl', "{}\n");

    $this->delete("/videos/{$video->id}")->assertSessionHas('success');

    expect(is_dir($dir))->toBeFalse()
        ->and(LongVideo::count())->toBe(0);
});

test('deleting a local video never touches the source file', function () {
    $file = tempnam(sys_get_temp_dir(), 'rc') . '.mp4';
    file_put_contents($file, 'x');
    $video = LongVideo::create(['filename' => 'a.mp4', 'storage_path' => $file, 'status' => 'completed']);

    try {
        $this->delete("/videos/{$video->id}");
        expect(file_exists($file))->toBeTrue();
    } finally {
        @unlink($file);
    }
});
