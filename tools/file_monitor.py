import os
import time
import threading
from typing import Callable, Dict, Any

class FileMonitor:
    def __init__(self, callback: Callable):
        self.callback = callback
        self.watched_files = {}  # path -> {"last_size": int, "last_mtime": float}
        self.running = False
        self.thread = None
    
    def add_file(self, path: str):
        if os.path.exists(path):
            self.watched_files[path] = {
                "last_size": os.path.getsize(path),
                "last_mtime": os.path.getmtime(path)
            }
    
    def start(self, interval: int = 30):
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, args=(interval,), daemon=True)
        self.thread.start()
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
    
    def _monitor_loop(self, interval):
        while self.running:
            for path, info in list(self.watched_files.items()):
                if not os.path.exists(path):
                    continue
                current_size = os.path.getsize(path)
                current_mtime = os.path.getmtime(path)
                if current_size > info["last_size"]:
                    # Le fichier a grossi : lire les nouvelles lignes
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            # Lire depuis la dernière position
                            f.seek(info["last_size"])
                            new_content = f.read()
                            if new_content.strip():
                                # Appeler le callback avec le nouveau contenu
                                self.callback(path, new_content)
                        info["last_size"] = current_size
                        info["last_mtime"] = current_mtime
                    except Exception as e:
                        print(f"[Monitor] Erreur lecture {path}: {e}")
            time.sleep(interval)