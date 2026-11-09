<?php

use App\Models\LongVideo;
use App\Models\VideoClip;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

test('the dashboard returns a successful response with studio controls', function () {
    $response = $this->get('/');

    $response->assertStatus(200)
        ->assertSee('RoninClips')
        ->assertSee('BGM Auto-Ducking')
        ->assertSee('Transition Speed')
        ->assertSee('Large-v3 (Studio Grade)');
});

test('storing a video rejects non-existent file paths', function () {
    $response = $this->post('/videos', [
        'video_path' => 'C:\\non_existent_path\\missing_video.mp4',
    ]);

    $response->assertRedirect();
    $response->assertSessionHas('error');
});

test('clip status endpoint returns current status and timestamp', function () {
    $video = LongVideo::create([
        'filename' => 'sample.mp4',
        'storage_path' => 'C:\\sample.mp4',
        'status' => 'completed',
    ]);

    $clip = VideoClip::create([
        'long_video_id' => $video->id,
        'start_time' => '00:00:00',
        'end_time' => '00:00:30',
        'hook_explanation' => json_encode(['title' => 'Hook 1', 'virality_score' => 95]),
        'status' => 'ready',
    ]);

    $this->getJson("/clips/{$clip->id}/status")
        ->assertStatus(200)
        ->assertJsonFragment([
            'id' => $clip->id,
            'status' => 'ready',
        ]);
});

test('deleting a video cleans up associated clips and temporary artifacts', function () {
    $video = LongVideo::create([
        'filename' => 'cleanup_test.mp4',
        'storage_path' => 'C:\\cleanup_test.mp4',
        'status' => 'completed',
    ]);

    $clip = VideoClip::create([
        'long_video_id' => $video->id,
        'start_time' => '00:00:00',
        'end_time' => '00:00:30',
        'hook_explanation' => 'Hook',
        'status' => 'ready',
    ]);

    $wordsFile = storage_path("app/clip_{$clip->id}_words.json");
    file_put_contents($wordsFile, '[]');
    expect(file_exists($wordsFile))->toBeTrue();

    $this->delete("/videos/{$video->id}")->assertRedirect();

    expect(LongVideo::find($video->id))->toBeNull();
    expect(VideoClip::find($clip->id))->toBeNull();
    expect(file_exists($wordsFile))->toBeFalse();
});

test('logs endpoint returns pipeline progress and step index', function () {
    $video = LongVideo::create([
        'filename' => 'progress_test.mp4',
        'storage_path' => 'C:\\progress_test.mp4',
        'status' => 'analyzing',
    ]);

    $this->getJson("/videos/{$video->id}/logs")
        ->assertStatus(200)
        ->assertJsonFragment([
            'status' => 'analyzing',
            'step_index' => 2,
            'progress_percent' => 50,
        ]);
});

test('transcript endpoint returns word timings and re-render validates style presets', function () {
    $video = LongVideo::create([
        'filename' => 'subs_test.mp4',
        'storage_path' => 'C:\\subs_test.mp4',
        'status' => 'completed',
    ]);

    $clip = VideoClip::create([
        'long_video_id' => $video->id,
        'start_time' => '00:00:00',
        'end_time' => '00:00:15',
        'hook_explanation' => 'Hook',
        'status' => 'ready',
    ]);

    $sampleWords = [
        ['word' => 'HELLO', 'start' => 0.0, 'end' => 0.4],
        ['word' => 'WORLD', 'start' => 0.5, 'end' => 0.9],
    ];
    $wordsFile = storage_path("app/clip_{$clip->id}_words.json");
    file_put_contents($wordsFile, json_encode($sampleWords));

    $this->getJson("/clips/{$clip->id}/transcript")
        ->assertStatus(200)
        ->assertJsonPath('words.0.word', 'HELLO');

    // Reject invalid caption_style outside allowlist
    $this->postJson("/clips/{$clip->id}/re-render", [
        'words' => $sampleWords,
        'caption_style' => 'invalid_injected_style',
    ])->assertStatus(422);

    // Clean up via destroyClip
    $this->delete("/clips/{$clip->id}")->assertRedirect();
    expect(file_exists($wordsFile))->toBeFalse();
});

test('retry endpoint rejects missing source file for failed video', function () {
    $video = LongVideo::create([
        'filename' => 'failed_source.mp4',
        'storage_path' => 'C:\\non_existent_path\\failed_source.mp4',
        'status' => 'failed',
    ]);

    $response = $this->post("/videos/{$video->id}/retry");
    $response->assertRedirect();
    $response->assertSessionHas('error');
    expect($video->fresh()->status)->toBe('failed');
});

