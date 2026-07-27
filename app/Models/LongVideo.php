<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class LongVideo extends Model
{
    protected $fillable = ['filename', 'storage_path', 'status', 'transcript', 'processing_settings'];

    protected $casts = [
        'processing_settings' => 'array',
    ];

    public function clips()
    {
        return $this->hasMany(VideoClip::class);
    }
}
