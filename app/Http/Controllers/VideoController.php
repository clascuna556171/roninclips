<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use App\Models\LongVideo;
use Symfony\Component\Process\Process;

class VideoController extends Controller
{
    public function index()
    {
        $videos = LongVideo::with('clips')->latest()->get();
        return view('dashboard', compact('videos'));
    }

    public function store(Request $request)
    {
        $request->validate(['video_path' => 'required|string']);
        
        $path = $request->video_path;
        if (!file_exists($path)) {
            return redirect()->back()->with('error', 'Error: File does not exist at the provided path.');
        }

        if (strtolower(pathinfo($path, PATHINFO_EXTENSION)) !== 'mp4') {
            return redirect()->back()->with('error', 'Error: Only .mp4 files are supported.');
        }

        // Build processing settings from form toggles
        // NOTE: HTML forms don't send unchecked checkboxes, so boolean() defaults
        // must be false — the checkbox being present means it's checked.
        $settings = [
            'output_format' => $request->input('output_format', '9:16'),
            'caption_style' => $request->input('caption_style', 'yellow_pop'),
            'caption_font' => $request->input('caption_font', 'Arial Black'),
            'caption_position' => $request->input('caption_position', 'bottom'),
            'caption_layout' => $request->input('caption_layout', 'two_line'),
            'transition_speed' => (float) $request->input('transition_speed', 0.25),
            'target_clip_count' => (int) $request->input('target_clip_count', 5),
            'full_video_mode' => $request->input('processing_mode') === 'full_video',
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

        // Start the process completely detached from PHP
        // This is crucial on Windows, otherwise the process is killed when the PHP request ends
        $pythonPath = 'python';
        $scriptPath = base_path('processor/engine.py');
        $logFile = storage_path('logs/engine_' . $video->id . '.log');
        
        if (strtoupper(substr(PHP_OS, 0, 3)) === 'WIN') {
            pclose(popen('start /B cmd /c "python "' . $scriptPath . '" ' . $video->id . ' > "' . $logFile . '" 2>&1"', 'r'));
        } else {
            $cmd = escapeshellarg($pythonPath) . ' ' . escapeshellarg($scriptPath) . ' ' . escapeshellarg($video->id);
            exec($cmd . ' > ' . escapeshellarg($logFile) . ' 2>&1 &');
        }

        return redirect()->back()->with('success', 'Processing started for ' . $video->filename);
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
        if (str_contains($logContent, 'Extracting audio')) {
            $currentStep = 'Extracting audio track';
        }
        if (str_contains($logContent, 'Transcribing audio')) {
            $currentStep = 'Transcribing audio locally';
        }
        if (str_contains($logContent, 'Analyzing transcript')) {
            $currentStep = 'Analyzing transcript with Groq';
        }
        if (str_contains($logContent, 'FULL VIDEO MODE')) {
            $currentStep = 'Full video mode — skipping AI clipping';
        }
        if (str_contains($logContent, 'Found') && str_contains($logContent, 'viral hook candidates')) {
            $currentStep = 'AI analysis complete, preparing render';
        }
        if (str_contains($logContent, 'Inserted 1 full-video clip entry')) {
            $currentStep = 'Full video clip entry created, preparing render';
        }
        if (str_contains($logContent, 'Rendering clip')) {
            preg_match_all('/Rendering clip (\d+)/', $logContent, $matches);
            $clipNum = !empty($matches[1]) ? end($matches[1]) : '?';
            $currentStep = "Rendering clip #{$clipNum} with FFmpeg";
        }
        
        if ($video->status === 'completed') {
            $currentStep = 'Pipeline completed!';
        } elseif ($video->status === 'failed') {
            $currentStep = 'Pipeline failed. Check logs.';
        }

        return response()->json([
            'status' => $video->status,
            'current_step' => $currentStep,
            'logs' => $logContent ?: 'No log records yet.'
        ]);
    }

    public function destroyClip(Request $request, $id)
    {
        $clip = \App\Models\VideoClip::findOrFail($id);
        
        if ($clip->output_path && file_exists(base_path($clip->output_path))) {
            @unlink(base_path($clip->output_path));
        }
        
        $clip->delete();
        
        return redirect()->back()->with('success', 'Clip removed successfully.');
    }

    public function destroy($id)
    {
        $video = \App\Models\LongVideo::with('clips')->findOrFail($id);
        
        foreach ($video->clips as $clip) {
            if ($clip->output_path && file_exists(base_path($clip->output_path))) {
                @unlink(base_path($clip->output_path));
            }
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

    public function openExplorer($id)
    {
        $clip = \App\Models\VideoClip::findOrFail($id);
        if ($clip->output_path && file_exists(base_path($clip->output_path))) {
            $absPath = str_replace('/', '\\', base_path($clip->output_path));
            if (strtoupper(substr(PHP_OS, 0, 3)) === 'WIN') {
                pclose(popen('explorer.exe /select,"' . $absPath . '"', 'r'));
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
            'words' => 'required|array'
        ]);

        // Save updated words
        $jsonPath = storage_path("app/clip_{$clip->id}_words.json");
        file_put_contents($jsonPath, json_encode($request->words, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));

        // Update clip status
        $clip->status = 'rendering';
        $clip->save();

        // Run the python re-render script
        $pythonPath = 'python';
        $scriptPath = base_path('processor/re_render_clip.py');
        $logFile = storage_path('logs/re_render_' . $clip->id . '.log');
        
        if (strtoupper(substr(PHP_OS, 0, 3)) === 'WIN') {
            pclose(popen('start /B cmd /c "python "' . escapeshellarg($scriptPath) . '" ' . $clip->id . ' > "' . $logFile . '" 2>&1"', 'r'));
        } else {
            $cmd = escapeshellarg($pythonPath) . ' ' . escapeshellarg($scriptPath) . ' ' . escapeshellarg($clip->id);
            exec($cmd . ' > ' . escapeshellarg($logFile) . ' 2>&1 &');
        }

        return response()->json(['success' => true]);
    }
}
