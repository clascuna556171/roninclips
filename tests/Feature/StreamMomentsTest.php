<?php

use App\Models\LongVideo;
use App\Models\VideoClip;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\File;

uses(RefreshDatabase::class);

// Same isolation as VodImportTest: never touch real storage/logs/engine_{id}.log
beforeEach(function () {
    $this->tmpStorage = sys_get_temp_dir() . DIRECTORY_SEPARATOR . 'rc_storage_' . uniqid();
    File::ensureDirectoryExists($this->tmpStorage . '/logs');
    $this->app->useStoragePath($this->tmpStorage);
});

afterEach(function () {
    File::deleteDirectory($this->tmpStorage);
});

function momentsVideo(string $status, array $settings = []): LongVideo
{
    return LongVideo::create([
        'filename' => 'Twitch VOD 2612345678',
        'storage_path' => 'C:\\vods\\a.mp4',
        'status' => $status,
        'processing_settings' => array_merge(['stream_moments' => true], $settings),
    ]);
}

test('stream moments mode is stored from the processing pipeline choice', function () {
    $this->post('/videos', [
        'video_path' => 'https://www.twitch.tv/videos/2612345678',
        'processing_mode' => 'stream_moments',
    ])->assertRedirect();

    $settings = LongVideo::sole()->processing_settings;
    expect($settings['stream_moments'])->toBeTrue()
        ->and($settings['full_video_mode'])->toBeFalse();
});

test('other modes leave stream moments off', function () {
    $this->post('/videos', ['video_path' => 'https://www.twitch.tv/videos/1', 'processing_mode' => 'viral_hooks']);
    $this->post('/videos', ['video_path' => 'https://www.twitch.tv/videos/2', 'processing_mode' => 'full_video']);

    foreach (LongVideo::all() as $video) {
        expect($video->processing_settings['stream_moments'])->toBeFalse();
    }
});

test('logs endpoint shows moment detection and window transcription steps', function () {
    $video = momentsVideo('transcribing');
    $log = storage_path('logs/engine_' . $video->id . '.log');

    file_put_contents($log, "Audio extracted: 900 KB\n\nScanning for stream moments (chat + audio)...\n");
    $this->getJson("/videos/{$video->id}/logs")
        ->assertJson(['step_index' => 1, 'progress_percent' => 30, 'current_step' => 'Detecting chat floods and audio spikes']);

    file_put_contents($log, "Scanning for stream moments (chat + audio)...\n  📝 Transcribing moment window 1/6 (00:01:00-00:01:40)...\n  📝 Transcribing moment window 2/6 (00:05:00-00:05:40)...\n");
    $this->getJson("/videos/{$video->id}/logs")
        ->assertJson(['progress_percent' => 35, 'current_step' => 'Transcribing moment window 2/6']);
});

test('logs endpoint labels the analyzing step per mode', function () {
    $moments = momentsVideo('analyzing');
    $hooks = momentsVideo('analyzing', ['stream_moments' => false]);

    $this->getJson("/videos/{$moments->id}/logs")->assertJson(['current_step' => 'Ranking stream moments with Groq AI']);
    $this->getJson("/videos/{$hooks->id}/logs")->assertJson(['current_step' => 'Analyzing transcript with Groq AI for viral hooks']);
});

test('dashboard offers the mode and shows why a moment was picked', function () {
    $video = momentsVideo('completed');
    VideoClip::create([
        'long_video_id' => $video->id,
        'start_time' => '00:01:00.000',
        'end_time' => '00:01:40.000',
        'status' => 'ready',
        'hook_explanation' => json_encode([
            'title' => 'Insane clutch',
            'reason' => 'Last-second escape from five cop cars',
            'source' => 'stream_moments',
            'signal_summary' => 'Chat spiked 8x (142 msgs in 10s) + audio peak (+9 dB)',
        ]),
    ]);
    VideoClip::create([
        'long_video_id' => $video->id,
        'start_time' => '00:05:00.000',
        'end_time' => '00:05:40.000',
        'status' => 'ready',
        'hook_explanation' => json_encode([
            'title' => 'Stream moment at 00:05:25',
            'reason' => 'Audio peak (+11 dB)',
            'source' => 'stream_moments',
            'signal_summary' => 'Audio peak (+11 dB)',
        ]),
    ]);

    $html = $this->get('/')->assertOk()
        ->assertSee('Stream Moments')
        ->assertSee('value="stream_moments"', false)
        ->assertSee('Chat spiked 8x (142 msgs in 10s) + audio peak (+9 dB)')
        ->getContent();

    // When the reason already is the signal summary, it isn't repeated
    expect(substr_count($html, 'Audio peak (+11 dB)'))->toBeGreaterThan(0);
    expect(substr_count($html, 'class="clip-signal"'))->toBe(1);
});
