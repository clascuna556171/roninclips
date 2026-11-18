<?php

namespace App\Http\Controllers;

use App\Support\EnvFile;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Http;
use Throwable;

class ApiKeyController extends Controller
{
    /** form field => [env var, display name, verify URL] */
    public const PROVIDERS = [
        'groq' => ['GROQ_API_KEY', 'Groq', 'https://api.groq.com/openai/v1/models'],
        'gemini' => ['GEMINI_API_KEY', 'Gemini', 'https://generativelanguage.googleapis.com/v1beta/models'],
    ];

    public function update(Request $request)
    {
        $request->validate([
            'groq_api_key' => ['nullable', 'string', 'max:200'],
            'gemini_api_key' => ['nullable', 'string', 'max:200'],
            'clear' => ['nullable', 'in:groq,gemini'],
        ]);

        try {
            if ($provider = $request->input('clear')) {
                [$envVar, $name] = self::PROVIDERS[$provider];
                EnvFile::set([$envVar => '']);
                return back()->with('success', "{$name} key removed.");
            }

            $toSave = [];
            $notes = [];
            foreach (self::PROVIDERS as $provider => [$envVar, $name, $url]) {
                $key = trim((string) $request->input("{$provider}_api_key", ''));
                if ($key === '') {
                    continue;
                }
                if (!preg_match('/^[A-Za-z0-9_\-]{10,200}$/', $key)) {
                    return back()->with('error', "That {$name} key doesn't look right. Copy it again without spaces or quotes.");
                }
                $check = $this->verify($provider, $key, $url);
                if ($check === 'invalid') {
                    return back()->with('error', "{$name} rejected that key. Check you copied the whole key.");
                }
                $toSave[$envVar] = $key;
                $notes[] = $check === 'ok' ? "{$name} key saved and working." : "{$name} key saved (couldn't reach {$name} to test it).";
            }

            if (!$toSave) {
                return back()->with('error', 'Paste a Groq or Gemini key first.');
            }
            EnvFile::set($toSave);
        } catch (Throwable $e) {
            return back()->with('error', 'Could not save the key: ' . $e->getMessage());
        }

        return back()->with('success', implode(' ', $notes));
    }

    /** 'ok', 'invalid' (provider refused the key) or 'unknown' (offline, rate-limited, provider down). */
    private function verify(string $provider, string $key, string $url): string
    {
        try {
            $req = Http::timeout(10)->acceptJson();
            $response = $provider === 'groq'
                ? $req->withToken($key)->get($url)
                : $req->withHeaders(['x-goog-api-key' => $key])->get($url);
        } catch (Throwable) {
            return 'unknown';
        }

        if ($response->successful()) {
            return 'ok';
        }
        // Gemini answers a bad key with 400 API_KEY_INVALID; Groq with 401.
        if (in_array($response->status(), [401, 403], true)
            || ($response->status() === 400 && str_contains($response->body(), 'API_KEY_INVALID'))) {
            return 'invalid';
        }

        return 'unknown';
    }
}
