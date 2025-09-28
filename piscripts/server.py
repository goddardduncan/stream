
from http.server import HTTPServer, SimpleHTTPRequestHandler
import os
import re
import urllib.parse
import requests
import subprocess
import json
import threading
from collections import defaultdict
import pychromecast

# === CONFIG ===
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(APP_ROOT, "media")
CACHE_FILE = os.path.join(APP_ROOT, "metadata_cache.json")
PI_IP = "0.0.0.0"  # Replace with LAN IP if needed
PORT = 8000
CHROMECAST_NAME = "Living Room TV"
CHROMECAST_IP = "192.168.68.57"
OMDB_API_KEY = "98eb08a4"
VIDEO_EXTENSIONS = (".mp4", ".mkv", ".avi", ".m4v")
CATT_PATH = "/home/duncan/.local/bin/catt"

last_known_duration = {"value": 0}
movie_metadata = defaultdict(dict)
metadata_cache = {}
autoplay_enabled = False
last_cast = {"folder": None, "file": None}

chromecast = None
media_controller = None


def clean_title(filename):
    filename = os.path.splitext(filename)[0]
    filename = re.sub(
        r"\[.*?\]|\(.*?\)|\d{3,4}p|bluray|x264|dvdrip|hdtv|aac|mp3",
        "",
        filename,
        flags=re.IGNORECASE,
    )
    filename = re.sub(r"\d{4}", "", filename)
    filename = re.sub(r"[\._\-]", " ", filename)
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
        with open(CACHE_FILE, "r") as f:
            metadata_cache = json.load(f)
    for root, _, files in os.walk(MEDIA_DIR):
        folder = os.path.relpath(root, MEDIA_DIR)
        # 🛑 Skip 'TV' folders and any subfolders
        if "TV" in folder.split(os.sep):
            continue
        for file in sorted(files):
            if file.lower().endswith(VIDEO_EXTENSIONS):
                title = clean_title(file)
                if file not in movie_metadata[folder]:
                    if folder == "survivor":
                        movie_metadata[folder][file] = {}
                    else:
                        info = fetch_movie_info(title)
                        if info:
                            movie_metadata[folder][file] = info
    with open(CACHE_FILE, "w") as f:
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


def schedule_next_episode(folder, current_file):
    if not autoplay_enabled:
        return
    file_list = sorted(movie_metadata.get(folder, {}).keys())
    try:
        idx = file_list.index(current_file)
        next_file = file_list[idx + 1]
    except (ValueError, IndexError):
        return
    full_path = os.path.abspath(os.path.join(MEDIA_DIR, folder, next_file))
    def delayed_cast():
        subprocess.Popen([CATT_PATH, "--device", CHROMECAST_NAME, "cast", full_path])
        last_cast["folder"] = folder
        last_cast["file"] = next_file
    threading.Timer(20, delayed_cast).start()

