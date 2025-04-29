import os
import re
import time
import threading
import requests
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from ytmusicapi import YTMusic
from yt_dlp import YoutubeDL
from io import BytesIO

app = Flask(__name__)
CORS(app)

ytmusic = YTMusic()

DOWNLOAD_FOLDER = os.path.join(os.getcwd(), "static")
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)


def delete_file_after_delay(file_path, delay_seconds):
    time.sleep(delay_seconds)
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"File eliminato: {file_path}")
    except Exception as e:
        print(f"Errore durante l'eliminazione di {file_path}: {e}")


@app.route('/search')
def search():
    query = request.args.get('q')
    if not query:
        return jsonify({'error': 'Nessuna query'}), 400

    try:
        search_results = ytmusic.search(query, filter='songs', limit=10)
        if not search_results:
            return jsonify({'error': 'Nessun risultato trovato'}), 404

        results = []
        for item in search_results:
            video_id = item.get('videoId')
            if not video_id:
                continue

            raw_thumb = item.get('thumbnails', [{}])[-1].get('url', '')
            thumb_proxy = raw_thumb

            mp3_url = f"http://localhost:3001/download/{video_id}.mp3"

            results.append({
                'title': item.get('title'),
                'artist': ', '.join([a['name'] for a in item.get('artists', [])]),
                'duration': item.get('duration'),
                'thumbnail': thumb_proxy,
                'videoId': video_id,
                'url': mp3_url
            })

        return jsonify(results)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/proxy-thumbnail')
def proxy_thumbnail():
    image_url = request.args.get('url')
    if not image_url:
        return jsonify({'error': 'URL mancante'}), 400

    try:
        response = requests.get(image_url, stream=True, timeout=5)
        if response.status_code != 200:
            return jsonify({'error': 'Immagine non trovata'}), 404

        return Response(
            response.content,
            content_type=response.headers['Content-Type']
        )

    except Exception as e:
        return jsonify({'error': f'Errore nel proxy: {str(e)}'}), 500


@app.route('/download/<video_id>.mp3')
def download_mp3(video_id):
    output_path = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.mp3")

    if not os.path.exists(output_path):
        try:
            ydl_opts = {
                'format': 'bestaudio/best',
                'quiet': True,
                'noplaylist': True,
                'outtmpl': os.path.join(DOWNLOAD_FOLDER, f'{video_id}.%(ext)s'),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }

            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([f'https://www.youtube.com/watch?v={video_id}'])

            # Avvia un thread per eliminare il file dopo 24 ore 
            threading.Thread(target=delete_file_after_delay, args=(output_path, 3600)).start()

        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return stream_audio(output_path)


def stream_audio(path):
    range_header = request.headers.get('Range', None)
    if not os.path.exists(path):
        return jsonify({'error': 'File non trovato'}), 404

    file_size = os.path.getsize(path)
    byte1, byte2 = 0, None

    if range_header:
        match = re.search(r'bytes=(\d+)-(\d*)', range_header)
        if match:
            byte1 = int(match.group(1))
            if match.group(2):
                byte2 = int(match.group(2))

    byte2 = byte2 or file_size - 1
    length = byte2 - byte1 + 1

    with open(path, 'rb') as f:
        f.seek(byte1)
        data = f.read(length)

    rv = Response(data, 206, mimetype='audio/mpeg', direct_passthrough=True)
    rv.headers.add('Content-Range', f'bytes {byte1}-{byte2}/{file_size}')
    rv.headers.add('Accept-Ranges', 'bytes')
    rv.headers.add('Content-Length', str(length))
    return rv


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3001)
