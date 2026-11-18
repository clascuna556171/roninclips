<?php

use Illuminate\Support\Facades\Route;
use App\Http\Controllers\VideoController;
use App\Http\Controllers\ApiKeyController;

Route::get('/', [VideoController::class, 'index'])->name('dashboard');
Route::post('/videos', [VideoController::class, 'store'])->name('videos.store');
Route::post('/videos/{video}/retry', [VideoController::class, 'retry'])->name('videos.retry');
Route::get('/videos/{id}/logs', [VideoController::class, 'getLogs'])->name('videos.logs');
Route::delete('/videos/{video}', [VideoController::class, 'destroy'])->name('videos.destroy');
Route::delete('/clips/{clip}', [VideoController::class, 'destroyClip'])->name('clips.destroy');
Route::post('/clips/{clip}/explorer', [VideoController::class, 'openExplorer'])->name('clips.explorer');
Route::post('/browse-file', [VideoController::class, 'browseFile'])->name('videos.browse');
Route::get('/clips/{clip}/transcript', [VideoController::class, 'getTranscript'])->name('clips.transcript.get');
Route::get('/clips/{clip}/status', [VideoController::class, 'getClipStatus'])->name('clips.status');
Route::post('/clips/{clip}/re-render', [VideoController::class, 'reRenderClip'])->name('clips.transcript.update');
Route::post('/clips/{clip}/facecam', [VideoController::class, 'adjustFacecam'])->name('clips.facecam.update');
Route::post('/settings/api-keys', [ApiKeyController::class, 'update'])->name('settings.api-keys');
