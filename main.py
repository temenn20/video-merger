import os
import re
import subprocess
import requests
import cloudinary
import cloudinary.uploader
from flask import Flask, request, jsonify

app = Flask(__name__)

# Cloudinary Ayarları (Environment Variables üzerinden)
cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
    secure=True
)

def get_direct_drive_url(url):
    """Google Drive paylaşım linklerini otomatik olarak direkt indirme linkine çevirir."""
    file_id = None
    
    match_file = re.search(r'/file/d/([a-zA-Z0-9_-]+)', url)
    if match_file:
        file_id = match_file.group(1)
    else:
        match_id = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', url)
        if match_id:
            file_id = match_id.group(1)
            
    if file_id:
        return f"https://drive.google.com/uc?export=download&id={file_id}"
        
    return url

def download_file(url, output_path):
    """Google Drive ve normal HTTP linklerini arkadaşının confirm ve güvenlik kurallarıyla indiren fonksiyon"""
    actual_url = get_direct_drive_url(url)
    session = requests.Session()
    response = session.get(actual_url, stream=True)
    
    # 1. HTTP durum kodu kontrolü
    response.raise_for_status()
    
    # Google Drive büyük dosya virüs/onay uyarısı kontrolü
    for key, value in response.cookies.items():
        if key.startswith('download_warning'):
            confirmed_url = f"{actual_url}&confirm={value}"
            response = session.get(confirmed_url, stream=True)
            response.raise_for_status()
            break

    # 2. Dosya yerine HTML hata sayfası döndüyse engelle
    content_type = response.headers.get("Content-Type", "")
    if "text/html" in content_type:
        raise Exception("Google Drive veya sunucu dosya yerine HTML hata sayfası döndürdü (Erişim iznini kontrol et).")

    with open(output_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=32768):
            if chunk:
                f.write(chunk)

@app.route("/", methods=["GET"])
def home():
    return "Video Merger API is running!"

@app.route("/process", methods=["POST"])
def process_video():
    input_video = "/tmp/input_video.mp4"
    input_audio = "/tmp/input_audio.mp3"
    output_video = "/tmp/output_video.mp4"

    try:
        # Güvenli JSON verisi alma
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"status": "error", "message": "Geçersiz veya boş JSON verisi"}), 400

        video_url = data.get("video_url")
        audio_url = data.get("audio_url")

        if not video_url or not audio_url:
            return jsonify({"status": "error", "message": "video_url ve audio_url zorunludur"}), 400

        # Dosyaları güvenle indir
        download_file(video_url, input_video)
        download_file(audio_url, input_audio)

        # FFmpeg ile birleştirme ve detaylı stderr hata yakalama
        ffmpeg_cmd = [
    "ffmpeg", "-y",
    "-i", input_video,
    "-i", input_audio,
    "-c:v", "libx264",
    "-preset", "veryfast",
    "-c:a", "aac",
    "-shortest",
    output_video
]
        
        process = subprocess.run(
            ffmpeg_cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True
        )
        
        if process.returncode != 0:
            return jsonify({
                "status": "error", 
                "message": "FFmpeg execution failed", 
                "details": process.stderr
            }), 500

        # Çıktı dosyasının fiziksel olarak oluşup oluşmadığını kontrol et
        if not os.path.exists(output_video):
            raise Exception("FFmpeg çıktı videosunu oluşturamadı.")

        # Birleşen videoyu Cloudinary'ye yükle
        upload_result = cloudinary.uploader.upload(
            output_video,
            resource_type="video",
            folder="automated_videos"
        )
        
        cloudinary_video_url = upload_result.get("secure_url")

        # Cloudinary boş URL döndürürse hata fırlat
        if not cloudinary_video_url:
            raise Exception("Cloudinary video URL döndüremedi.")

        return jsonify({
            "status": "success",
            "video_url": cloudinary_video_url
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    finally:
        # Geçici dosyaları temizle
        for f in [input_video, input_audio, output_video]:
            if os.path.exists(f):
                os.remove(f)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
