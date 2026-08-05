import os
import re
import requests
from flask import Flask, request, jsonify, send_file
import subprocess

app = Flask(__name__)

def get_direct_drive_url(url):
    """
    Google Drive paylaşım linkinden dosya ID'sini çıkarır ve
    doğrudan indirme URL'sine dönüştürür.
    """
    drive_id_match = re.search(r'(?:/d/|id=)([\w-]+)', url)
    if drive_id_match:
        file_id = drive_id_match.group(1)
        return f"https://drive.google.com/uc?export=download&confirm=t&id={file_id}"
    return url

def download_file(url, destination):
    """
    Verilen URL'yi saf dosya içeriği olarak belirtilen konuma indirir.
    HTML web sayfası engeline takılırsa tespit eder.
    """
    direct_url = get_direct_drive_url(url)
    session = requests.Session()
    response = session.get(direct_url, stream=True)
    
    # Drive güvenlik uyarısı verirse çerezlerle onaylayıp devam et
    for key, value in response.cookies.items():
        if key.startswith('download_warning'):
            direct_url = f"{direct_url}&confirm={value}"
            response = session.get(direct_url, stream=True)
            break
            
    # ARKADAŞININ DEDİĞİ KRİTİK KONTROL:
    content_type = response.headers.get("Content-Type", "")
    if "text/html" in content_type:
        raise Exception("Google Drive dosya yerine HTML onay sayfası döndürdü. Lütfen Drive dosya izinlerinin 'Bağlantıya sahip herkes' olarak ayarlandığından emin olun.")

    if response.status_code == 200:
        with open(destination, 'wb') as f:
            for chunk in response.iter_content(chunk_size=32768):
                if chunk:
                    f.write(chunk)
    else:
        raise Exception(f"Dosya indirilemedi. HTTP Kodu: {response.status_code}")

@app.route('/process', methods=['POST'])
def process_video():
    try:
        data = request.get_json()
        video_url = data.get('video_url')
        audio_url = data.get('audio_url')

        if not video_url or not audio_url:
            return jsonify({"status": "error", "message": "video_url veya audio_url eksik"}), 400

        input_video_path = "/tmp/input_video.mp4"
        input_audio_path = "/tmp/input_audio.mp3"
        output_video_path = "/tmp/output_video.mp4"

        # Dosyaları güvenli indirme fonksiyonu ile indir
        download_file(video_url, input_video_path)
        download_file(audio_url, input_audio_path)

        # FFmpeg ile video ve sesi birleştir
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-i', input_video_path,
            '-i', input_audio_path,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-map', '0:v:0',
            '-map', '1:a:0',
            '-shortest',
            output_video_path
        ]

        result = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if result.returncode != 0:
            return jsonify({"status": "error", "message": f"FFmpeg hatası:\n{result.stderr}"}), 500

        # Çıktı dosyası kontrolü
        if not os.path.exists(output_video_path):
            raise Exception("FFmpeg tamamlandı ancak çıktı videosu diske yazılamadı.")

        # Videoyu Make'e gönder
        return send_file(
            output_video_path,
            mimetype='video/mp4',
            as_attachment=True,
            download_name='output_video.mp4'
        )

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
