<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use App\Models\LongVideo;
use App\Support\EnvFile;
use Symfony\Component\Process\Process;

class VideoController extends Controller
{
    private function getPythonBinary(): string
    {
        $venvWin = base_path('processor/.venv/Scripts/python.exe');
        $venvUnix = base_path('processor/.venv/bin/python');
        if (file_exists($venvWin)) {
            return $venvWin;
        }
        if (file_exists($venvUnix)) {
            return $venvUnix;
        }
        return 'python';
    }

    public function index()
    {
        $videos = LongVideo::with('clips')->latest()->get();
        $dbDriver = config('database.default', 'sqlite');
        $groqModel = config('services.groq.model', 'openai/gpt-oss-120b');
        $apiKeys = [
            'groq' => EnvFile::mask(EnvFile::get('GROQ_API_KEY')),
            'gemini' => EnvFile::mask(EnvFile::get('GEMINI_API_KEY')),
        ];
        $hasNvidia = file_exists('C:\\Windows\\System32\\nvidia-smi.exe') || file_exists('/usr/bin/nvidia-smi');
        $hwBadge = $hasNvidia ? 'CUDA GPU' : 'CPU ENGINE';
        $activeJobsCount = $videos->whereNotIn('status', ['completed', 'failed'])->count();
        $totalClipsCount = $videos->sum(function($v) {
            return $v->clips->where('status', 'ready')->count();
        });

        return view('dashboard', compact(
            'videos', 'dbDriver', 'groqModel', 'apiKeys', 'hwBadge', 'activeJobsCount', 'totalClipsCount'
        ));
    }

    public function browseFile(Request $request)
    {
        if (strtoupper(substr(PHP_OS, 0, 3)) === 'WIN') {
            $isAudio = $request->input('type') === 'audio';
            $filter = $isAudio
                ? 'Audio Files (*.mp3;*.wav;*.m4a;*.aac)|*.mp3;*.wav;*.m4a;*.aac|All Files (*.*)|*.*'
                : 'MP4 Video (*.mp4)|*.mp4|All Video Files (*.mp4;*.mov;*.mkv)|*.mp4;*.mov;*.mkv|All Files (*.*)|*.*';
            $title = $isAudio ? 'Select Background Music for RoninClips' : 'Select Video File for RoninClips';
            $psScript = '[System.Reflection.Assembly]::LoadWithPartialName("System.windows.forms") | Out-Null; ' .
                        '$f = New-Object System.Windows.Forms.OpenFileDialog; ' .
                        '$f.Filter = "' . $filter . '"; ' .
                        '$f.Title = "' . $title . '"; ' .
                        'if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $f.FileName }';
            $cmd = 'powershell.exe -NoProfile -NonInteractive -Command "' . $psScript . '"';
            $selectedPath = trim(shell_exec($cmd) ?? '');
            if (!empty($selectedPath) && file_exists($selectedPath)) {
                return response()->json(['success' => true, 'file_path' => $selectedPath]);
            }
            return response()->json(['success' => false, 'message' => 'No file selected.']);
        }
        return response()->json(['success' => false, 'message' => 'Native file picker is available on Windows host. You can paste the file path directly.']);
    }

