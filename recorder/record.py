from flask import Flask, render_template_string, request, redirect
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import os
import subprocess
import urllib.parse
import requests
import xml.etree.ElementTree as ET
import signal

app = Flask(__name__)
scheduler = BackgroundScheduler()
scheduler.start()

# === Config ===
SAVE_DIR = "./saved"
os.makedirs(SAVE_DIR, exist_ok=True)

EPG_URL = "https://i.mjh.nz/au/Melbourne/epg.xml"
EPG_CACHE = {"data": None, "fetched_at": None}
active_direct_jobs = {}

streams = {
    "mjh-abc-vic": "https://c.mjh.nz/abc-vic.m3u8",
    "mjh-seven-mel": "https://i.mjh.nz/.r/seven-mel.m3u8",
    "mjh-7two-mel": "https://i.mjh.nz/.r/7two-mel.m3u8",
    "mjh-7mate-mel": "https://i.mjh.nz/.r/7mate-mel.m3u8",
    "mjh-7flix-mel": "https://i.mjh.nz/.r/7flix-mel.m3u8",
    "mjh-channel-9-vic": "https://i.mjh.nz/.r/channel-9-vic.m3u8",
    "mjh-gem-vic": "https://i.mjh.nz/.r/gem-vic.m3u8",
    "mjh-go-vic": "https://i.mjh.nz/.r/go-vic.m3u8",
    "mjh-life-vic": "https://i.mjh.nz/.r/life-vic.m3u8",
    "mjh-rush-vic": "https://i.mjh.nz/.r/rush-vic.m3u8",
    "mjh-10-vic": "https://i.mjh.nz/.r/10-vic.m3u8",
    "mjh-10bold-vic": "https://i.mjh.nz/.r/10bold-vic.m3u8",
    "mjh-10peach-vic": "https://i.mjh.nz/.r/10peach-vic.m3u8",
    "mjh-10shake-vic": "https://i.mjh.nz/.r/10shake-vic.m3u8",
    "mjh-sbs": "https://i.mjh.nz/.r/sbs.m3u8",
    "mjh-sbs-viceland": "https://i.mjh.nz/.r/sbs-viceland.m3u8",
    "mjh-sbs-food": "https://i.mjh.nz/.r/sbs-food.m3u8",
    "mjh-sbs-world-movies": "https://i.mjh.nz/.r/sbs-world-movies.m3u8",
    "mjh-sbs-nitv": "https://i.mjh.nz/.r/sbs-nitv.m3u8",
    "mjh-c31": "https://i.mjh.nz/.r/c31.m3u8"
}

# === EPG Functions ===

def get_epg_root():
    now = datetime.utcnow()
    if EPG_CACHE["data"] and EPG_CACHE["fetched_at"] and (now - EPG_CACHE["fetched_at"]).seconds < 900:
        return EPG_CACHE["data"]
    xml_data = requests.get(EPG_URL).content
    root = ET.fromstring(xml_data)
    EPG_CACHE["data"] = root
    EPG_CACHE["fetched_at"] = now
    return root

def find_program_title(channel_id, dt):
    root = get_epg_root()
    target_time = dt.strftime("%Y%m%d%H%M%S")
    for programme in root.findall('programme'):
        if programme.attrib['channel'] != channel_id:
            continue
        start = programme.attrib['start'].split()[0]
        stop = programme.attrib['stop'].split()[0]
        if start <= target_time < stop:
            title = programme.findtext('title')
            subtitle = programme.findtext('sub-title')
            return f"{title} - {subtitle}" if subtitle else title
    return None

def get_channel_info(channel_id):
    root = get_epg_root()
    for channel in root.findall('channel'):
        if channel.attrib['id'] == channel_id:
            name = channel.findtext('display-name') or channel_id
            icon_elem = channel.find('icon')
            icon = icon_elem.attrib.get('src') if icon_elem is not None else ""
            return name, icon
    return channel_id, ""

# === HTML Template ===

html_template = """
<!DOCTYPE html>
<html>
<head><title>Stream Scheduler</title></head>
<body style="font-family:sans-serif;">
    <h2>📅 Schedule a Recording</h2>
    <form method="POST" action="/schedule">
        <label>Start Time:</label><input type="datetime-local" name="start_time" required><br><br>
        <label>Duration (minutes):</label><input type="number" name="duration" value="30" min="1" required><br><br>
        <label>Choose Stream:</label><br>
        {% for key, url in streams.items() %}
            <label style="display: flex; align-items: center; margin-bottom: 4px;">
                <input type="radio" name="stream_key" value="{{ key }}" required style="margin-right: 8px;">
                {% if icons[key] %}
                    <img src="{{ icons[key] }}" style="height: 1em; margin-right: 6px;">
                {% endif %}
                {{ labels[key] }}
            </label>
        {% endfor %}
        <br><input type="submit" value="Schedule Recording">
    </form>

    <hr>
    <h2>🎬 Record Direct m3u8 Stream</h2>
    <form method="POST" action="/record_direct">
        <label>m3u8 URL:</label><br>
        <input type="url" name="url" style="width: 80%;" required><br><br>

        <label>Optional Filename:</label><br>
        <input type="text" name="label" style="width: 50%;" placeholder="My Live Stream"><br><br>

        <label>Duration (optional, in minutes):</label><br>
        <input type="number" name="duration" min="1" style="width: 80px;" placeholder="Leave blank for until complete"><br><br>

        <input type="submit" value="Start Recording">
    </form>

    {% if active_direct %}
    <hr>
    <h3>🛑 Active Direct Recordings:</h3>
    <ul>
        {% for name, job in active_direct.items() %}
            <li>
                {{ name }} — started at {{ job['start'] }}
                <form method="POST" action="/stop_direct" style="display:inline;">
                    <input type="hidden" name="job_id" value="{{ job['id'] }}">
                    <button type="submit">Stop</button>
                </form>
            </li>
        {% endfor %}
    </ul>
    {% endif %}

    <hr>
    <h3>📝 Scheduled Jobs:</h3>
    <ul>
    {% for job in jobs %}
        <li>{{ job.name }} @ {{ job.next_run_time }}</li>
    {% endfor %}
    </ul>
</body>
</html>
"""

