<?php

use App\Support\DatabaseOffline;
use Illuminate\Database\QueryException;
use Illuminate\Support\Facades\DB;

// No RefreshDatabase here: these tests point the app at a database that can't be reached.

function useUnreachableMysql(): void
{
    config([
        'database.default' => 'mysql',
        'database.connections.mysql.host' => '127.0.0.1',
        'database.connections.mysql.port' => 1, // nothing listens here: connection refused
        'session.driver' => 'array',
    ]);
    DB::purge('mysql');
}

test('dashboard explains MySQL being down instead of a bare 500', function () {
    useUnreachableMysql();

    $this->get('/')
        ->assertStatus(503)
        ->assertSee('[ DATABASE OFFLINE ]')
        ->assertSee("MySQL isn't running or isn't reachable.")
        ->assertSee('XAMPP Control Panel')
        ->assertSee('DB_CONNECTION=sqlite');
});

test('polling endpoints get a JSON 503', function () {
    useUnreachableMysql();

    $this->getJson('/videos/1/logs')
        ->assertStatus(503)
        ->assertJson(['error' => 'database_offline']);
});

test('detector classifies the common database failures', function () {
    $q = fn (string $msg) => new QueryException('mysql', 'select 1', [], new PDOException($msg));

    expect(DatabaseOffline::detect($q('SQLSTATE[HY000] [1045] Access denied for user'))['kind'])->toBe('bad_login')
        ->and(DatabaseOffline::detect($q("SQLSTATE[HY000] [1049] Unknown database 'roninclips'"))['kind'])->toBe('no_database')
        ->and(DatabaseOffline::detect($q('SQLSTATE[HY000]: General error: 1 no such table: long_videos'))['kind'])->toBe('not_migrated')
        ->and(DatabaseOffline::detect($q('SQLSTATE[HY000] [2002] No connection could be made'))['kind'])->toBe('not_running')
        ->and(DatabaseOffline::detect($q('SQLSTATE[23000]: Integrity constraint violation')))->toBeNull()
        ->and(DatabaseOffline::detect(new RuntimeException('unrelated')))->toBeNull();
});
