import subprocess
cmd = r'''ffmpeg -f lavfi -i color=c=black:s=1280x720 -vf "drawtext=fontfile='C\:/Windows/Fonts/seguiemj.ttf':text='🔥':fontsize='if(between(t,36.680,36.830),76-(12)*(t-36.680)/0.150,64)':x=769:y=293:alpha='if(between(t,36.680,36.830),(t-36.680)/0.150,if(between(t,36.830,37.880),1,if(between(t,37.880,38.180),1-(t-37.880)/0.300,0)))':enable='between(t,36.680,38.180)'" -frames:v 1 -y test_emoji2.mp4'''
result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='utf-8')
print("RETURN CODE:", result.returncode)
print("STDERR:", result.stderr[-1000:])
