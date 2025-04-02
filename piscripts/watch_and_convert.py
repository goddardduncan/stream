import time
import os
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Set your watch and output folders here
WATCH_FOLDER = "/home/duncan/watch"
OUTPUT_FOLDER = "/home/duncan/MovieCast/media"

# Create output folder if it doesn't exist
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

class VideoHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return

        filepath = event.src_path
        filename = os.path.basename(filepath)

        # Check for video file extensions
        if any(filename.lower().endswith(ext) for ext in ['.mkv', '.avi', '.mov', '.flv', '.wmv']):
            print(f"New file detected: {filename}")
            base_name = os.path.splitext(filename)[0]
            output_path = os.path.join(OUTPUT_FOLDER, base_name + ".mp4")

            # Wait a bit in case file is still copying
            time.sleep(5)

            print(f"Converting {filename} to MP4...")
            subprocess.run([
                "ffmpeg", "-i", filepath,
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "192k",
                output_path
            ])
            print(f"Conversion complete: {output_path}")

if __name__ == "__main__":
    event_handler = VideoHandler()
    observer = Observer()
    observer.schedule(event_handler, path=WATCH_FOLDER, recursive=False)
    observer.start()

    print(f"Watching folder: {WATCH_FOLDER}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
