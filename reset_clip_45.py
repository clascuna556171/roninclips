import sys
import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv('.env')

db = mysql.connector.connect(
    host=os.environ.get('DB_HOST', '127.0.0.1'),
    user=os.environ.get('DB_USERNAME', 'root'),
    password=os.environ.get('DB_PASSWORD', ''),
    database=os.environ.get('DB_DATABASE', 'roninclips'),
    port=int(os.environ.get('DB_PORT', 3306))
)
cursor = db.cursor()

# Set all clips to ready EXCEPT 45 to force processing of just 45
cursor.execute("UPDATE video_clips SET status = 'ready' WHERE long_video_id = 11")
cursor.execute("UPDATE video_clips SET status = 'pending' WHERE id = 45")

# Ensure the video is in processing status
cursor.execute("UPDATE long_videos SET status = 'processing' WHERE id = 11")
db.commit()

db.close()
print("Reset clip 45 to pending, set others to ready.")
