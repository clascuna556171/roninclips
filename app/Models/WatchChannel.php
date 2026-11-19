<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class WatchChannel extends Model
{
    protected $fillable = ['login', 'enabled', 'last_checked_at', 'last_error'];

    protected $casts = [
        'enabled' => 'boolean',
        'last_checked_at' => 'datetime',
    ];

    public function vods()
    {
        return $this->hasMany(WatchVod::class);
    }

    public function url(): string
    {
        return 'https://www.twitch.tv/' . $this->login;
    }
}
