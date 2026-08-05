import os
import re
import uuid
import subprocess
import requests
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

UPLOAD_FOLDER = '/tmp'

def extract_drive_id(url_or_id):
    """Gelen WebViewLink, WebContentLink veya File ID içerisinden saf ID'yi çeker."""
    if not url_or_id:
        return None
    # Eğer gelen veri direkt bir Drive URL'si ise ID'yi regex ile yakala
    match = re.search(r'/d/([a-zA-Z0-9_-]+)', url_or_id)
    if match:
        return match.group(1)
    # URL parametresi olarak 'id=' şeklinde geldiyse
    match_id = re.search(r'id=([a-zA-Z0-9_-]+)', url_or_id)
    if match_id:
        return match_id.group(1)
    # Zaten ham ID olarak geldiyse direkt kendisini dön
    return url_or_id

def download_file(video_param, destination):
    """Google Drive engellerini aşarak videoyu sunucuya indirir."""
    file_id = extract_drive_id(video_param)
    if not file_id:
        return False
        
    # Doğrudan indirme bağlantısını oluşturuyoruz
    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    
    session = requests.Session()
    response = session.get(download_url, stream=True)
    
    # Büyük dosyalar için Google Drive onay mekanizmasını geçme
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
        # 1. Google Drive Linki veya ID'sini al (WebViewLink dahil)
        video_url = request.form.get('video_url') or request.args.get('video_url')
        if not video_url and request.is_json:
            video_url = request.json.get('video_url')

        if not video_url:
            return jsonify({"status": "error", "message": "video_url parametresi bulunamadı!"}), 400

        print(f"[{session_id}] Video indirme başlatıldı: {video_url}")
        if not download_file(video_url, video_path):
            return jsonify({"status": "error", "message": "Video Google Drive'dan indirilemedi. Linki veya ID'yi kontrol edin."}), 500

        # 2. ElevenLabs'ten gelen Data (Binary) verisini al
        if request.data:
            with open(audio_path, 'wb') as f:
                f.write(request.data)
            print(f"[{session_id}] Ses (Data) basarıyla alındı ve kaydedildi.")
        elif 'audio_file' in request.files:
            file = request.files['audio_file']
            file.save(audio_path)
            print(f"[{session_id}] Ses dosyası multipart olarak alındı.")
        else:
            return jsonify({"status": "error", "message": "ElevenLabs audio Data verisi ulasmadı!"}), 400

        # 3. FFmpeg ile Birleştirme
        print(f"[{session_id}] FFmpeg çalıştırılıyor...")
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-i', audio_path,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-map', '0:v:0',
            '-map', '1:a:0',
            '-shortest',
            output_path
        ]

        result = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if result.returncode != 0:
            print(f"[{session_id}] FFmpeg Hata Detayı:\n{result.stderr}")
            return jsonify({"status": "error", "message": "FFmpeg hatası", "details": result.stderr}), 500

        print(f"[{session_id}] Başarılı! Video gönderiliyor.")
        return send_file(output_path, mimetype='video/mp4', as_attachment=True, download_name='final_video.mp4')

    except Exception as e:
        print(f"[{session_id}] Sunucu İçi Hata: {str(e)}")
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
