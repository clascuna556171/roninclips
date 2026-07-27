<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class VideoClip extends Model
{
    protected $fillable = ['long_video_id', 'start_time', 'end_time', 'hook_explanation', 'crop_coordinates_json', 'output_path', 'status'];

    public function longVideo()
    {
        return $this->belongsTo(LongVideo::class);
    }
}
