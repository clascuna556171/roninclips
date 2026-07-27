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
        Schema::create('video_clips', function (Blueprint $table) {
            $table->id();
            $table->foreignId('long_video_id')->constrained('long_videos')->onDelete('cascade');
            $table->string('start_time');
            $table->string('end_time');
            $table->text('hook_explanation');
            $table->json('crop_coordinates_json')->nullable();
            $table->string('output_path')->nullable();
            $table->enum('status', ['pending', 'rendering', 'ready'])->default('pending');
            $table->timestamps();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('video_clips');
    }
};
