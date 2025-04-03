from http.server import HTTPServer, SimpleHTTPRequestHandler
import os
import re
import urllib.parse
import requests
import subprocess
import json
from collections import defaultdict

# === CONFIG ===
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(APP_ROOT, "media")
CACHE_FILE = os.path.join(APP_ROOT, "metadata_cache.json")
PI_IP = "192.168.68.71"
PORT = 8000
CHROMECAST_NAME = "Living Room TV"
OMDB_API_KEY = "98eb08a4"
VIDEO_EXTENSIONS = (".mp4", ".mkv", ".avi", ".m4v")
CATT_PATH = "/home/duncan/.local/bin/catt"  # Adjust this if different

# === METADATA CACHE ===
movie_metadata = defaultdict(dict)
metadata_cache = {}

def clean_title(filename):
    filename = os.path.splitext(filename)[0]
    filename = re.sub(r'\[.*?\]|\(.*?\)|\d{3,4}p|bluray|x264|dvdrip|hdtv|aac|mp3', '', filename, flags=re.IGNORECASE)
    filename = re.sub(r'\d{4}', '', filename)
    filename = re.sub(r'[\._\-]', ' ', filename)
    return filename.strip()

def fetch_movie_info(title):
    if title in metadata_cache:
        return metadata_cache[title]
    url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&t={urllib.parse.quote(title)}"
    try:
        r = requests.get(url)
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
    except Exception as e:
        print("Fetch error:", e)
    return None

def load_metadata():
    global metadata_cache
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f:
            metadata_cache = json.load(f)

    for root, _, files in os.walk(MEDIA_DIR):
        folder = os.path.relpath(root, MEDIA_DIR)
        for file in files:
            if file.lower().endswith(VIDEO_EXTENSIONS):
                title = clean_title(file)
                if file not in movie_metadata[folder]:
                    info = fetch_movie_info(title)
                    if info:
                        movie_metadata[folder][file] = info

    with open(CACHE_FILE, 'w') as f:
        json.dump(metadata_cache, f, indent=2)

class BannerHandler(SimpleHTTPRequestHandler):
    def get_head(self, title="Movie Caster"):
        return f"""
        <head>
            <title>{title}</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{
                    background: #111;
                    color: #eee;
                    font-family: 'Segoe UI', 'Helvetica Neue', sans-serif;
                    margin: 0;
                    padding: 0;
                }}
                h1 {{
                    color: hotpink;
                    text-align: center;
                    margin: 2vw;
                }}
                h2 {{
                    color: #6cf;
                    margin: 1vw 2vw 0.5vw;
                }}
                .banner {{
                    display: flex;
                    overflow-x: auto;
                    gap: 20px;
                    padding: 2vw;
                    scroll-behavior: smooth;
                }}
                .movie {{
                    flex: 0 0 auto;
                    width: 160px;
                    text-align: center;
                    position: relative;
                }}
                .movie img {{
                    width: 100%;
                    border-radius: 1em;
                    box-shadow: 0 0 10px #000;
                    transition: transform 0.2s ease;
                }}
                .movie:hover img {{
                    transform: scale(1.05);
                }}
                .plot-overlay {{
                    display: none;
                    position: absolute;
                    top: 0;
                    left: 170px;
                    width: 280px;
                    background: rgba(0, 0, 0, 0.85);
                    color: #ccc;
                    font-size: 0.9em;
                    padding: 1em;
                    border-radius: 1em;
                    text-align: left;
                    z-index: 10;
                }}
                .movie:hover .plot-overlay {{
                    display: block;
                }}
                .meta {{
                    font-size: 0.9em;
                    color: #ccc;
                    margin-top: 0.5em;
                }}
                .button {{
                    display: inline-block;
                    margin: 2vw;
                    padding: 1vw 2vw;
                    background: hotpink;
                    color: black;
                    font-weight: bold;
                    text-decoration: none;
                    border-radius: 1em;
                    font-size: 1em;
                }}
                a {{
                    text-decoration: none;
                    color: inherit;
                }}
            </style>
        </head>
        """

    def send_pretty_page(self, title, message):
        html = f"""
        <html>
        {self.get_head(title)}
        <body>
        <h1>{message}</h1>
        <div style="text-align:center;">
            <a class="button" href="/">Go Back</a>
        </div>
        </body>
        </html>
        """
        self.wfile.write(html.encode())

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()

            rows_html = ""
            for folder, movies in movie_metadata.items():
                banner_items = ""
                for filename, meta in movies.items():
                    if meta.get("Poster") == "N/A":
                        continue
                    rel_path = os.path.join(folder, filename)
                    plot = meta['Plot'].replace('"', '&quot;')
                    banner_items += f"""
                    <div class="movie">
                        <a href="/cast?file={urllib.parse.quote(rel_path)}">
                            <img src="{meta['Poster']}" alt="{meta['Title']}">
                        </a>
                        <div class="plot-overlay">{plot}</div>
                        <div class="meta">
                            <strong>{meta['Title']}</strong><br>
                            IMDB {meta['IMDb Rating']}
                        </div>
                    </div>
                    """
                if banner_items:
                    rows_html += f"<h2>{folder}</h2><div class='banner'>{banner_items}</div>"

            html = f"""
            <html>
            {self.get_head()}
            <body>
                <h1>This is for my love whom I love</h1>
                {rows_html}
                <div style="text-align:center;">
                    <a class="button" href="/stop">Stop Cast</a>
                    <a class="button" href="/playpause">Play/Pause</a>
                </div>
            </body>
            </html>
            """
            self.wfile.write(html.encode())

        elif parsed.path == "/cast":
            filename = params.get("file", [None])[0]
            if filename:
                full_path = os.path.abspath(os.path.join(MEDIA_DIR, filename))
                try:
                    subprocess.Popen([CATT_PATH, "--device", CHROMECAST_NAME, "cast", full_path])
                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    self.send_pretty_page("Casting", f"Now casting: {filename}")
                except Exception as e:
                    self.send_error(500, f"Casting error: {str(e)}")
            else:
                self.send_error(400, "Missing file parameter")

        elif parsed.path == "/stop":
            subprocess.run([CATT_PATH, "--device", CHROMECAST_NAME, "stop"])
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.send_pretty_page("Stopped", "Stopped casting.")

        elif parsed.path == "/playpause":
            subprocess.run([CATT_PATH, "--device", CHROMECAST_NAME, "play_toggle"])
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.send_pretty_page("Toggled", "Playback toggled.")

        else:
            self.send_error(404, "Not found")

# === RUN SERVER ===
if __name__ == "__main__":
    load_metadata()
    server_address = (PI_IP, PORT)
    print(f"🎬 Serving on http://{PI_IP}:{PORT}/")
    HTTPServer(server_address, BannerHandler).serve_forever()