    public function store(Request $request)
    {
        $request->validate(['video_path' => 'required|string']);

        $path = trim($request->video_path);
        $source = self::parseVodUrl($path);

        if (!$source && preg_match('~^https?://~i', $path)) {
            return redirect()->back()->with('error', 'Error: Unsupported link. Paste a Twitch VOD link (twitch.tv/videos/…) or a Kick VOD link (kick.com/<channel>/videos/…).');
        }

        if (!$source) {
            if (!file_exists($path)) {
                return redirect()->back()->with('error', 'Error: File does not exist at the provided path.');
            }

            $allowedExtensions = ['mp4', 'mov', 'mkv', 'webm', 'm4v', 'avi'];
            $extension = strtolower(pathinfo($path, PATHINFO_EXTENSION));
            if (!in_array($extension, $allowedExtensions)) {
                return redirect()->back()->with('error', 'Error: Unsupported format .' . $extension . '. Supported formats: ' . implode(', ', $allowedExtensions));
            }
        }

        // Build processing settings from form toggles
        $settings = [
            'output_format' => $request->input('output_format', '9:16'),
            'caption_style' => $request->input('caption_style', 'yellow_pop'),
            'caption_font' => $request->input('caption_font', 'Arial Black'),
            'caption_position' => $request->input('caption_position', 'bottom'),
            'caption_layout' => $request->input('caption_layout', 'two_line'),
            'transition_speed' => (float) $request->input('transition_speed', 0.25),
            'target_clip_count' => (int) $request->input('target_clip_count', 5),
            'full_video_mode' => $request->input('processing_mode') === 'full_video',
            'stream_moments' => $request->input('processing_mode') === 'stream_moments',
            'whisper_model' => $request->input('whisper_model', 'small'),
            'language_mode' => $request->input('language_mode', 'auto'),
            'hardware_accel' => $request->input('hardware_accel', 'auto'),
            'smart_crop' => $request->boolean('smart_crop'),
            'auto_captions' => $request->boolean('auto_captions'),
            'punch_in_zoom' => $request->boolean('punch_in_zoom'),
            'ken_burns' => $request->boolean('ken_burns'),
            'emoji_overlays' => $request->boolean('emoji_overlays'),
            'whip_pan_transitions' => $request->boolean('whip_pan_transitions'),
            'background_music' => $request->boolean('background_music'),
            'bgm_path' => $request->input('bgm_path', ''),
            'split_screen' => $request->boolean('split_screen'),
            'gaming_layout' => $request->boolean('gaming_layout'),
        ];

        if ($source) {
            // Link import: the engine downloads the VOD (and Twitch chat) into storage/app/vods/{id}/
            $settings['source_url'] = $path;
            $settings['source_platform'] = $source['platform'];
            $settings['source_vod_id'] = $source['vod_id'];

            $video = LongVideo::create([
                'filename' => ucfirst($source['platform']) . ' VOD ' . $source['vod_id'],
                'storage_path' => '',
                'status' => 'pending',
                'processing_settings' => $settings,
            ]);

            $this->dispatchEngineProcess($video);

            $what = $source['platform'] === 'twitch' ? 'video + chat' : "video only, Kick chat can't be fetched";
            return redirect()->back()->with('success', 'Import started for ' . $video->filename . ' (' . $what . ')');
        }

        $video = LongVideo::create([
            'filename' => basename($path),
            'storage_path' => $path,
            'status' => 'pending',
            'processing_settings' => $settings,
        ]);

        $this->dispatchEngineProcess($video);

        return redirect()->back()->with('success', 'Processing started for ' . $video->filename);
    }

    /**
     * Recognise a Twitch or Kick VOD link. Mirrors processor/vod_import.py parse_source_url().
     *
     * @return array{platform: string, vod_id: string}|null
     */
    public static function parseVodUrl(string $url): ?array
    {
        $url = trim($url);
        if (preg_match('~^https?://(?:www\.|m\.)?twitch\.tv/videos/(\d+)~i', $url, $m)) {
            return ['platform' => 'twitch', 'vod_id' => $m[1]];
        }
        if (preg_match('~^https?://(?:www\.)?kick\.com/[\w-]+/videos/([0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})~i', $url, $m)) {
            return ['platform' => 'kick', 'vod_id' => strtolower($m[1])];
        }
        return null;
    }

    private function vodImportDir(LongVideo $video): string
    {
        return storage_path('app/vods/' . $video->id);
    }

    private function dispatchEngineProcess(LongVideo $video): void
    {
        if (app()->runningUnitTests()) {
            return;
        }

        $pythonPath = $this->getPythonBinary();
        $scriptPath = base_path('processor/engine.py');
        $logFile = storage_path('logs/engine_' . $video->id . '.log');
        
        if (strtoupper(substr(PHP_OS, 0, 3)) === 'WIN') {
            pclose(popen('start /B cmd /c ""' . $pythonPath . '" "' . $scriptPath . '" ' . $video->id . ' > "' . $logFile . '" 2>&1"', 'r'));
        } else {
            $cmd = escapeshellarg($pythonPath) . ' ' . escapeshellarg($scriptPath) . ' ' . escapeshellarg($video->id);
            exec($cmd . ' > ' . escapeshellarg($logFile) . ' 2>&1 &');
        }
    }

