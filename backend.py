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
import traceback
from colorthief import ColorThief

app = Flask(__name__)
CORS(app)

ytmusic = YTMusic()

BACKEND_URL = "https://backend-echo.onrender.com"
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
        final_results = []

        # SONGS
        songs = ytmusic.search(query, filter="songs", limit=10)
        for item in songs:
            if item.get('resultType') != 'song':
                continue
            final_results.append({
                'type': 'song',
                'title': item.get('title'),
                'album': item.get('album'),
                'artist': ', '.join([a['name'] for a in item.get('artists', [])]),
                'duration': item.get('duration'),
                'thumbnail': item.get('thumbnails', [{}])[-1].get('url', ''),
                'videoId': item.get('videoId'),
                'url': f"{BACKEND_URL}/download/{item.get('videoId')}.mp3"
            })

        # ALBUMS
        albums = ytmusic.search(query, filter="albums", limit=10)
        for item in albums:
            if item.get('resultType') != 'album':
                continue
            final_results.append({
                'type': 'album',
                'title': item.get('title'),
                'artist': ', '.join([a['name'] for a in item.get('artists', [])]),
                'browseId': item.get('browseId'),
                'thumbnail': item.get('thumbnails', [{}])[-1].get('url', '')
            })

        # PLAYLISTS
        playlists = ytmusic.search(query, filter="playlists", limit=10)
        for item in playlists:
            if item.get('resultType') != 'playlist':
                continue

            # Usa browseId invece di playlistId se manca
            playlist_id = item.get('playlistId') or item.get('browseId')
            if not playlist_id:
                continue

            final_results.append({
                'type': 'playlist',
                'title': item.get('title'),
                'author': item.get('author'),
                'playlistId': playlist_id,
                'thumbnail': item.get('thumbnails', [{}])[-1].get('url', '')
            })

        if not final_results:
            return jsonify({'error': 'Nessun risultato trovato'}), 404

        return jsonify(final_results)

    except Exception as e:
        print("Errore in /search:", str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/album/<album_id>')
def get_album_tracks(album_id):
    try:
        print(f"Ricevuto ID album: {album_id}")
        album_data = ytmusic.get_album(album_id)
        if not album_data:
            print("Album non trovato")
            return jsonify({'error': 'Album non trovato'}), 404

        tracks = album_data.get('tracks', [])
        if not tracks:
            print("Nessuna traccia trovata per l'album")
            return jsonify({'error': 'Nessuna traccia trovata per l\'album'}), 404

        print(f"Tracce trovate: {len(tracks)}")
        track_info = []
        for track in tracks:
            if not track or not track.get('videoId'):
                continue

            # Qui prendo la thumbnail specifica della traccia, se disponibile
            thumbnail_list = track.get("videoThumbnail", {}).get("thumbnails", [])
            if not thumbnail_list:
                # fallback se non c'è videoThumbnail
                thumbnail_list = track.get('thumbnails', [])
            thumbnail_url = thumbnail_list[-1]["url"] if thumbnail_list else ""

            proxied_thumbnail = f"{BACKEND_URL}/proxy-thumbnail?url={requests.utils.quote(thumbnail_url)}" if thumbnail_url else ''

            track_info.append({
                'title': track.get('title', ''),
                'artist': ', '.join([a['name'] for a in track.get('artists', [])]) if track.get('artists') else 'Sconosciuto',
                'thumbnail': proxied_thumbnail,
                'videoId': track.get('videoId'),
                'url': f"{BACKEND_URL}/download/{track.get('videoId')}.mp3"
            })

        return jsonify(track_info)

    except Exception as e:
        print(f"Errore nel recupero album: {str(e)}")
        return jsonify({'error': f"Errore nel recupero delle tracce: {str(e)}"}), 500

@app.route('/playlist/<playlist_id>')
def get_playlist_tracks(playlist_id):
    try:
        print(f"Richiesta playlist completa per ID: {playlist_id}")
        
        playlist_data = ytmusic.get_playlist(playlist_id, limit=100)
        all_tracks = playlist_data.get('tracks', [])
        total_tracks = playlist_data.get('trackCount', len(all_tracks))

        print(f"Tracce iniziali caricate: {len(all_tracks)} / Totali: {total_tracks}")

        # Continua a caricare se non le ha ancora tutte
        while len(all_tracks) < total_tracks:
            next_batch = ytmusic.get_playlist(playlist_id, limit=total_tracks)
            if not next_batch or not next_batch.get('tracks'):
                break
            all_tracks = next_batch['tracks']
            print(f"Tracce aggiornate: {len(all_tracks)}")

        if not all_tracks:
            return jsonify({'error': 'Nessuna traccia trovata'}), 404

        track_info = []
        for i, track in enumerate(all_tracks):
            print(f"Processo traccia {i + 1}/{len(all_tracks)}: {track.get('title', 'Sconosciuta')}")

            if not track:
                continue

            video_id = track.get('videoId')
            title = track.get('title')
            artists = track.get('artists')

            if not video_id or not title or not artists:
                continue

            thumbnail_list = track.get("thumbnails", [])
            thumbnail_url = thumbnail_list[-1]["url"] if thumbnail_list else ''
            proxied_thumbnail = f"{BACKEND_URL}/proxy-thumbnail?url={requests.utils.quote(thumbnail_url)}" if thumbnail_url else ''

            track_info.append({
                'title': title,
                'artist': ', '.join([a['name'] for a in artists]),
                'thumbnail': proxied_thumbnail,
                'videoId': video_id,
                'url': f"{BACKEND_URL}/download/{video_id}.mp3"
            })

        return jsonify(track_info)

    except Exception as e:
        print(f"❌ Errore nel recupero playlist: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': f"Errore nel recupero delle tracce: {str(e)}"}), 500

@app.route('/proxy-thumbnail')
def proxy_thumbnail():
    image_url = request.args.get('url')
    if not image_url:
        return jsonify({'error': 'URL mancante'}), 400

    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(image_url, headers=headers, stream=True, timeout=10)

        if response.status_code != 200:
            return jsonify({'error': 'Immagine non trovata'}), 404

        return Response(
            response.content,
            content_type=response.headers.get('Content-Type', 'image/jpeg')
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

            threading.Thread(target=delete_file_after_delay, args=(output_path, 1800)).start()

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

@app.route('/dominant-color')
def dominant_color():
    image_url = request.args.get('url')
    response = requests.get(image_url)
    color_thief = ColorThief(BytesIO(response.content))
    dominant_color = color_thief.get_color(quality=1)
    return jsonify({'color': dominant_color})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3001))
    app.run(host='0.0.0.0', port=port)
