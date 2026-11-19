<?php

namespace App\Support;

use App\Models\WatchChannel;

/**
 * The background watchlist process (processor/watchlist.py): is it running, start it, ask it to check now.
 * It writes storage/app/watchlist/heartbeat.json every few seconds while it runs.
 */
class Watcher
{
    public const STALE_AFTER_S = 90;

    public static function dir(): string
    {
        return storage_path('app/watchlist');
    }

    public static function heartbeat(): ?array
    {
        $path = self::dir() . '/heartbeat.json';
        if (!is_file($path)) {
            return null;
        }
        $data = json_decode((string) @file_get_contents($path), true);
        return is_array($data) ? $data : null;
    }

    public static function isRunning(?array $heartbeat = null): bool
    {
        $heartbeat ??= self::heartbeat();
        return $heartbeat !== null && (time() - (int) ($heartbeat['updated_at'] ?? 0)) < self::STALE_AFTER_S;
    }

    /** Ask the running watcher to check every channel now (it looks for this file every ~10 s). */
    public static function requestCheck(): void
    {
        if (!is_dir(self::dir())) {
            mkdir(self::dir(), 0775, true);
        }
        touch(self::dir() . '/check_now');
    }

    /** Start the watcher when channels are followed and it isn't running. The watcher refuses to run twice. */
    public static function ensureRunning(): bool
    {
        if (app()->runningUnitTests() || self::isRunning()) {
            return false;
        }
        if (!WatchChannel::where('enabled', true)->exists()) {
            return false;
        }
        self::start();
        return true;
    }

    public static function start(): void
    {
        if (app()->runningUnitTests()) {
            return;
        }
        if (!is_dir(self::dir())) {
            mkdir(self::dir(), 0775, true);
        }
        $python = self::pythonBinary();
        $script = base_path('processor/watchlist.py');
        $log = storage_path('logs/watchlist.log');

        if (strtoupper(substr(PHP_OS, 0, 3)) === 'WIN') {
            pclose(popen('start /B cmd /c ""' . $python . '" "' . $script . '" >> "' . $log . '" 2>&1"', 'r'));
        } else {
            exec(escapeshellarg($python) . ' ' . escapeshellarg($script) . ' >> ' . escapeshellarg($log) . ' 2>&1 &');
        }
    }

    public static function pythonBinary(): string
    {
        foreach ([base_path('processor/.venv/Scripts/python.exe'), base_path('processor/.venv/bin/python')] as $venv) {
            if (file_exists($venv)) {
                return $venv;
            }
        }
        return 'python';
    }
}
