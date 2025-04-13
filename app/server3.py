import os
import re
import json
import shutil
import time
import threading
import urllib.parse
import subprocess
from http.server import HTTPServer, SimpleHTTPRequestHandler
from collections import defaultdict
import mimetypes
import requests

APP_ROOT = os.getcwd()
MEDIA_DIR = os.path.join(APP_ROOT, "media")
TMP_HLS_DIR = os.path.join(APP_ROOT, "tmp_hls")
CACHE_FILE = os.path.join(APP_ROOT, "metadata_cache.json")

PORT = 8050
OMDB_API_KEY = "98eb08a4"
VIDEO_EXTENSIONS = (".mp4", ".mkv", ".avi", ".m4v")

movie_metadata = defaultdict(dict)
metadata_cache = {}
hls_last_access = {}
HLS_EXPIRATION_SECONDS = 30000

mimetypes.add_type('application/vnd.apple.mpegurl', '.m3u8')
mimetypes.add_type('video/MP2T', '.ts')

def clean_title(filename):
    filename = os.path.splitext(filename)[0]
    filename = re.sub(r'[\[\(].*?[\]\)]|\d{3,4}p|bluray|x264|dvdrip|hdtv|aac|mp3', '', filename, flags=re.IGNORECASE)
    filename = re.sub(r'\d{4}', '', filename)
    filename = re.sub(r'[\._\-]', ' ', filename)
    return filename.strip()

def fetch_movie_info(title):
    if title in metadata_cache:
        return metadata_cache[title]
    url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&t={urllib.parse.quote(title)}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("Response") == "True":
            info = {
                "Title": data.get("Title"),
                "Year": data.get("Year"),
                "IMDb Rating": data.get("imdbRating"),
                "Plot": data.get("Plot"),
                "Poster": data.get("Poster"),
            }
            metadata_cache[title] = info
            return info
    except: pass
    return None

def load_metadata():
    global metadata_cache
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                metadata_cache = json.load(f)
        except: pass
    for root, _, files in os.walk(MEDIA_DIR):
        folder = os.path.relpath(root, MEDIA_DIR)
        if folder.lower() == "survivor":
            continue  # Skip survivor folder in OMDb scan
        for file in sorted(files):
            if file.lower().endswith(VIDEO_EXTENSIONS):
                title = clean_title(file)
                if file not in movie_metadata[folder]:
                    info = fetch_movie_info(title)
                    if info:
                        movie_metadata[folder][file] = info
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(metadata_cache, f, indent=2)
    except: pass

def hls_ready(file_param):
    base_name = re.sub(r'[^\w\-]', '_', file_param)
    hls_dir = os.path.join(TMP_HLS_DIR, base_name)
    return os.path.exists(os.path.join(hls_dir, "playlist.m3u8"))

