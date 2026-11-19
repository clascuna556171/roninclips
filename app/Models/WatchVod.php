<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class WatchVod extends Model
{
    protected $fillable = ['watch_channel_id', 'vod_id', 'title', 'duration_s', 'status', 'long_video_id', 'error'];

    public function channel()
    {
        return $this->belongsTo(WatchChannel::class, 'watch_channel_id');
    }

    public function longVideo()
    {
        return $this->belongsTo(LongVideo::class);
    }

    public function url(): string
    {
        return 'https://www.twitch.tv/videos/' . $this->vod_id;
    }

    public function durationLabel(): string
    {
        if (!$this->duration_s) {
            return '';
        }
        $h = intdiv($this->duration_s, 3600);
        $m = intdiv($this->duration_s % 3600, 60);
        return $h ? "{$h}h " . str_pad((string) $m, 2, '0', STR_PAD_LEFT) . 'm' : "{$m}m";
    }
}
