<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        Schema::create('long_videos', function (Blueprint $table) {
            $table->id();
            $table->string('filename');
            $table->string('storage_path');
            $table->enum('status', ['pending', 'transcribing', 'analyzing', 'processing', 'completed', 'failed'])->default('pending');
            $table->longText('transcript')->nullable();
            $table->timestamps();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('long_videos');
    }
};
