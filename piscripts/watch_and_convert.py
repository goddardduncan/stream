import time
import os
import threading
import queue
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

WATCH_FOLDER = "/home/duncan/watch"
OUTPUT_FOLDER = "/home/duncan/MovieCast/media"

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

video_extensions = ['.mkv', '.avi', '.mov', '.flv', '.wmv']

# Thread-safe queue to hold files to process
file_queue = queue.Queue()

def is_file_ready(filepath):
    """Check if file is fully written by monitoring its size over time"""
    initial_size = -1
    while True:
        try:
            current_size = os.path.getsize(filepath)
            if current_size == initial_size:
                return True
            initial_size = current_size
            time.sleep(1)
        except FileNotFoundError:
            return False

def convert_video_worker():
    """Worker thread to convert videos from the queue"""
    while True:
        filepath = file_queue.get()
        if filepath is None:
            break  # Exit signal
        filename = os.path.basename(filepath)
        base_name, _ = os.path.splitext(filename)
        output_path = os.path.join(OUTPUT_FOLDER, base_name + ".mp4")

        print(f"Waiting for file to finish copying: {filename}")
        if is_file_ready(filepath):
            print(f"Converting {filename} to MP4...")
            try:
                subprocess.run([
                    "ffmpeg", "-y", "-i", filepath,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "192k",
                    output_path
                ], check=True)
                print(f"✅ Conversion complete: {output_path}")
            except subprocess.CalledProcessError as e:
                print(f"❌ Failed to convert {filename}: {e}")
        file_queue.task_done()

class VideoHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        filepath = event.src_path
        if any(filepath.lower().endswith(ext) for ext in video_extensions):
            print(f"📦 Queuing new file: {filepath}")
            file_queue.put(filepath)

if __name__ == "__main__":
    print(f"👀 Watching folder: {WATCH_FOLDER}")
    event_handler = VideoHandler()
    observer = Observer()
    observer.schedule(event_handler, path=WATCH_FOLDER, recursive=False)
    observer.start()

    # Start the worker thread
    worker_thread = threading.Thread(target=convert_video_worker, daemon=True)
    worker_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping...")
        observer.stop()
        file_queue.put(None)  # Signal to exit the worker thread
        worker_thread.join()
    observer.join()
