<?php

use App\Support\EnvFile;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Http;

uses(RefreshDatabase::class);

// Never touch the real .env: point the app at a throwaway copy.
beforeEach(function () {
    $this->envDir = sys_get_temp_dir() . DIRECTORY_SEPARATOR . 'rc_env_' . uniqid();
    File::ensureDirectoryExists($this->envDir);
    file_put_contents($this->envDir . '/.env', "APP_NAME=Laravel\nGROQ_API_KEY=\n# GROQ_MODEL=llama\n");
    $this->app->useEnvironmentPath($this->envDir);
});

afterEach(function () {
    File::deleteDirectory($this->envDir);
});

function envText(): string
{
    return file_get_contents(EnvFile::path());
}

test('a working Groq key is tested and saved, a missing Gemini line is appended', function () {
    Http::fake([
        'api.groq.com/*' => Http::response(['data' => []]),
        'generativelanguage.googleapis.com/*' => Http::response(['models' => []]),
    ]);

    $this->post('/settings/api-keys', [
        'groq_api_key' => ' gsk_abcdefghijklmnop1234 ',
        'gemini_api_key' => 'AIzaSyTestKey_0987654321',
    ])->assertRedirect()->assertSessionHas('success', 'Groq key saved and working. Gemini key saved and working.');

    expect(envText())
        ->toContain('GROQ_API_KEY="gsk_abcdefghijklmnop1234"')
        ->toContain('GEMINI_API_KEY="AIzaSyTestKey_0987654321"')
        ->toContain('# GROQ_MODEL=llama');
    Http::assertSent(fn ($r) => $r->hasHeader('Authorization', 'Bearer gsk_abcdefghijklmnop1234'));
    Http::assertSent(fn ($r) => $r->hasHeader('x-goog-api-key', 'AIzaSyTestKey_0987654321'));
});

test('a key the provider rejects is not saved', function () {
    Http::fake(['generativelanguage.googleapis.com/*' => Http::response(
        ['error' => ['status' => 'INVALID_ARGUMENT', 'details' => [['reason' => 'API_KEY_INVALID']]]], 400
    )]);

    $this->post('/settings/api-keys', ['gemini_api_key' => 'AIzaWrongKey123456'])
        ->assertSessionHas('error', 'Gemini rejected that key. Check you copied the whole key.');

    expect(envText())->not->toContain('GEMINI_API_KEY');
});

test('a key is still saved when the provider cannot be reached', function () {
    Http::fake(['api.groq.com/*' => Http::response('rate limited', 429)]);

    $this->post('/settings/api-keys', ['groq_api_key' => 'gsk_offline_key_12345'])
        ->assertSessionHas('success', "Groq key saved (couldn't reach Groq to test it).");

    expect(envText())->toContain('GROQ_API_KEY="gsk_offline_key_12345"');
});

test('unsafe or empty input never reaches the env file', function () {
    Http::fake();
    $before = envText();

    $this->post('/settings/api-keys', ['groq_api_key' => "gsk_abc\nAPP_DEBUG=true"])
        ->assertSessionHas('error');
    $this->post('/settings/api-keys', ['groq_api_key' => 'gsk_has"quote12345'])
        ->assertSessionHas('error');
    $this->post('/settings/api-keys', [])
        ->assertSessionHas('error', 'Paste a Groq or Gemini key first.');

    expect(envText())->toBe($before);
    Http::assertNothingSent();
});

test('remove clears only that key', function () {
    file_put_contents(EnvFile::path(), "GROQ_API_KEY=\"gsk_keep_this_one_99\"\nGEMINI_API_KEY=\"AIzaRemoveMe12345\"\n");

    $this->post('/settings/api-keys', ['clear' => 'gemini'])
        ->assertSessionHas('success', 'Gemini key removed.');

    expect(EnvFile::get('GEMINI_API_KEY'))->toBeNull()
        ->and(EnvFile::get('GROQ_API_KEY'))->toBe('gsk_keep_this_one_99');
});

test('dashboard shows masked keys and provider links, never the full key', function () {
    file_put_contents(EnvFile::path(), "GROQ_API_KEY=\"gsk_secretmiddlepart_wxyz\"\n");

    $this->get('/')
        ->assertOk()
        ->assertSee('gsk_••••wxyz')
        ->assertDontSee('secretmiddlepart')
        ->assertSee('https://console.groq.com/keys')
        ->assertSee('https://aistudio.google.com/apikey')
        ->assertSee('Not set');
});

test('dashboard opens the keys panel and warns when no key is set', function () {
    $this->get('/')
        ->assertOk()
        ->assertSee('NO AI KEY')
        ->assertSee('needs a free key', false);
});

test('logs label the analyzing step with Gemini when the backup took over', function () {
    $tmp = sys_get_temp_dir() . DIRECTORY_SEPARATOR . 'rc_storage_' . uniqid();
    File::ensureDirectoryExists($tmp . '/logs');
    $this->app->useStoragePath($tmp);

    $video = \App\Models\LongVideo::create([
        'filename' => 'talk.mp4', 'storage_path' => 'C:/talk.mp4', 'status' => 'analyzing',
        'processing_settings' => ['stream_moments' => false],
    ]);
    file_put_contents(storage_path('logs/engine_' . $video->id . '.log'), "  Trying model: llama...\n  Trying Gemini model: gemini-2.5-flash...\n");

    $this->getJson("/videos/{$video->id}/logs")
        ->assertJson(['current_step' => 'Analyzing transcript with Gemini AI (backup) for viral hooks']);

    File::deleteDirectory($tmp);
});