# === Routes ===

@app.route("/", methods=["GET"])
def index():
    jobs = scheduler.get_jobs()
    root = get_epg_root()

    channel_labels = {}
    channel_icons = {}

    for key in streams:
        name, icon = get_channel_info(key)
        channel_labels[key] = name
        channel_icons[key] = icon

    return render_template_string(html_template,
                                  streams=streams,
                                  jobs=jobs,
                                  labels=channel_labels,
                                  icons=channel_icons,
                                  active_direct=active_direct_jobs)

@app.route("/schedule", methods=["POST"])
def schedule():
    start_time_str = request.form['start_time']
    duration = int(request.form['duration'])
    stream_key = request.form['stream_key']

    if stream_key not in streams:
        return "Invalid stream selected", 400

    stream_url = streams[stream_key]
    start_dt = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M")

    show_title = find_program_title(stream_key, start_dt) or "Unknown_Show"
    channel_name, _ = get_channel_info(stream_key)

    timestamp = start_dt.strftime("%Y%m%d_%H%M")
    base_filename = f"{channel_name} - {show_title} {timestamp}"
    safe_filename = urllib.parse.quote_plus(base_filename)
    output_file = os.path.join(SAVE_DIR, f"{safe_filename}.ts")
    mp4_file = output_file.replace(".ts", ".mp4")

    def record_job():
        print(f"🎥 Recording {channel_name} - {show_title}")
        record_cmd = [
            "ffmpeg", "-y", "-i", stream_url,
            "-t", str(duration * 60),
            "-c", "copy", output_file
        ]
        subprocess.run(record_cmd)

        print(f"🎞️ Converting to MP4: {mp4_file}")
        convert_cmd = [
            "ffmpeg", "-y", "-i", output_file,
            "-c:v", "copy", "-c:a", "aac", "-strict", "experimental", mp4_file
        ]
        subprocess.run(convert_cmd)

        if os.path.exists(mp4_file):
            os.remove(output_file)

    job_id = f"record_{stream_key}_{timestamp}"
    scheduler.add_job(record_job, 'date', run_date=start_dt, id=job_id,
                      name=f"{channel_name}: {show_title} @ {start_dt}")
    return redirect("/")

@app.route("/record_direct", methods=["POST"])
def record_direct():
    m3u8_url = request.form["url"]
    label = request.form.get("label", "Live_Stream").strip() or "Live_Stream"
    duration_str = request.form.get("duration", "").strip()

    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M")
    safe_filename = urllib.parse.quote_plus(f"{label}_{timestamp}")
    output_file = os.path.join(SAVE_DIR, f"{safe_filename}.ts")
    mp4_file = output_file.replace(".ts", ".mp4")

    ffmpeg_cmd = ["ffmpeg", "-y", "-i", m3u8_url, "-c", "copy", output_file]
    if duration_str:
        duration = int(duration_str)
        ffmpeg_cmd.insert(-2, "-t")
        ffmpeg_cmd.insert(-2, str(duration * 60))

    def record_job():
        print(f"📡 Direct Recording: {label}")
        process = subprocess.Popen(ffmpeg_cmd)
        active_direct_jobs[label] = {
            "id": f"direct_{safe_filename}",
            "start": timestamp,
            "process": process
        }
        process.wait()

        print(f"🎞️ Converting to MP4: {mp4_file}")
        subprocess.run([
            "ffmpeg", "-y", "-i", output_file,
            "-c:v", "copy", "-c:a", "aac", "-strict", "experimental", mp4_file
        ])

        if os.path.exists(mp4_file):
            os.remove(output_file)

        active_direct_jobs.pop(label, None)

    scheduler.add_job(record_job, 'date', run_date=now,
                      id=f"direct_{safe_filename}", name=label)
    return redirect("/")

@app.route("/stop_direct", methods=["POST"])
def stop_direct():
    job_id = request.form["job_id"]
    for name, job in list(active_direct_jobs.items()):
        if job["id"] == job_id:
            print(f"🛑 Stopping: {name}")
            job["process"].send_signal(signal.SIGINT)
            return redirect("/")
    return "Job not found", 404

# === Run ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
