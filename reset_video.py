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
cursor = db.cursor()
cursor.execute("UPDATE long_videos SET status = 'pending' WHERE id = 14")
cursor.execute("DELETE FROM video_clips WHERE long_video_id = 14")
db.commit()
print('Reset video 14 for reprocessing')
db.close()