    public function retry($id)
    {
        $video = LongVideo::with('clips')->findOrFail($id);
        $isImport = !empty($video->processing_settings['source_url']);

        // Link imports re-download (resuming any partial file), so a missing file is fine.
        if (!$isImport && (!$video->storage_path || !file_exists($video->storage_path))) {
            return redirect()->back()->with('error', 'Cannot retry: Source video file no longer exists at ' . $video->storage_path);
        }

        foreach ($video->clips as $clip) {
            $this->cleanupClipFiles($clip);
            $clip->delete();
        }

        $logFile = storage_path('logs/engine_' . $video->id . '.log');
        if (file_exists($logFile)) {
            @unlink($logFile);
        }

        $video->status = 'pending';
        $video->save();

        $this->dispatchEngineProcess($video);

        return redirect()->back()->with('success', 'Re-started pipeline for ' . $video->filename);
    }

    public function getLogs($id)
    {
        $video = \App\Models\LongVideo::findOrFail($id);
        $logFile = storage_path('logs/engine_' . $video->id . '.log');
        $logContent = '';
        if (file_exists($logFile)) {
            $logContent = file_get_contents($logFile);
        }
        
        $currentStep = 'Initializing pipeline...';
        $stepIndex = 0; // 0: init/pending, 1: transcribe, 2: analyze, 3: render, 4: ready
        $progressPercent = 10;
        
        $sLower = strtolower($video->status);

        if ($sLower === 'transcribing') {
            $stepIndex = 1;
            $progressPercent = 25;
            $currentStep = 'Transcribing audio locally with Faster-Whisper';
            // Stream Moments: scan chat + audio first, then transcribe only the moment windows
            if (preg_match_all('/^\s*📝 Transcribing moment window (\d+\/\d+)/mu', $logContent, $mw)) {
                $currentStep = 'Transcribing moment window ' . end($mw[1]);
                $progressPercent = 35;
            } elseif (str_contains($logContent, 'Scanning for stream moments')) {
                $currentStep = 'Detecting chat floods and audio spikes';
                $progressPercent = 30;
            }
        } elseif ($sLower === 'analyzing') {
            $stepIndex = 2;
            $progressPercent = 50;
            $ai = str_contains($logContent, 'Trying Gemini model') ? 'Gemini AI (backup)' : 'Groq AI';
            $currentStep = !empty($video->processing_settings['stream_moments'])
                ? "Ranking stream moments with {$ai}"
                : "Analyzing transcript with {$ai} for viral hooks";
        } elseif ($sLower === 'processing') {
            $stepIndex = 3;
            $progressPercent = 70;
            $currentStep = 'Rendering clips with FFmpeg';
            if (str_contains($logContent, 'Rendering clip')) {
                preg_match_all('/Rendering clip (\d+)/', $logContent, $matches);
                $clipNum = !empty($matches[1]) ? end($matches[1]) : '?';
                $currentStep = "Rendering clip #{$clipNum} with FFmpeg";
                $progressPercent = 80;
            }
        } elseif ($sLower === 'completed') {
            $stepIndex = 4;
            $progressPercent = 100;
            $currentStep = 'Pipeline completed! All clips ready.';
        } elseif ($sLower === 'failed') {
            $progressPercent = 100;
            $currentStep = 'Pipeline failed. Check console logs.';
            $importError = $video->processing_settings['import_error'] ?? null;
            if (!$importError && preg_match('/^IMPORT ERROR: (.+)$/m', $logContent, $m)) {
                $importError = trim($m[1]);
            }
            if ($importError) {
                $currentStep = 'Import failed: ' . $importError;
            }
        } elseif (preg_match_all('/^(Importing \w+ VOD .+|Downloading VOD: .+|Downloading chat log.*)$/m', $logContent, $dl)) {
            // Link import in progress (status stays 'pending' until the download finishes)
            $last = trim(end($dl[1]));
            $currentStep = $last;
            if (str_starts_with($last, 'Importing')) {
                $progressPercent = 2;
                $currentStep = 'Reading VOD info';
            } elseif (str_starts_with($last, 'Downloading chat')) {
                $progressPercent = 20;
                $currentStep = 'Downloading Twitch chat log';
            } elseif (preg_match('/Downloading VOD: ([\d.]+)%/', $last, $pm)) {
                $progressPercent = (int) round(2 + min(100, (float) $pm[1]) * 0.18);
            } else {
                $progressPercent = 20;
            }
        } else {
            // Check logs if status is still pending or transitioning
            if (str_contains($logContent, 'Extracting audio')) {
                $stepIndex = 1;
                $progressPercent = 15;
                $currentStep = 'Extracting audio track';
            } elseif (str_contains($logContent, 'Transcribing audio')) {
                $stepIndex = 1;
                $progressPercent = 30;
                $currentStep = 'Transcribing audio locally';
            } elseif (str_contains($logContent, 'Analyzing transcript')) {
                $stepIndex = 2;
                $progressPercent = 55;
                $currentStep = 'Analyzing transcript with Groq AI';
            } elseif (str_contains($logContent, 'Rendering clip')) {
                $stepIndex = 3;
                $progressPercent = 80;
                $currentStep = 'Rendering clips with FFmpeg';
            }
        }

        return response()->json([
            'status' => $video->status,
            'current_step' => $currentStep,
            'step_index' => $stepIndex,
            'progress_percent' => $progressPercent,
            'logs' => $logContent ?: 'No log records yet.'
        ]);
    }

