<?php

namespace App\Support;

use Illuminate\Database\QueryException;
use Illuminate\Database\SQLiteDatabaseDoesNotExistException;
use PDOException;
use Throwable;

/**
 * Recognises "the database can't be used" errors (MySQL down, bad login, missing SQLite file,
 * tables not migrated) so the app can explain the fix instead of showing a bare 500.
 */
class DatabaseOffline
{
    /** @return array{driver: string, problem: string, kind: string, detail: string}|null */
    public static function detect(Throwable $e): ?array
    {
        for ($cur = $e; $cur; $cur = $cur->getPrevious()) {
            if ($cur instanceof SQLiteDatabaseDoesNotExistException) {
                return self::info('sqlite', 'missing_file', 'The SQLite database file does not exist yet.', $e);
            }
            if (!$cur instanceof QueryException && !$cur instanceof PDOException) {
                continue;
            }
            $msg = $cur->getMessage();
            if (preg_match('/\[(2002|2003|2006)\]/', $msg)) {
                return self::info('mysql', 'not_running', "MySQL isn't running or isn't reachable.", $e);
            }
            if (preg_match('/\[(1044|1045)\]/', $msg)) {
                return self::info('mysql', 'bad_login', 'MySQL refused the username or password in .env.', $e);
            }
            if (preg_match('/\[1049\]/', $msg)) {
                return self::info('mysql', 'no_database', "The MySQL database named in .env doesn't exist.", $e);
            }
            if (preg_match('/no such table|\[1146\]|Base table or view not found/i', $msg)) {
                return self::info(config('database.default', 'sqlite'), 'not_migrated', "The database tables haven't been created yet.", $e);
            }
        }

        return null;
    }

    private static function info(string $driver, string $kind, string $problem, Throwable $e): array
    {
        return ['driver' => $driver, 'kind' => $kind, 'problem' => $problem, 'detail' => $e->getMessage()];
    }
}
