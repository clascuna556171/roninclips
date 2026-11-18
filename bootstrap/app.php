<?php

use Illuminate\Foundation\Application;
use Illuminate\Foundation\Configuration\Exceptions;
use Illuminate\Foundation\Configuration\Middleware;
use Illuminate\Http\Request;

return Application::configure(basePath: dirname(__DIR__))
    ->withRouting(
        web: __DIR__.'/../routes/web.php',
        commands: __DIR__.'/../routes/console.php',
        health: '/up',
    )
    ->withMiddleware(function (Middleware $middleware): void {
        //
    })
    ->withExceptions(function (Exceptions $exceptions): void {
        $exceptions->shouldRenderJsonWhen(
            fn (Request $request) => $request->is('api/*') || $request->expectsJson(),
        );

        // Database down or not set up: explain the fix (start MySQL or use SQLite) instead of a bare 500.
        $exceptions->render(function (\Throwable $e, Request $request) {
            $info = \App\Support\DatabaseOffline::detect($e);
            if ($info === null) {
                return null;
            }
            if ($request->expectsJson()) {
                return response()->json(['error' => 'database_offline', 'message' => $info['problem']], 503);
            }

            return response()->view('errors.database-offline', $info, 503);
        });
    })->create();
