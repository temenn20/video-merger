import os
import re
import uuid
import subprocess
import requests
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

UPLOAD_FOLDER = '/tmp'

def extract_drive_id(url_or_id):
    if not url_or_id:
        return None
    match = re.search(r'/d/([a-zA-Z0-9_-]+)', url_or_id)
    if match:
        return match.group(1)
    match_id = re.search(r'id=([a-zA-Z0-9_-]+)', url_or_id)
    if match_id:
        return match_id.group(1)
    return url_or_id

def download_file(video_param, destination):
    file_id = extract_drive_id(video_param)
    if not file_id:
        return False
        
    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    session = requests.Session()
    response = session.get(download_url, stream=True)
    
    for key, value in response.cookies.items():
        if key.startswith('download_warning'):
            download_url += f"&confirm={value}"
            response = session.get(download_url, stream=True)
            break
            
    if response.status_code == 200:
        with open(destination, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    return False

@app.route('/process', methods=['POST'])
def process_media():
    session_id = str(uuid.uuid4())[:8]
    video_path = os.path.join(UPLOAD_FOLDER, f"input_video_{session_id}.mp4")
    audio_path = os.path.join(UPLOAD_FOLDER, f"input_audio_{session_id}.mp3")
    output_path = os.path.join(UPLOAD_FOLDER, f"output_{session_id}.mp4")

    try:
        data = request.get_json(silent=True) or {}
        video_url = data.get('video_url') or request.form.get('video_url')
        audio_url = data.get('audio_url') or request.form.get('audio_url')

        if not video_url:
            return jsonify({"status": "error", "message": "video_url bulunamadı!"}), 400

        print(f"[{session_id}] Video indiriliyor...")
        if not download_file(video_url, video_path):
            return jsonify({"status": "error", "message": "Video indirilemedi."}), 500

        print(f"[{session_id}] Ses indiriliyor...")
        if audio_url and audio_url.startswith('http'):
            r = requests.get(audio_url)
            with open(audio_path, 'wb') as f:
                f.write(r.content)
        elif request.data:
            with open(audio_path, 'wb') as f:
                f.write(request.data)
        else:
            # Gelen veriyi string olarak kaydet
            with open(audio_path, 'wb') as f:
                f.write(str(audio_url).encode('utf-8'))

        # 3. Esnek FFmpeg Birleştirme
        print(f"[{session_id}] FFmpeg çalıştırılıyor...")
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-probesize', '50M',
            '-analyzeduration', '100M',
            '-i', video_path,
            '-i', audio_path,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-strict', '-2',
            '-map', '0:v:0',
            '-map', '1:a:0',
            '-shortest',
            output_path
        ]

        result = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if result.returncode != 0:
            print(f"[{session_id}] FFmpeg Hatası:\n{result.stderr}")
            return jsonify({"status": "error", "message": "FFmpeg hatası", "details": result.stderr}), 500

        print(f"[{session_id}] Başarılı!")
        return send_file(output_path, mimetype='video/mp4', as_attachment=True, download_name='final_video.mp4')

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    finally:
        for p in [video_path, audio_path, output_path]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
