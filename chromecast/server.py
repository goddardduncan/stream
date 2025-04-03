from http.server import HTTPServer, SimpleHTTPRequestHandler
import os
import urllib.parse
import subprocess

# 🛠️ Hardcoded for your setup
MEDIA_DIR = "media"
current_path = os.path.abspath(MEDIA_DIR)
PORT = 8000
PI_IP = "192.168.68.71"
CHROMECAST_NAME = "Living Room TV"

class LANCastHandler(SimpleHTTPRequestHandler):
    def list_files(self):
        entries = os.listdir(current_path)
        folders = []
        files = []

        for entry in entries:
            if entry.startswith(".") or entry == "Program":
                continue
            path = os.path.join(current_path, entry)
            if os.path.isdir(path):
                folders.append(f"[{entry}]")
            elif os.path.isfile(path):
                if not entry.endswith(".c"):
                    files.append(entry)

        folders.sort(key=lambda x: x.lower())
        files.sort(key=lambda x: x.lower())

        items = []
        if current_path != os.path.abspath(MEDIA_DIR):
            items.append('<li><a href="/navigate?dir=..">(Back)</a></li>')

        for folder in folders:
            name = folder.strip("[]")
            items.append(f'<li><a href="/navigate?dir={urllib.parse.quote(name)}">{folder}</a></li>')

        for f in files:
            items.append(f'<li><a href="/cast?file={urllib.parse.quote(f)}">{f}</a></li>')

        return "\n".join(items)

    def do_GET(self):
        global current_path
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        def get_head(title):
            return f"""
            <head>
            <title>{title}</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{
                    font-family: monospace;
                    background: #111;
                    color: #eee;
                    padding: 5vw;
                    font-size: 1.2em;
                }}
                a {{
                    color: #6cf;
                    text-decoration: none;
                }}
                li {{
                    margin: 4vw 0;
                    font-size: 1.1em;
                }}
                h1, h2 {{
                    color: hotpink;
                    font-size: 1.5em;
                    margin-bottom: 1em;
                }}
                .stop-button {{
                    display: inline-block;
                    margin: 5vw 2vw 5vw 0;
                    padding: 4vw 6vw;
                    background: hotpink;
                    color: black;
                    font-weight: bold;
                    text-decoration: none;
                    border-radius: 1em;
                    font-size: 1em;
                }}
                .playpause-button {{
                    display: inline-block;
                    margin: 5vw 0;
                    padding: 4vw 6vw;
                    background: #6f6;
                    color: black;
                    font-weight: bold;
                    text-decoration: none;
                    border-radius: 1em;
                    font-size: 1em;
                }}
                .button {{
                    display: inline-block;
                    margin: 5vw 0;
                    padding: 4vw 6vw;
                    background: hotpink;
                    color: black;
                    font-weight: bold;
                    text-decoration: none;
                    border-radius: 1em;
                    font-size: 1em;
                }}
            </style>
            </head>
            """

        if parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            html = f"""
            <html>
            {get_head("Movie Caster")}
            <body>
            <h1>This is for my love whom I love.</h1>
            <ul>{self.list_files()}</ul><br><br>
            <a class="stop-button" href="/stop">Stop Cast</a>
            <a class="playpause-button" href="/playpause">PLAY/PAUSE</a>
            </body></html>
            """
            self.wfile.write(html.encode())

        elif parsed.path == "/navigate":
            dirname = params.get("dir", [""])[0]
            if dirname == "..":
                new_path = os.path.dirname(current_path)
                if os.path.commonpath([new_path, os.path.abspath(MEDIA_DIR)]) == os.path.abspath(MEDIA_DIR):
                    current_path = new_path
            else:
                new_path = os.path.join(current_path, dirname)
                if os.path.isdir(new_path):
                    current_path = new_path

            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()

        elif parsed.path == "/cast":
            filename = params.get("file", [None])[0]
            if filename:
                file_path = os.path.abspath(os.path.join(current_path, filename))
                if not os.path.isfile(file_path):
                    self.send_error(404, "File not found")
                    return

                try:
                    subprocess.Popen(["catt", "--device", CHROMECAST_NAME, "cast", file_path])
                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    html = f"""
                    <html>
                    {get_head("Casting")}
                    <body>
                    <h2>Started casting: {filename}</h2>
                    <a class="button" href='/'>Go back</a>
                    </body></html>
                    """
                    self.wfile.write(html.encode())
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(f"<html><body><h2>Error: {str(e)}</h2><a href='/'>Go back</a></body></html>".encode())
            else:
                self.send_error(400, "Missing file parameter")

        elif parsed.path == "/stop":
            try:
                subprocess.run(["catt", "--device", CHROMECAST_NAME, "stop"])
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                html = f"""
                <html>
                {get_head("Stopped")}
                <body>
                <h2>Stopped casting</h2>
                <a class="button" href='/'>Go back</a>
                </body></html>
                """
                self.wfile.write(html.encode())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"<html><body><h2>Error stopping cast: {str(e)}</h2><a href='/'>Go back</a></body></html>".encode())

        elif parsed.path == "/playpause":
            try:
                subprocess.run(["catt", "--device", CHROMECAST_NAME, "play_toggle"])
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                html = f"""
                <html>
                {get_head("Toggled Playback")}
                <body>
                <h2>Playback toggled</h2>
                <a class="button" href='/'>Go back</a>
                </body></html>
                """
                self.wfile.write(html.encode())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"<html><body><h2>Error toggling playback: {str(e)}</h2><a href='/'>Go back</a></body></html>".encode())

        else:
            super().do_GET()

def run():
    server_address = (PI_IP, PORT)
    httpd = HTTPServer(server_address, LANCastHandler)
    print(f"Serving on http://{PI_IP}:{PORT}/")
    httpd.serve_forever()

if __name__ == "__main__":
    run()