class BannerHandler(SimpleHTTPRequestHandler):
    def get_head(self, title="Movie Caster"):
        return f"""
        <head>
            <title>{title}</title>
            <link rel="icon" href="/favicon.ico" type="image/x-icon">
            <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
            <style>
                body {{ background: #111; color: #eee; font-family: sans-serif; margin: 0; padding: 0; }}
                h1 {{ color: hotpink; text-align: center; margin: 2vw; }}
                h2 {{ color: #6cf; margin: 1vw 2vw 0.5vw; }}
                .banner {{ display: flex; overflow-x: auto; gap: 20px; padding: 2vw; scroll-behavior: smooth; }}
                .movie {{ flex: 0 0 auto; width: 160px; text-align: center; position: relative; scroll-snap-align: center;}}
                .movie img {{ width: 100%; border-radius: 1em; box-shadow: 0 0 10px #000; transition: transform 0.2s ease; }}
                .movie:hover img {{ transform: scale(1.15); }}
                .movie.selected img {{ transform: scale(1.15); }}
                .movie.selected .plot-overlay {{ display: block;}}
                .plot-overlay {{ display: none; position: absolute; top: 0; left: 170px; width: 280px; background: rgba(0, 0, 0, 0.85); color: #ccc; font-size: 0.9em; padding: 1em; border-radius: 1em; text-align: left; z-index: 10; }}
                .movie:hover .plot-overlay {{ display: block; }}
                .meta {{ font-size: 0.9em; color: #ccc; margin-top: 0.5em; }}
                .button {{ display: inline-block; margin: 2vw; padding: 1vw 2vw; background: hotpink; color: black; font-weight: bold; text-decoration: none; border-radius: 1em; font-size: 1em; }}
                .toggle {{ display: block; margin: 2vw auto; text-align: center; font-size: 1em; }}

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
                <a class="button" id="backBtn" href="/">Go Back</a>
            </div>
            <script>
            document.addEventListener("keydown", function(e) {{
                const key = e.key.toLowerCase();
                if (key === "enter") {{
                    const backBtn = document.getElementById("backBtn");
                if (backBtn) backBtn.click();
                }} else if (key === "contextmenu") {{
		e.preventDefault();
                fetch("/playpause");
                }}
            }});
            </script>
        </body>
        </html>
        """
        self.wfile.write(html.encode())


    def do_GET(self):
        global autoplay_enabled
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/favicon.ico":
            try:
                with open(os.path.join(APP_ROOT, "favicon.ico"), "rb") as f:
                    self.send_response(200)
                    self.send_header("Content-Type", "image/x-icon")
                    self.end_headers()
                    self.wfile.write(f.read())
                return
            except FileNotFoundError:
                self.send_error(404, "favicon.ico not found")
                return

        if parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()

            rows_html = ""
            rows_html += """
            <h2>TV Shows</h2>
            <div class='banner'>
                <div class="movie">
                    <a href="http://192.168.68.71:8030">
                        <img src="https://variety.com/wp-content/uploads/2024/01/100-Greatest-TV-Shows-V1-2.jpg?w=1024" alt="TV Shows" style="width: 300px; border-radius: 10px; box-shadow: 2px 2px 8px #000;">
                    </a>
                    <div class="meta"><strong><br>Select to see shows</strong></div>
                </div>
            </div>
            """

            # First: all folders except "survivor"
            for folder in sorted(k for k in movie_metadata if k != "survivor"):
                movies = movie_metadata[folder]
                if folder == "survivor":
                    continue

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

            # Then: add survivor banner last
            if "survivor" in movie_metadata:
                banner_items = ""
                for filename in movie_metadata["survivor"]:
                    rel_path = os.path.join("survivor", filename)
                    clean_name = os.path.splitext(filename)[0]
                    banner_items += f"""
                    <div class="movie">
                        <a href="/cast?file={urllib.parse.quote(rel_path)}">
                            <img src="https://plus.unsplash.com/premium_photo-1710409625244-e9ed7e98f67b?fm=jpg&q=60&w=3000&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1yZWxhdGVkfDF8fHxlbnwwfHx8fHw%3D" alt="{clean_name}">
                        </a>
                        <div class="meta">
                            <strong>{clean_name}</strong>
                        </div>
                    </div>
                    """
                if banner_items:
                    rows_html += (
                        f"<h2>Saves</h2><div class='banner'>{banner_items}</div>"
                    )

            toggle_label = (
                "Autoplay next episode" if autoplay_enabled else "Autoplay is BROKEN"
            )
            keyboard_script = """
            let selectedIndex = 0;
let rowIndex = 0;
let rows = [];
let movieElements = [];

document.addEventListener("DOMContentLoaded", () => {
    rows = Array.from(document.querySelectorAll('.banner'));
    movieElements = Array.from(rows[0].querySelectorAll('.movie'));
    highlightSelected();

    document.addEventListener("keydown", (e) => {
        const key = e.key.toLowerCase();

        if (key === "arrowright") {
            selectedIndex = (selectedIndex + 1) % movieElements.length;
            highlightSelected();
        } else if (key === "arrowleft") {
            selectedIndex = (selectedIndex - 1 + movieElements.length) % movieElements.length;
            highlightSelected();
        } else if (key === "arrowdown") {
            if (rowIndex < rows.length - 1) {
                rowIndex++;
                updateRow();
            }
        } else if (key === "arrowup") {
            if (rowIndex > 0) {
                rowIndex--;
                updateRow();
            }
        } else if (key === "enter") {
            const link = movieElements[selectedIndex].querySelector('a');
            if (link) link.click();
        } else if (key === "contextmenu") {
		e.preventDefault();
            fetch("/playpause");
        }
    });

    function updateRow() {
        const oldLength = movieElements.length;
        movieElements = Array.from(rows[rowIndex].querySelectorAll('.movie'));
        selectedIndex = Math.min(selectedIndex, movieElements.length - 1);
        highlightSelected();
        rows[rowIndex].scrollIntoView({
            behavior: "smooth",
            block: "center",
            inline: "center"
        });
    }

        function highlightSelected() {
        document.querySelectorAll('.movie').forEach(el => el.classList.remove("selected"));
        const el = movieElements[selectedIndex];
        if (el) {
            el.classList.add("selected");

            // Get poster's position relative to the page
            const rect = el.getBoundingClientRect();
            const absoluteTop = window.scrollY + rect.top;
            const offset = absoluteTop - (window.innerHeight / 2) + (rect.height / 2);

            window.scrollTo({
                top: offset,
                behavior: "auto"
            });

           // Horizontal scroll (center movie in banner)
    const container = rows[rowIndex];
    const elOffset = el.offsetLeft;
    const elWidth = el.offsetWidth;
    const containerWidth = container.clientWidth;

    const scrollLeftTarget = elOffset - (containerWidth / 2) + (elWidth / 2);

    container.scrollTo({
        left: scrollLeftTarget,
        behavior: "auto"  // or "smooth"
    });
        }
    }

});
            """
            slider_script = """
const sliderContainer = document.createElement("div");
sliderContainer.id = "slider-container";
sliderContainer.style.textAlign = "center";
sliderContainer.style.margin = "2vw";
sliderContainer.innerHTML = `
    <input type="range" id="seekSlider" min="0" max="100" value="0" step="1" style="width: 60%;">
    <div id="timeDisplay" style="margin-top: 0.5em; color: #aaa;">0:00 / 0:00</div>
`;
document.body.appendChild(sliderContainer);
let slider = document.getElementById("seekSlider");
let timeDisplay = document.getElementById("timeDisplay");
let duration = 0;
let isDragging = false;
let dragTimeout = null;
function formatTime(seconds) {
    seconds = Math.floor(seconds || 0);
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}
function updateSlider(currentTime) {
    if (!isDragging) {
        slider.value = Math.floor(currentTime);
        timeDisplay.innerText = `${formatTime(currentTime)} / ${formatTime(duration)}`;
    }
}
function pollStatus() {
    fetch('/status')
        .then(response => response.json())
        .then(data => {
            duration = Math.floor(data.duration || 0);
            slider.max = duration;
            updateSlider(data.current_time || 0);
        })
        .catch(err => {
            console.warn("Status polling failed:", err);
        });
}
slider.addEventListener("input", () => {
    isDragging = true;
    clearTimeout(dragTimeout);
    timeDisplay.innerText = `${formatTime(slider.value)} / ${formatTime(duration)}`;
});

slider.addEventListener("change", () => {
    fetch(`/seek?time=${slider.value}`)
        .then(() => {
            // give it a short delay before resuming polling updates
            dragTimeout = setTimeout(() => {
                isDragging = false;
            }, 1000);
        })
        .catch(err => {
            console.error("Seek failed:", err);
            isDragging = false;
        });
});
setInterval(pollStatus, 2000);
"""

            html = """
            <html>
            {head}
            <body>
                <h1>This is for my love whom I love</h1>
                {rows}
                <div class='toggle'>
                    <a class='button' href='/toggle_autoplay'>{toggle}</a>
                </div>
                <div style='text-align:center;'>
                    <a class='button' href='/stop'>Stop Cast</a>
                    <a class='button' href='/playpause'>Play/Pause</a>
                </div>
                <script>{script}</script>
		<div style="position: fixed; bottom: 20px; right: 20px;">
                    <a href="http://100.107.223.221:8050/" title="Play in Browser">
                        <svg xmlns="http://www.w3.org/2000/svg" height="36" width="36" viewBox="0 0 24 24" fill="#6cf">
                            <path d="M8 5v14l11-7z"/>
                        </svg>
                    </a>
                </div>
            </body>
            </html>
            """.format(
                head=self.get_head(),
                rows=rows_html,
                toggle=toggle_label,
                script=slider_script + keyboard_script,
               
            )

            self.wfile.write(html.encode())

        elif parsed.path == "/toggle_autoplay":
            autoplay_enabled = not autoplay_enabled
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()

        elif parsed.path == "/cast":
                filename = params.get("file", [None])[0]
                if filename:
                        full_path = os.path.abspath(os.path.join(MEDIA_DIR, filename))
                        folder = os.path.relpath(os.path.dirname(full_path), MEDIA_DIR)
                        file = os.path.basename(full_path)
                        try:
                                connect_chromecast()

                                # Check if something is currently playing or paused
                                try:
                                        media_controller.update_status()
                                        if media_controller.status.player_state in ("PLAYING", "PAUSED", "BUFFERING"):
                                                print("⏹ Stopping current media first...")
                                                media_controller.stop()
                                                # Give Chromecast a brief moment to settle before casting new file
                                                threading.Timer(1.0, lambda: subprocess.Popen([
                                                        CATT_PATH, "--device", CHROMECAST_NAME, "cast", full_path
                                                ])).start()
                                        else:
                                                # Nothing playing, cast immediately
                                                subprocess.Popen([
                                                        CATT_PATH, "--device", CHROMECAST_NAME, "cast", full_path
                                                ])
                                except Exception as stop_err:
                                        print("⚠️ Could not update status or stop media:", stop_err)
                                        # Still attempt to cast anyway
                                        subprocess.Popen([
                                                CATT_PATH, "--device", CHROMECAST_NAME, "cast", full_path
                                        ])

                                last_cast["folder"] = folder
                                last_cast["file"] = file
                                schedule_next_episode(folder, file)

                                self.send_response(200)
                                self.send_header("Content-type", "text/html")
                                self.end_headers()
                                self.send_pretty_page("Casting", f"Now casting: {file}")

                        except Exception as e:
                                self.send_error(500, f"Casting error: {str(e)}")
                else:
                        self.send_error(400, "Missing file parameter")

        elif parsed.path == "/cast":
            filename = params.get("file", [None])[0]
            if filename:
                full_path = os.path.abspath(os.path.join(MEDIA_DIR, filename))
                folder = os.path.relpath(os.path.dirname(full_path), MEDIA_DIR)
                file = os.path.basename(full_path)
                try:
                    connect_chromecast()
                    subprocess.Popen([CATT_PATH, "--device", CHROMECAST_NAME, "cast", full_path])
                    last_cast["folder"] = folder
                    last_cast["file"] = file
                    schedule_next_episode(folder, file)
                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    self.send_pretty_page("Casting", f"Now casting: {file}")
                except Exception as e:
                    self.send_error(500, f"Casting error: {str(e)}")
            else:
                self.send_error(400, "Missing file parameter")

        elif parsed.path == "/playpause":
            try:
                connect_chromecast()
                media_controller.update_status()
                if media_controller.status.player_state == "PLAYING":
                    media_controller.pause()
                else:
                    media_controller.play()
                self.send_response(302)
                self.send_header("Location", "/")
                self.end_headers()
            except Exception as e:
                self.send_error(500, f"Toggle error: {str(e)}")

        elif parsed.path == "/stop":
            try:
                connect_chromecast()
                media_controller.stop()
                self.send_response(302)
                self.send_header("Location", "/")
                self.end_headers()
            except Exception as e:
                self.send_error(500, f"Stop error: {str(e)}")

        elif parsed.path == "/seek":
            try:
                seconds = float(params.get("time", [0])[0])
                connect_chromecast()
                media_controller.seek(seconds)
                self.send_response(200)
                self.end_headers()
            except Exception as e:
                self.send_error(500, f"Seek error: {str(e)}")

        elif parsed.path == "/status":
            try:
                connect_chromecast()
                media_controller.update_status()
                status = {
                    "current_time": media_controller.status.current_time or 0,
                    "duration": media_controller.status.duration or 0,
                    "state": media_controller.status.player_state or "UNKNOWN"
                }
                self.send_response(200)
                print("📊 Status response:", json.dumps(status, indent=2))
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(status).encode())

            except Exception as e:
                print("Status polling failed:", e)
                self.send_response(200)  # Still respond with 200 OK
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "current_time": 0,
                    "duration": 0,
                    "state": "OFFLINE"
                }).encode())


if __name__ == "__main__":
    load_metadata()
    os.chdir(APP_ROOT)
    server_address = (PI_IP, PORT)
    print(f"🎬 Serving on http://{PI_IP}:{PORT}/")
    HTTPServer(server_address, BannerHandler).serve_forever()
