<?php

namespace App\Support;

use Dotenv\Dotenv;
use RuntimeException;

/**
 * Reads and updates single keys in the app's .env file.
 *
 * The dashboard reads the file directly instead of env()/config(): a long-running PHP worker
 * keeps the values it booted with, so a key saved a moment ago would otherwise look unset.
 */
class EnvFile
{
    public const VALUE_PATTERN = '/^[A-Za-z0-9_\-.]*$/';

    public static function path(): string
    {
        return app()->environmentFilePath();
    }

    public static function get(string $key): ?string
    {
        $path = self::path();
        if (!is_file($path)) {
            return null;
        }
        $value = Dotenv::parse((string) file_get_contents($path))[$key] ?? null;

        return ($value === null || trim($value) === '') ? null : trim($value);
    }

    /** @param array<string, string> $values key => value ('' clears the key) */
    public static function set(array $values): void
    {
        $path = self::path();
        if (!is_file($path)) {
            throw new RuntimeException('.env file not found. Copy .env.example to .env first.');
        }
        $contents = (string) file_get_contents($path);

        foreach ($values as $key => $value) {
            if (!preg_match('/^[A-Z][A-Z0-9_]*$/', $key) || !preg_match(self::VALUE_PATTERN, $value)) {
                throw new RuntimeException("Refusing to write an unsafe value for {$key}.");
            }
            $line = $key . '=' . ($value === '' ? '' : '"' . $value . '"');
            $pattern = '/^' . preg_quote($key, '/') . '=.*$/m';
            if (preg_match($pattern, $contents)) {
                $contents = preg_replace($pattern, $line, $contents, 1);
            } else {
                $contents = rtrim($contents, "\r\n") . PHP_EOL . $line . PHP_EOL;
            }
        }

        if (file_put_contents($path, $contents, LOCK_EX) === false) {
            throw new RuntimeException('Could not write the .env file.');
        }
    }

    /** "gsk_…abcd" style label that never reveals the full key. */
    public static function mask(?string $value): ?string
    {
        if ($value === null) {
            return null;
        }
        $prefix = str_contains(substr($value, 0, 5), '_') ? substr($value, 0, strpos($value, '_') + 1) : substr($value, 0, 4);

        return strlen($value) <= 8 ? str_repeat('•', 6) : $prefix . '••••' . substr($value, -4);
    }
}