    private function cleanupClipFiles(\App\Models\VideoClip $clip): void
    {
        $filesToDelete = [
            $clip->output_path ? base_path($clip->output_path) : null,
            storage_path("app/intermediate_{$clip->id}.mp4"),
            storage_path("app/clip_{$clip->id}_words.json"),
            storage_path("app/clip_{$clip->id}.ass"),
            storage_path("logs/re_render_{$clip->id}.log"),
            storage_path("app/public/clip_{$clip->id}_frame.jpg"),
        ];

        foreach ($filesToDelete as $file) {
            if ($file && file_exists($file)) {
                @unlink($file);
            }
        }
    }

    public function destroyClip(Request $request, $id)
    {
        $clip = \App\Models\VideoClip::findOrFail($id);
        $this->cleanupClipFiles($clip);
        $clip->delete();
        
        return redirect()->back()->with('success', 'Clip removed successfully.');
    }

    public function destroy($id)
    {
        $video = \App\Models\LongVideo::with('clips')->findOrFail($id);
        
        foreach ($video->clips as $clip) {
            $this->cleanupClipFiles($clip);
            $clip->delete();
        }
        
        $tempMp3 = storage_path('app/temp_' . $video->id . '.mp3');
        if (file_exists($tempMp3)) {
            @unlink($tempMp3);
        }
        
        $logFile = storage_path('logs/engine_' . $video->id . '.log');
        if (file_exists($logFile)) {
            @unlink($logFile);
        }

        // Link imports own their downloaded VOD + chat folder; local files are never touched.
        if (!empty($video->processing_settings['source_url'])) {
            \Illuminate\Support\Facades\File::deleteDirectory($this->vodImportDir($video));
        }

        $video->delete();
        
        return redirect()->back()->with('success', 'Video and all clips removed successfully.');
    }

    public function getClipStatus($id)
    {
        $clip = \App\Models\VideoClip::findOrFail($id);
        return response()->json([
            'id' => $clip->id,
            'status' => $clip->status,
            'updated_at' => $clip->updated_at?->timestamp ?? time(),
        ]);
    }

    public function openExplorer($id)
    {
        $clip = \App\Models\VideoClip::findOrFail($id);
        if ($clip->output_path && file_exists(base_path($clip->output_path))) {
            $absPath = str_replace('/', '\\', base_path($clip->output_path));
            $cleanPath = str_replace(['"', '`', '%', '$'], '', $absPath);
            if (strtoupper(substr(PHP_OS, 0, 3)) === 'WIN') {
                pclose(popen('explorer.exe /select,"' . $cleanPath . '"', 'r'));
            }
            return response()->json(['success' => true]);
        }
        return response()->json(['error' => 'File not found on disk.'], 404);
    }
    public function getTranscript($id)
    {
        $clip = \App\Models\VideoClip::findOrFail($id);
        $jsonPath = storage_path("app/clip_{$clip->id}_words.json");
        if (file_exists($jsonPath)) {
            $words = json_decode(file_get_contents($jsonPath), true);
            return response()->json(['success' => true, 'words' => $words]);
        }
        return response()->json(['error' => 'Transcript not found. Please reprocess the video to generate word-level timings.'], 404);
    }

