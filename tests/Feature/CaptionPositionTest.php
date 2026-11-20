<?php

use App\Models\LongVideo;
use App\Models\VideoClip;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\File;

uses(RefreshDatabase::class);

// Never touch real storage: words JSON and preview frames go to a temp storage path
beforeEach(function () {
    $this->tmpStorage = sys_get_temp_dir() . DIRECTORY_SEPARATOR . 'rc_storage_' . uniqid();
    File::ensureDirectoryExists($this->tmpStorage . '/app/public');
    File::ensureDirectoryExists($this->tmpStorage . '/logs');
    $this->app->useStoragePath($this->tmpStorage);
});

afterEach(function () {
    File::deleteDirectory($this->tmpStorage);
});

function captionClip(array $settings = [], array $crop = [], bool $withWords = true): VideoClip
{
    $video = LongVideo::create([
        'filename' => 'talk.mp4',
        'storage_path' => 'C:\\talk.mp4',
        'status' => 'completed',
        'processing_settings' => $settings,
    ]);
    $clip = VideoClip::create([
        'long_video_id' => $video->id,
        'start_time' => '00:00:00',
        'end_time' => '00:00:30',
        'hook_explanation' => json_encode(['title' => 'Talk']),
        'crop_coordinates_json' => json_encode(array_merge(['crop_filter' => null], $crop)),
        'status' => 'ready',
    ]);
    if ($withWords) {
        file_put_contents(storage_path("app/clip_{$clip->id}_words.json"), json_encode([['word' => 'hey', 'start' => 0, 'end' => 0.4]]));
    }
    return $clip;
}

function clipCaption(VideoClip $clip): ?array
{
    return json_decode($clip->fresh()->crop_coordinates_json, true)['caption'] ?? null;
}

test('moving captions to a dragged spot saves it on the clip and queues a re-render', function () {
    $clip = captionClip([], ['gaming_layout' => ['cam_box' => null]]);

    $this->postJson("/clips/{$clip->id}/caption", ['caption_x' => 0.3, 'caption_y' => 0.42])
        ->assertOk()->assertJson(['success' => true]);

    $crop = json_decode($clip->fresh()->crop_coordinates_json, true);
    expect($clip->fresh()->status)->toBe('rendering')
        ->and($crop['caption'])->toBe(['x' => 0.3, 'y' => 0.42])
        ->and($crop)->toHaveKey('gaming_layout'); // other crop data is kept
});

test('a preset replaces a dragged spot, and a dragged spot replaces a preset', function () {
    $clip = captionClip([], ['caption' => ['style' => 'neon_cyan', 'x' => 0.2, 'y' => 0.3]]);

    $this->postJson("/clips/{$clip->id}/caption", ['caption_position' => 'top'])->assertOk();
    expect(clipCaption($clip))->toBe(['style' => 'neon_cyan', 'position' => 'top']);

    $this->postJson("/clips/{$clip->id}/caption", ['caption_x' => 0.5, 'caption_y' => 0.6])->assertOk();
    expect(clipCaption($clip))->toBe(['style' => 'neon_cyan', 'x' => 0.5, 'y' => 0.6]);
});

test('dragged spots are kept off the very edge of the frame', function () {
    $clip = captionClip();

    $this->postJson("/clips/{$clip->id}/caption", ['caption_x' => 0, 'caption_y' => 1])->assertOk();

    expect(clipCaption($clip))->toBe(['x' => 0.05, 'y' => 0.95]);
});

test('moving captions validates the spot and needs a transcript', function () {
    $clip = captionClip();
    $this->postJson("/clips/{$clip->id}/caption", ['caption_x' => 1.5, 'caption_y' => 0.5])->assertStatus(422);
    $this->postJson("/clips/{$clip->id}/caption", ['caption_x' => 0.5])->assertStatus(422);
    $this->postJson("/clips/{$clip->id}/caption", [])->assertStatus(422);
    $this->postJson("/clips/{$clip->id}/caption", ['caption_position' => 'left'])->assertStatus(422);

    $noWords = captionClip([], [], false);
    $this->postJson("/clips/{$noWords->id}/caption", ['caption_position' => 'top'])
        ->assertStatus(422)->assertJson(['error' => 'This clip has no captions to move.']);
});

test('the subtitle editor keeps style, and position only when it is sent', function () {
    $clip = captionClip();
    $words = [['word' => 'hello', 'start' => 0, 'end' => 0.5]];

    $this->postJson("/clips/{$clip->id}/re-render", ['words' => $words, 'caption_style' => 'fire_gold'])->assertOk();
    expect(clipCaption($clip))->toBe(['style' => 'fire_gold']);

    $this->postJson("/clips/{$clip->id}/re-render", ['words' => $words, 'caption_style' => 'fire_gold', 'caption_x' => 0.5, 'caption_y' => 0.25])->assertOk();
    expect(clipCaption($clip))->toBe(['style' => 'fire_gold', 'x' => 0.5, 'y' => 0.25]);
});

test('caption editor info prefers the clip spot, then the job spot, then the preset', function () {
    $job = ['caption_style' => 'cyber_pink', 'caption_layout' => 'single_word', 'caption_x' => 0.4, 'caption_y' => 0.3];

    $this->getJson('/clips/' . captionClip($job, ['caption' => ['x' => 0.7, 'y' => 0.2, 'style' => 'neon_cyan']])->id . '/caption')
        ->assertOk()->assertJson(['x' => 0.7, 'y' => 0.2, 'position' => null, 'style' => 'neon_cyan', 'layout' => 'single_word', 'frame_url' => null]);

    $this->getJson('/clips/' . captionClip($job)->id . '/caption')
        ->assertOk()->assertJson(['x' => 0.4, 'y' => 0.3, 'position' => null, 'style' => 'cyber_pink']);

    $this->getJson('/clips/' . captionClip(['caption_position' => 'top'])->id . '/caption')
        ->assertOk()->assertJson(['x' => null, 'y' => null, 'position' => 'top', 'style' => 'yellow_pop']);

    // Gaming layout ignores the job's spot and keeps bottom captions
    $this->getJson('/clips/' . captionClip($job, ['gaming_layout' => ['cam_box' => null]])->id . '/caption')
        ->assertOk()->assertJson(['x' => null, 'position' => 'bottom']);
});

test('caption editor returns the preview frame when one exists', function () {
    $clip = captionClip();
    file_put_contents(storage_path("app/public/clip_{$clip->id}_preview.jpg"), 'jpg');

    $url = $this->getJson("/clips/{$clip->id}/caption")->assertOk()->json('frame_url');

    expect($url)->toContain("storage/clip_{$clip->id}_preview.jpg?v=");
});

test('the dashboard has the draggable caption simulator', function () {
    $this->get('/')->assertOk()
        ->assertSee('id="caption_x"', false)
        ->assertSee('Drag the caption to place it on every new clip.');
});
