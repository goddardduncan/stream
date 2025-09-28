import os
import pychromecast
import re
import json
import urllib.parse
import subprocess
import requests
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from collections import defaultdict

APP_ROOT = os.getcwd()
MEDIA_DIR = os.path.join(APP_ROOT, "media")
TV_DIR = os.path.join(MEDIA_DIR, "TV")
CACHE_FILE = os.path.join(APP_ROOT, "metadata_cache_tv.json")
PORT = 8030
CHROMECAST_NAME = "Living Room TV"
CATT_PATH = "/home/duncan/.local/bin/catt"
VIDEO_EXTENSIONS = (".mp4", ".mkv", ".avi", ".m4v")
OMDB_API_KEY = "98eb08a4"

tv_metadata = defaultdict(lambda: {"metadata": {}, "seasons": defaultdict(list)})
metadata_cache = {}

chromecast = None
media_controller = None
last_chromecast_failure = None

def clean_title(filename):
    filename = os.path.splitext(filename)[0]
    filename = re.sub(r'[\[\(].*?[\]\)]|\d{3,4}p|bluray|x264|dvdrip|hdtv|aac|mp3', '', filename, flags=re.IGNORECASE)
    filename = re.sub(r'\d{4}', '', filename)
    filename = re.sub(r'[\._\-]', ' ', filename)
    return filename.strip()

def fetch_show_info(title):
    url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&t={urllib.parse.quote(title)}&type=series"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("Response") == "True":
            return {
                "title": data.get("Title"),
                "poster": data.get("Poster"),
                "plot": data.get("Plot", "")
            }
    except Exception:
        pass
    return {
        "title": title,
        "poster": "https://via.placeholder.com/120x180?text=" + urllib.parse.quote(title),
        "plot": ""
    }

def load_tv_metadata():
    global metadata_cache
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f:
            metadata_cache = json.load(f)

    for show_name in sorted(os.listdir(TV_DIR)):
        show_path = os.path.join(TV_DIR, show_name)
        if not os.path.isdir(show_path):
            continue
        meta = metadata_cache.get(show_name) or fetch_show_info(show_name)
        metadata_cache[show_name] = meta
        for season in sorted(os.listdir(show_path)):
            season_path = os.path.join(show_path, season)
            if not os.path.isdir(season_path):
                continue
            def natural_key(s):
                return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

            episodes = [f for f in os.listdir(season_path) if f.lower().endswith(VIDEO_EXTENSIONS)]
            episodes.sort(key=natural_key)
            cleaned = [(os.path.splitext(ep)[0], os.path.join("TV", show_name, season, ep)) for ep in episodes]

            tv_metadata[show_name]["seasons"][season] = cleaned
        tv_metadata[show_name]["metadata"] = meta

    with open(CACHE_FILE, 'w') as f:
        json.dump(metadata_cache, f, indent=2)

def connect_chromecast():
    global chromecast, media_controller, last_chromecast_failure

    if chromecast and hasattr(chromecast, "media_controller"):
        return  # Already connected and valid

    try:
        print(f"🔍 Discovering Chromecast named '{CHROMECAST_NAME}'...")
        chromecasts, browser = pychromecast.get_listed_chromecasts(friendly_names=[CHROMECAST_NAME])
        if not chromecasts:
            raise Exception(f"Chromecast '{CHROMECAST_NAME}' not found.")

        chromecast = chromecasts[0]
        chromecast.wait()
        media_controller = chromecast.media_controller
        last_chromecast_failure = None
        print(f"✅ Connected to {CHROMECAST_NAME}")
    except Exception as e:
        chromecast = None
        media_controller = None
        last_chromecast_failure = str(e)
        print(f"❌ Connection failed: {e}")
        raise

class TVHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(generate_main_html().encode())

        elif parsed.path == "/overlay":
            show = params.get("show", [None])[0]
            if show and show in tv_metadata:
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(generate_overlay_html(show).encode())
            else:
                self.send_error(404)

        elif parsed.path == "/cast":
            file_param = params.get("file", [None])[0]
            if file_param:
                abs_path = os.path.abspath(os.path.join(MEDIA_DIR, urllib.parse.unquote(file_param)))
                try:
                    connect_chromecast()

                    def send_cast_response():
                        self.send_response(200)
                        self.send_header("Content-type", "text/html")
                        self.end_headers()
                        self.wfile.write(f"""
                        <html><head><title>Now Casting</title>
                        <style>
                        body {{ background: #111; color: white; font-family: sans-serif; text-align: center; padding: 5em; }}
                        h1 {{ color: hotpink; font-size: 28px; }}
                        a.button {{ display: inline-block; margin-top: 2em; padding: 0.5em 1em; background: hotpink; color: black; text-decoration: none; border-radius: 1em; font-size: 1em; }}
                        </style>
                        </head><body>
                        <h1>Now casting: {os.path.basename(abs_path)}</h1>
                        <a class='button' href='/'>Back</a>
                        <script>
                        document.addEventListener('keydown', e => {{
                            if (e.key.toLowerCase() === 'enter') {{
                                window.location = '/';
                            }}
                        }});
                        </script>
                        </body></html>""".encode())

                    def cast_now():
                        subprocess.Popen([CATT_PATH, "--device", CHROMECAST_NAME, "cast", abs_path])
                        send_cast_response()

                    try:
                        media_controller.update_status()
                        if media_controller.status.player_state in ("PLAYING", "PAUSED", "BUFFERING"):
                            print("⏹ Stopping current media first...")
                            media_controller.stop()
                            threading.Timer(1.0, cast_now).start()
                        else:
                            cast_now()
                    except Exception as stop_err:
                        print("⚠️ Could not update status or stop media:", stop_err)
                        cast_now()
                except Exception as e:
                    self.send_error(500, f"Casting failed: {e}")
            else:
                self.send_error(400, "Missing file param")
        
        else:
            super().do_GET() # Serve static files

def generate_main_html():
    ROWS = 2 # Change this value to adjust the number of rows
    COLS = 7
    html = f"""
    <html><head><title>TV shows</title>
    <style>
    body {{
        background: #111;
        color: #ccc;
        font-family: sans-serif;
    }}
    .container {{
        width: 100%;
        overflow-x: hidden;
        overflow-y: auto;
        padding: 1em;
    }}
    .row {{
        display: flex;
        gap: 1em;
        margin-bottom: 2em;
        padding-bottom: 0.5em;
    }}
    .movie {{
        flex: 0 0 auto;
        cursor: pointer;
        text-align: center;
        width: 120px;
        display: flex;
        flex-direction: column;
        align-items: center;
    }}
    .movie img {{
        width: 120px;
        height: 180px;
        object-fit: cover;
        border-radius: 8px;
    }}
    .meta {{
        margin-top: 1.5em;
        font-size: 0.9em;
        text-align: center;
        width: 100%;
        min-height: 3.5em;
        line-height: 1.2em;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #ccc;
        white-space: normal;
        overflow-wrap: break-word;
        overflow: hidden;
    }}
    .movie.selected img {{
        transform: scale(1.2);
        border: 2px solid hotpink;
    }}
    </style>
    </head><body>
    <h1 style='color:hotpink;'>TVini for a Petrini</h1>
    <div class='container' id='container'>
    """
    
    shows = list(tv_metadata.items())
    num_shows = len(shows)
    
    for i in range(0, num_shows, COLS):
        html += "<div class='row'>"
        for j in range(COLS):
            idx = i + j
            if idx < num_shows:
                show, data = shows[idx]
                safe = show.replace("'", "\\'")
                poster = data["metadata"].get("poster") or "https://via.placeholder.com/120x180"
                title = data["metadata"].get("title", show)
                html += f"<div class='movie' data-index='{idx}' onclick=\"openOverlay('{safe}')\"><img src='{poster}' alt='{title}'><div class='meta'><strong>{title}</strong></div></div>"
        html += "</div>"

    html += f"""
    </div>
    <script>
    const COLS = {COLS};
    let index = 0;
    let movies = document.querySelectorAll('.movie');
    const numRows = Math.ceil(movies.length / COLS);
    
    function highlight() {{
        movies.forEach(m => m.classList.remove('selected'));
        if (movies[index]) {{
            movies[index].classList.add('selected');
            movies[index].scrollIntoView({{ behavior: 'smooth', inline: 'center', block: 'center' }});
        }}
    }}
    
    document.addEventListener('keydown', e => {{
        const key = e.key.toLowerCase();
        let newIndex = index;

        if (key === 'arrowright') {{
            newIndex = (index + 1) % movies.length;
        }} else if (key === 'arrowleft') {{
            newIndex = (index - 1 + movies.length) % movies.length;
        }} else if (key === 'arrowdown') {{
            newIndex = (index + COLS);
            if (newIndex >= movies.length) {{
                newIndex = index;
            }}
        }} else if (key === 'arrowup') {{
            newIndex = (index - COLS);
            if (newIndex < 0) {{
                newIndex = index;
            }}
        }} else if (key === 'enter') {{
            if (movies[index]) {{
                movies[index].click();
            }}
            return;
        }} else if (key === 'contextmenu') {{
            fetch('/playpause');
            return;
        }}
        
        index = newIndex;
        highlight();
    }});
    
    highlight();
    function openOverlay(show) {{ window.location = `/overlay?show=${{encodeURIComponent(show)}}`; }}
    </script>
    </body></html>
    """
    return html

