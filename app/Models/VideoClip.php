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

    /**
     * Parse rich AI metadata from hook_explanation (with transparent fallback for plain text).
     */
    public function getMetadataAttribute(): array
    {
        $raw = $this->hook_explanation ?? '';
        if (str_starts_with(trim($raw), '{')) {
            $decoded = json_decode($raw, true);
            if (is_array($decoded)) {
                return array_merge([
                    'title' => 'Clip #' . $this->id,
                    'virality_score' => 88,
                    'hook_strength' => 90,
                    'pacing_energy' => 85,
                    'shareability' => 89,
                    'reason' => $raw,
                    'social_caption' => 'Check out this viral moment! 🔥',
                    'hashtags' => '#viral #shorts #trending #clips',
                    'shorts_description' => 'Viral clip extracted with RoninClips AI.'
                ], $decoded);
            }
        }

        // Backward compatibility fallback for legacy plain string explanations
        return [
            'title' => 'Viral Hook Clip',
            'virality_score' => 88,
            'hook_strength' => 90,
            'pacing_energy' => 85,
            'shareability' => 89,
            'reason' => $raw ?: 'Engaging video hook moment',
            'social_caption' => $raw ?: 'Check out this viral moment! 🔥',
            'hashtags' => '#viral #shorts #trending #clips',
            'shorts_description' => $raw ?: 'Viral clip extracted with RoninClips AI.'
        ];
    }

    public function getTitleAttribute(): string
    {
        return $this->metadata['title'] ?? ('Clip #' . $this->id);
    }

    public function getViralityScoreAttribute(): int
    {
        return (int) ($this->metadata['virality_score'] ?? 88);
    }

    public function getHookStrengthAttribute(): int
    {
        return (int) ($this->metadata['hook_strength'] ?? 90);
    }

    public function getPacingEnergyAttribute(): int
    {
        return (int) ($this->metadata['pacing_energy'] ?? 85);
    }

    public function getShareabilityAttribute(): int
    {
        return (int) ($this->metadata['shareability'] ?? 88);
    }

    public function getReasonAttribute(): string
    {
        return $this->metadata['reason'] ?? ($this->hook_explanation ?? '');
    }

    public function getSocialCaptionAttribute(): string
    {
        return $this->metadata['social_caption'] ?? '';
    }

    public function getHashtagsAttribute(): string
    {
        return $this->metadata['hashtags'] ?? '#viral #shorts';
    }

    public function getShortsDescriptionAttribute(): string
    {
        return $this->metadata['shorts_description'] ?? '';
    }

    public function getFullPostTextAttribute(): string
    {
        $title = $this->title;
        $caption = $this->social_caption;
        $hashtags = $this->hashtags;

        $parts = [];
        if ($title) $parts[] = "🚀 " . $title;
        if ($caption) $parts[] = $caption;
        if ($hashtags) $parts[] = $hashtags;

        return implode("\n\n", $parts);
    }
}
