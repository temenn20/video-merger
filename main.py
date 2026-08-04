from flask import Flask, request, jsonify
import subprocess
import requests
import os

app = Flask(__name__)

@app.route('/merge', methods=['POST'])
def merge():
    data = request.json
    video_url = data.get('video_url')
    audio_url = data.get('audio_url')

    # Dosyaları indir
    with open('video.mp4', 'wb') as f:
        f.write(requests.get(video_url).content)
    with open('audio.mp3', 'wb') as f:
        f.write(requests.get(audio_url).content)

    # FFmpeg ile birleştir
    cmd = "ffmpeg -y -i video.mp4 -i audio.mp3 -c:v copy -c:a aac output.mp4"
    subprocess.run(cmd, shell=True)

    return jsonify({"status": "success", "message": "Video merged successfully"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