def generate_overlay_html(show):
    meta = tv_metadata[show]["metadata"]
    html = f"""
    <html><head><title>{meta['title']}</title>
    <style>
    body {{ background: black; color: white; font-family: sans-serif; font-size: 20px; }}
    h1 {{ color: hotpink; font-size: 56px; }}
    h2 {{ color: #6cf; font-size: 20px; }}
    .plot {{ color: #aaa; font-size: 16px; margin-bottom: 1em; max-width: 80ch; }}
    .episode {{ font-size: 18px; margin: 0.4em 0; cursor: pointer; }}
    .episode.selected {{ font-size: 20px; font-weight: bold; color: violet; }}
    .banner {{ position: absolute; top: 1em; right: 10em; width: 140px; }}
    .banner img {{ width: 100%; border-radius: 8px; }}
    </style>
    </head><body>
    <div class='banner'><img src='{meta['poster']}' alt='Poster'></div>
    <h1>{meta['title']}</h1>
    <div class='plot'>{meta['plot']}</div>
    """
    all_eps = []
    for season, eps in tv_metadata[show]["seasons"].items():
        html += f"<h2><b>{season}</b></h2>"
        for title, path in eps:
            all_eps.append((title, path))
            html += f"<div class='episode' data-path='{urllib.parse.quote(path)}'>{title}</div>"

    html += """
    <script>
        window.onload = function () {
            let items = Array.from(document.querySelectorAll('.episode'));
            let index = 0;
            function highlight() {
                items.forEach(e => e.classList.remove('selected'));
                items[index].classList.add('selected');
                items[index].scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
            document.addEventListener('keydown', e => {
                const key = e.key.toLowerCase();
                if (key === 'arrowdown') { index = (index + 1) % items.length; highlight(); }
                else if (key === 'arrowup') {
                    if (index === 0) {
                        // Do nothing or wrap around
                    } else {
                        index = (index - 1 + items.length) % items.length;
                        highlight();
                    }
                }
                else if (key === 'enter') {
                    const path = items[index].dataset.path;
                    window.location = `/cast?file=${encodeURIComponent(path)}`;
                } else if (key === 'arrowleft') { window.location = '/'; }
            });
            highlight();

            // Enable mouse click to cast
            items.forEach((item, idx) => {
                item.addEventListener('click', () => {
                    const path = item.dataset.path;
                    window.location = `/cast?file=${encodeURIComponent(path)}`;
                });
                item.addEventListener('mouseover', () => {
                    index = idx;
                    highlight();
                });
            });
        }
    </script>
</body></html>
    """
    return html

if __name__ == "__main__":
    load_tv_metadata()
    os.chdir(APP_ROOT)
    print(f"\U0001F4FA Serving on http://0.0.0.0:{PORT}/")
    HTTPServer(("0.0.0.0", PORT), TVHandler).serve_forever()
