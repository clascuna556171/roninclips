<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use App\Models\LongVideo;
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
        $hasNvidia = file_exists('C:\\Windows\\System32\\nvidia-smi.exe') || file_exists('/usr/bin/nvidia-smi');
        $hwBadge = $hasNvidia ? 'CUDA GPU' : 'CPU ENGINE';
        $activeJobsCount = $videos->whereNotIn('status', ['completed', 'failed'])->count();
        $totalClipsCount = $videos->sum(function($v) {
            return $v->clips->where('status', 'ready')->count();
        });

        return view('dashboard', compact(
            'videos', 'dbDriver', 'groqModel', 'hwBadge', 'activeJobsCount', 'totalClipsCount'
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
        
        $path = $request->video_path;
        if (!file_exists($path)) {
            return redirect()->back()->with('error', 'Error: File does not exist at the provided path.');
        }

        $allowedExtensions = ['mp4', 'mov', 'mkv', 'webm', 'm4v', 'avi'];
        $extension = strtolower(pathinfo($path, PATHINFO_EXTENSION));
        if (!in_array($extension, $allowedExtensions)) {
            return redirect()->back()->with('error', 'Error: Unsupported format .' . $extension . '. Supported formats: ' . implode(', ', $allowedExtensions));
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
        ];
        
        $video = LongVideo::create([
            'filename' => basename($path),
            'storage_path' => $path,
            'status' => 'pending',
            'processing_settings' => $settings,
        ]);

        $this->dispatchEngineProcess($video);

        return redirect()->back()->with('success', 'Processing started for ' . $video->filename);
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

        if (!$video->storage_path || !file_exists($video->storage_path)) {
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
        } elseif ($sLower === 'analyzing') {
            $stepIndex = 2;
            $progressPercent = 50;
            $currentStep = 'Analyzing transcript with Groq AI for viral hooks';
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

        // Run the python re-render script
        $pythonPath = $this->getPythonBinary();
        $scriptPath = base_path('processor/re_render_clip.py');
        $logFile = storage_path('logs/re_render_' . $clip->id . '.log');
        
        $extraArgs = '';
        if (!empty($captionStyle)) {
            $extraArgs .= ' ' . escapeshellarg($captionStyle);
            if (!empty($captionPos)) {
                $extraArgs .= ' ' . escapeshellarg($captionPos);
            }
        }
        
        if (strtoupper(substr(PHP_OS, 0, 3)) === 'WIN') {
            $cmd = 'start /B cmd /c ""' . $pythonPath . '" "' . $scriptPath . '" ' . $clip->id . $extraArgs . ' > "' . $logFile . '" 2>&1"';
            pclose(popen($cmd, 'r'));
        } else {
            $cmd = escapeshellarg($pythonPath) . ' ' . escapeshellarg($scriptPath) . ' ' . escapeshellarg($clip->id) . $extraArgs;
            exec($cmd . ' > ' . escapeshellarg($logFile) . ' 2>&1 &');
        }

        return response()->json(['success' => true]);
    }
}