    public function reRenderClip(Request $request, $id)
    {
        $clip = \App\Models\VideoClip::findOrFail($id);
        
        $request->validate([
            'words' => 'required|array|min:1',
            'words.*.word' => 'required|string|max:120',
            'words.*.start' => 'required|numeric|min:0',
            'words.*.end' => 'required|numeric|min:0',
            'caption_style' => 'nullable|string|in:yellow_pop,neon_cyan,bold_white,hormozi_box,karaoke_green,cyber_pink,fire_gold,electric_violet',
            'caption_position' => 'nullable|string|in:bottom,center,top',
        ]);

        // Save updated words
        $jsonPath = storage_path("app/clip_{$clip->id}_words.json");
        file_put_contents($jsonPath, json_encode($request->words, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));

        // Update clip status
        $clip->status = 'rendering';
        $clip->save();

        // Optional style & position overrides
        $captionStyle = $request->input('caption_style', '');
        $captionPos = $request->input('caption_position', '');

        $extraArgs = '';
        if (!empty($captionStyle)) {
            $extraArgs .= ' ' . escapeshellarg($captionStyle);
            if (!empty($captionPos)) {
                $extraArgs .= ' ' . escapeshellarg($captionPos);
            }
        }

        $this->dispatchReRender($clip, $extraArgs);

        return response()->json(['success' => true]);
    }

    /**
     * Save a user-adjusted facecam box for a gaming-layout clip and re-render it.
     * Box values are fractions (0..1) of the source frame; "none" removes the cam panel.
     */
    public function adjustFacecam(Request $request, $id)
    {
        $clip = \App\Models\VideoClip::findOrFail($id);

        $crop = json_decode($clip->crop_coordinates_json ?? '', true);
        if (!is_array($crop) || empty($crop['gaming_layout'])) {
            return response()->json(['error' => 'This clip was not rendered with the gaming facecam layout.'], 422);
        }

        $request->validate([
            'none' => 'sometimes|boolean',
            'x' => 'required_unless:none,true|numeric|min:0|max:1',
            'y' => 'required_unless:none,true|numeric|min:0|max:1',
            'w' => 'required_unless:none,true|numeric|min:0.03|max:1',
            'h' => 'required_unless:none,true|numeric|min:0.03|max:1',
        ]);

        $layout = $crop['gaming_layout'];
        $inputW = (int) ($layout['input_w'] ?? 1920);
        $inputH = (int) ($layout['input_h'] ?? 1080);

        if ($request->boolean('none')) {
            $layout['cam_box'] = null;
        } else {
            $even = fn (float $v) => max(16, ((int) round($v)) - (((int) round($v)) % 2));
            $w = min($even($request->input('w') * $inputW), $inputW - ($inputW % 2));
            $h = min($even($request->input('h') * $inputH), $inputH - ($inputH % 2));
            $x = (int) max(0, min(round($request->input('x') * $inputW), $inputW - $w));
            $y = (int) max(0, min(round($request->input('y') * $inputH), $inputH - $h));
            $layout['cam_box'] = [$x, $y, $w, $h];
        }
        $layout['auto_detected'] = false;
        $crop['gaming_layout'] = $layout;

        $clip->crop_coordinates_json = json_encode($crop);
        $clip->status = 'rendering';
        $clip->save();

        $this->dispatchReRender($clip);

        return response()->json(['success' => true, 'cam_box' => $layout['cam_box']]);
    }

    private function dispatchReRender(\App\Models\VideoClip $clip, string $extraArgs = ''): void
    {
        if (app()->runningUnitTests()) {
            return;
        }

        $pythonPath = $this->getPythonBinary();
        $scriptPath = base_path('processor/re_render_clip.py');
        $logFile = storage_path('logs/re_render_' . $clip->id . '.log');

        if (strtoupper(substr(PHP_OS, 0, 3)) === 'WIN') {
            $cmd = 'start /B cmd /c ""' . $pythonPath . '" "' . $scriptPath . '" ' . $clip->id . $extraArgs . ' > "' . $logFile . '" 2>&1"';
            pclose(popen($cmd, 'r'));
        } else {
            $cmd = escapeshellarg($pythonPath) . ' ' . escapeshellarg($scriptPath) . ' ' . escapeshellarg($clip->id) . $extraArgs;
            exec($cmd . ' > ' . escapeshellarg($logFile) . ' 2>&1 &');
        }
    }
}
