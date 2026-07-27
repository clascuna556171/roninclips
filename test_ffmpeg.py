import subprocess
cmd = r'''ffmpeg -f lavfi -i color=c=black:s=1280x720 -vf "drawtext=fontfile='C\:/Windows/Fonts/seguiemj.ttf':text='🔥':fontsize=64:x=10:y=10" -frames:v 1 -y test_emoji.mp4'''
result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='utf-8')
print("STDOUT:", result.stdout)
print("STDERR:", result.stderr[-1000:])
