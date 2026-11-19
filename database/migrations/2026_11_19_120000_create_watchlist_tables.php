<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Twitch watchlist: followed channels, and every VOD the watcher has seen for them.
     * Statuses are plain strings (not enums) so SQLite and MySQL behave the same.
     */
    public function up(): void
    {
        Schema::create('watch_channels', function (Blueprint $table) {
            $table->id();
            $table->string('login', 40)->unique();          // twitch.tv/<login>, lower case
            $table->boolean('enabled')->default(true);
            $table->timestamp('last_checked_at')->nullable();
            $table->text('last_error')->nullable();
            $table->timestamps();
        });

        Schema::create('watch_vods', function (Blueprint $table) {
            $table->id();
            $table->foreignId('watch_channel_id')->constrained('watch_channels')->cascadeOnDelete();
            $table->string('vod_id', 32)->unique();
            $table->string('title')->nullable();
            $table->unsignedInteger('duration_s')->nullable();
            $table->string('status', 16)->default('queued');  // queued, processing, done, failed, skipped
            $table->foreignId('long_video_id')->nullable()->constrained('long_videos')->nullOnDelete();
            $table->text('error')->nullable();
            $table->timestamps();
            $table->index(['status']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('watch_vods');
        Schema::dropIfExists('watch_channels');
    }
};