def generate_hls(input_path, hls_dir):
    os.makedirs(hls_dir, exist_ok=True)
    output_path = os.path.join(hls_dir, "playlist.m3u8")
    if os.path.exists(output_path):
        return
    base_url = f"/tmp_hls/{os.path.basename(hls_dir)}/"
    ffmpeg = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
    cmd = [
        ffmpeg, "-i", input_path, "-codec:", "copy", "-start_number", "0",
        "-hls_time", "10", "-hls_list_size", "0",
        "-hls_segment_filename", os.path.join(hls_dir, "playlist%d.ts"),
        "-hls_base_url", base_url, "-f", "hls", output_path
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except: pass

def cleanup_old_hls():
    while True:
        time.sleep(60)
        now = time.time()
        for folder in list(hls_last_access.keys()):
            if now - hls_last_access[folder] > HLS_EXPIRATION_SECONDS:
                shutil.rmtree(os.path.join(TMP_HLS_DIR, folder), ignore_errors=True)
                hls_last_access.pop(folder)

class HLSHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/hls_status":
            file_param = params.get("file", [None])[0]
            if file_param:
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                ready = hls_ready(file_param)
                self.wfile.write(json.dumps({"ready": ready}).encode())
            return

        elif parsed.path.startswith("/hls/playlist.m3u8"):
            file_param = params.get("file", [None])[0]
            if file_param:
                src_path = os.path.abspath(os.path.join(MEDIA_DIR, urllib.parse.unquote(file_param)))
                if os.path.exists(src_path):
                    base_name = re.sub(r'[^\w\-]', '_', file_param)
                    hls_dir = os.path.join(TMP_HLS_DIR, base_name)
                    generate_hls(src_path, hls_dir)
                    hls_last_access[base_name] = time.time()
                    self.path = f"/tmp_hls/{base_name}/playlist.m3u8"
                    return SimpleHTTPRequestHandler.do_GET(self)
            self.send_error(404)

        elif parsed.path.startswith("/tmp_hls/"):
            match = re.match(r"/tmp_hls/([^/]+)/", parsed.path)
            if match:
                hls_last_access[match.group(1)] = time.time()
            return SimpleHTTPRequestHandler.do_GET(self)

        elif parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(generate_html().encode())

        else:
            return SimpleHTTPRequestHandler.do_GET(self)

def generate_html():
    def movie_div(path, poster, title, show_imdb=False, imdb=""):
        return f'''
        <div class="movie" data-path="{path}" onclick="handleClick(this)">
            <div class="flag"></div>
            <img src="{poster}" alt="{title}">
            <div class="meta"><strong>{title}</strong>{'<br>IMDB ' + imdb if show_imdb else ''}</div>
        </div>'''

    # Survivor Row
    survivor_folder = os.path.join(MEDIA_DIR, "survivor")
    survivor_row = ""
    if os.path.isdir(survivor_folder):
        files = [f for f in sorted(os.listdir(survivor_folder)) if f.lower().endswith(VIDEO_EXTENSIONS)]
        row = ""
        for filename in files:
            title = os.path.splitext(filename)[0]
            rel_path = urllib.parse.quote(os.path.join("survivor", filename))
            row += movie_div(rel_path, "reel.png", title)
        if row:
            survivor_row = f"<h2>Saves</h2><div class='banner'>{row}</div>"

    # Standard Movies
    standard_rows = ""
    for folder in sorted(k for k in movie_metadata if k != "survivor"):
        movies = movie_metadata[folder]
        row = ""
        for filename, meta in movies.items():
            rel_path = urllib.parse.quote(os.path.join(folder, filename))
            row += movie_div(rel_path, meta['Poster'], meta['Title'], show_imdb=True, imdb=meta['IMDb Rating'])
        if row:
            standard_rows += f"<h2>{folder}</h2><div class='banner'>{row}</div>"

    return f"""
    <html>
    <head>
        <title>Movie Streamer</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
        <style>
            body {{ background: #111; color: #eee; font-family: sans-serif; padding: 2vw; }}
            h1 {{ color: hotpink; }}
            h2 {{ color: #6cf; }}
            .banner {{ display: flex; overflow-x: auto; gap: 20px; padding: 1vw; }}
            .movie {{
                position: relative;
                flex: 0 0 auto;
                width: 160px;
                text-align: center;
                cursor: pointer;
            }}
            .movie img {{
                width: 100%;
                border-radius: 1em;
                box-shadow: 0 0 10px #000;
                transition: transform 0.2s ease;
            }}
            .movie:hover img {{ transform: scale(1.05); }}
            .meta {{ font-size: 0.9em; color: #ccc; margin-top: 0.5em; }}
            .flag {{
                position: absolute;
                top: 5px;
                right: 5px;
                width: 24px;
                height: 24px;
                background-size: cover;
                color: white;
                font-size: 18px;
                text-shadow: 0 0 4px black;
            }}
            video {{
                width: 100%;
                max-height: 60vh;
                margin-top: 2vw;
                border-radius: 1em;
                box-shadow: 0 0 15px #000;
            }}
        </style>
    </head>
    <body>
        <h1>Stream for my love</h1>
        <video id="player" controls playsinline preload="metadata" crossorigin="anonymous"></video>
        
        {standard_rows}
	{survivor_row}
        <script>
            const statuses = {{}};
            const pollingInterval = 15000;

            function checkReady(el, path) {{
                fetch(`/hls_status?file=${{path}}`)
                    .then(r => r.json())
                    .then(data => {{
                        const flag = el.querySelector('.flag');
                        if (data.ready) {{
                            statuses[path] = 'ready';
                            flag.textContent = '';
                            flag.style.backgroundImage = "url('/green-flag.png')";
                        }}
                    }});
            }}

            function pollStatuses() {{
                document.querySelectorAll('.movie').forEach(el => {{
                    const path = el.dataset.path;
                    if (statuses[path] === 'queued') {{
                        checkReady(el, path);
                    }}
                }});
            }}

            function handleClick(el) {{
                const path = el.dataset.path;
                const flag = el.querySelector('.flag');
                flag.textContent = '';
                const status = statuses[path];
                const video = document.getElementById("player");

                if (status === 'ready') {{
                    const url = `/hls/playlist.m3u8?file=${{path}}`;
                    if (Hls.isSupported()) {{
                        const hls = new Hls();
                        hls.loadSource(url);
                        hls.attachMedia(video);
                        hls.on(Hls.Events.MANIFEST_PARSED, () => video.play());
                    }} else {{
                        video.src = url;
                        video.onloadedmetadata = () => video.play();
                    }}
                }} else if (!status) {{
                    checkReady(el, path);
                    fetch(`/hls_status?file=${{path}}`)
                        .then(res => res.json())
                        .then(data => {{
                            if (data.ready) {{
                                statuses[path] = 'ready';
                                flag.textContent = '';
                                flag.style.backgroundImage = "url('/green-flag.png')";
                                return;
                            }}
                            statuses[path] = 'queued';
                            flag.style.backgroundImage = "url('/purple-flag.png')";
                            fetch(`/hls/playlist.m3u8?file=${{path}}`);
                            let dotCount = 0;
                            const dots = [".", "..", "..."];
                            const interval = setInterval(() => {{
                                if (statuses[path] === 'ready') return clearInterval(interval);
                                flag.style.backgroundImage = "url('/purple-flag.png')";
                                flag.textContent = dots[dotCount++ % dots.length];
                            }}, 500);
                        }});
                }}
            }}

            window.onload = () => {{
                document.querySelectorAll('.movie').forEach(el => {{
                    const path = el.dataset.path;
                    statuses[path] = null;
                    checkReady(el, path);
                }});
                setInterval(pollStatuses, pollingInterval);
            }};
        </script>
        <div style="position: fixed; bottom: 20px; right: 20px;">
		  <a href="http://100.107.223.221:8000/" title="Cast to TV">
    		<svg xmlns="http://www.w3.org/2000/svg" height="36" width="36" viewBox="0 0 24 24" fill="#ccc">
      		<path d="M1 18v3h3c0-1.66-1.34-3-3-3zm0-3v2c2.76 0 5 2.24 5 5h2c0-3.86-3.14-7-7-7zm0-3v2c4.97 0 9 4.03 9 9h2c0-6.08-4.93-11-11-11zM21 3H3c-1.1 0-2 .9-2 2v4h2V5h18v14h-8v2h8c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2z"/>
    		</svg>
  		</a>
	   </div>
    </body>
    </html>
    """

if __name__ == "__main__":
    if os.path.exists(TMP_HLS_DIR):
        shutil.rmtree(TMP_HLS_DIR)
    os.makedirs(TMP_HLS_DIR, exist_ok=True)
    load_metadata()
    threading.Thread(target=cleanup_old_hls, daemon=True).start()
    os.chdir(APP_ROOT)
    print(f"🎬 Serving on http://0.0.0.0:{PORT}/")
    HTTPServer(("0.0.0.0", PORT), HLSHandler).serve_forever()
