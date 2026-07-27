import mysql.connector
from dotenv import load_dotenv
import os

load_dotenv('.env')
db = mysql.connector.connect(
    host=os.environ.get('DB_HOST', '127.0.0.1'),
    user=os.environ.get('DB_USERNAME', 'root'),
    password=os.environ.get('DB_PASSWORD', ''),
    database=os.environ.get('DB_DATABASE', 'roninclips'),
    port=int(os.environ.get('DB_PORT', 3306))
)
cursor = db.cursor(dictionary=True)
cursor.execute('SELECT id, status, filename, storage_path FROM long_videos ORDER BY id DESC LIMIT 5')
rows = cursor.fetchall()
print("=== Videos ===")
for r in rows:
    print(r)

cursor.execute('SELECT id, long_video_id, status, start_time, end_time FROM video_clips ORDER BY id DESC LIMIT 10')
clips = cursor.fetchall()
print("\n=== Clips ===")
for c in clips:
    print(c)
db.close()
