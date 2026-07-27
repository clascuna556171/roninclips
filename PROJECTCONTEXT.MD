NOTE: WE MUST DO THIS PROJECT AS COMPLETE FREE NO FEES AT ALL

Architecture & Pipeline
The Hybrid Architecture Flow

Your application will operate as a coordinated local ecosystem:

* **The Frontend & Control Center (Laravel):** A local dashboard where you drop a long-form video file, view your finished clips, and manage tags.
* **The Data Layer (MySQL):** Stores paths to your raw videos, extracted transcripts, AI-generated hook timestamps, and crop settings.
* **The Processor (Python Engine):** A background script executed by Laravel (or running as a polling worker) that talks to the Gemini API, processes frames via MediaPipe, and calls FFmpeg.

Interactive Pipeline Explorer

Use this interactive breakdown to see exactly how your chosen tools pass data back and forth during each phase of the video processing lifecycle.

Implementation Blueprints

Save these two markdown blueprints to your local project directory to guide your development step-by-step.

PHASE_1_DATABASE_AND_UI.md

```markdown
# Phase 1: Storage & Control Center (Laravel + MySQL)

## 1. Database Schema
Run this migration to track your video processing state.

```sql
CREATE TABLE long_videos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    filename VARCHAR(255),
    storage_path VARCHAR(255),
    status ENUM('pending', 'transcribing', 'analyzing', 'processing', 'completed', 'failed') DEFAULT 'pending',
    transcript LONGTEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE video_clips (
    id INT AUTO_INCREMENT PRIMARY KEY,
    long_video_id INT,
    start_time TIME,
    end_time TIME,
    hook_explanation TEXT,
    crop_coordinates_json JSON DEFAULT NULL,
    output_path VARCHAR(255) DEFAULT NULL,
    status ENUM('pending', 'rendering', 'ready') DEFAULT 'pending',
    FOREIGN KEY (long_video_id) REFERENCES long_videos(id) ON DELETE CASCADE
);

```

## 2. Laravel Route & Controller Setup

Create a simple controller to handle file paths and trigger the Python backend.

```php
// app/Http/Controllers/VideoController.php
namespace App\Http\Controllers;

use Illuminate\Http\Request;
use App\Models\LongVideo;
use Symfony\Component\Process\Process;

class VideoController extends Controller
{
    public function store(Request $request)
    {
        $request->validate(['video_path' => 'required|string']);
        
        // Since it's local, just point to the absolute path of the file on your disk
        $video = LongVideo::create([
            'filename' => basename($request->video_path),
            'storage_path' => $request->video_path,
            'status' => 'pending'
        ]);

        // Trigger Python processing worker in the background asynchronously
        $process = new Process(['python3', base_path('processor/engine.py'), $video->id]);
        $process->disableOutput();
        $process->start();

        return response()->json(['message' => 'Processing started', 'id' => $video->id]);
    }
}

```

```

PHASE_2_PYTHON_AI_ENGINE.md
```markdown
# Phase 2: Core Processing Engine (Python + Gemini + FFmpeg)

Create a directory named `processor/` in your root folder. This script handles the AI transcription, hook analysis, and heavy rendering lifecycles.

## Dependency Setup
```bash
pip install google-generativeai mysql-connector-python opencv-python mediapipe

```

## `processor/engine.py` Core Logic

```python
import sys
import os
import subprocess
import mysql.connector
import google.generativeai as genai
import json

# 1. Boot Environment & Context
VIDEO_ID = sys.argv[1]
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

db = mysql.connector.connect(
    host="127.0.0.1", user="root", password="", database="your_local_db"
)
cursor = db.cursor(dictionary=True)

# Fetch video metadata
cursor.execute("SELECT * FROM long_videos WHERE id = %s", (VIDEO_ID,))
video = cursor.fetchone()

# 2. Extract Audio & Transcribe (Using Free Local FFmpeg + API)
audio_path = f"storage/app/temp_{VIDEO_ID}.mp3"
subprocess.run(f"ffmpeg -i {video['storage_path']} -q:a 0 -map a {audio_path} -y", shell=True)

# 3. Request Hook Points from Gemini Pro 
# Leveraging Gemini 1.5 flash native multimodal capabilities
print("Uploading audio block to Gemini Pro...")
audio_file = genai.upload_file(path=audio_path)

model = genai.GenerativeModel(model_name="gemini-1.5-flash" )
prompt = """
Analyze this audio file. Find up to 3 highly engaging, self-contained clips suitable for short-form video (TikTok/Shorts). 
Each clip must be between 30 and 60 seconds long.
Return your answer strict JSON format exactly matching this structure:
[
  {"start": "00:01:15", "end": "00:02:00", "reason": "Why this segment is hooky"}
]
"""

response = model.generate_content([audio_file, prompt])
# Strip any markdown backticks from the model output if present
clean_json = response.text.replace("```json", "").replace("```", "").strip()
clips = json.loads(clean_json)

# 4. Save Timestamps to MySQL for Laravel to view
for clip in clips:
    cursor.execute(
        "INSERT INTO video_clips (long_video_id, start_time, end_time, hook_explanation) VALUES (%s, %s, %s, %s)",
        (VIDEO_ID, clip['start'], clip['end'], clip['reason'])
    )
db.commit()

# 5. Programmatic Execution Block (FFmpeg Clipper)
cursor.execute("SELECT * FROM video_clips WHERE long_video_id = %s", (VIDEO_ID,))
saved_clips = cursor.fetchall()

for sc in saved_clips:
    output_clip = f"storage/app/public/clip_{sc['id']}.mp4"
    
    # Fast native cut command without re-encoding to test timestamps instantly
    ffmpeg_cmd = f"ffmpeg -ss {sc['start_time']} -to {sc['end_time']} -i {video['storage_path']} -c copy {output_clip} -y"
    subprocess.run(ffmpeg_cmd, shell=True)
    
    cursor.execute("UPDATE video_clips SET output_path = %s, status = 'ready' WHERE id = %s", (output_clip, sc['id']))

cursor.execute("UPDATE long_videos SET status = 'completed' WHERE id = %s", (VIDEO_ID,))
db.commit()
print("Pipeline process completed successfully.")

```

```

Implementation Pro-Tips
1. **Bypassing Upload Limits:** Because this app runs completely on your localhost, you don't actually need to "upload" giant 2GB files through an HTTP request. On your frontend layout form, just put a regular text box input where you copy-paste the absolute string file path from your local operating system file explorer (e.g., `/Users/name/Videos/podcast_01.mp4`). Your Laravel code can immediately read it straight from your hard drive via the Python script.
2. **Gemini Media API Cleanup:** The Python script uses `genai.upload_file()`. This stores the audio temporarily on Google's infrastructure for processing. Files under 2GB are automatically deleted after 48 hours for free, so you don't even have to write storage deletion cron jobs.

```
