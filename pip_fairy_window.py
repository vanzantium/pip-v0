"""
pip_fairy_window.py — Lightweight System Tray launcher for Pip.

Features:
  • Zero-overhead system tray icon via pystray (replaces the heavy Edge pywebview)
  • Starts pip_control_panel.py as a subprocess
  • Click "Open Dashboard" to view Pip in your fast, native default browser.
"""

import os
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
import webbrowser
from pathlib import Path
from PIL import Image, ImageDraw

import pip_platform
import pystray
from pystray import MenuItem as item

def start_ollama_background():
    """Silently spawn ollama serve in the background if it isn't running."""
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **pip_platform.hidden_subprocess_kwargs(),
        )
    except Exception as e:
        print("Failed to start Ollama in background:", e)

try:
    import pip_pc_tracker
    _TRACKER_AVAILABLE = True
except ImportError:
    _TRACKER_AVAILABLE = False

PORT = 8787
BASE_URL = f"http://127.0.0.1:{PORT}"

def start_server() -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, "pip_control_panel.py"],
        cwd=str(Path(__file__).resolve().parent),
    )
    # poll until the server accepts connections
    for _ in range(24):
        try:
            urllib.request.urlopen(BASE_URL, timeout=1)
            return proc
        except Exception:
            time.sleep(0.5)
    return proc

def create_icon_image():
    """Create a default 64x64 green fairy-light icon if no avatar is found."""
    # Try to load avatar if it exists
    for ext in ["png", "jpg", "jpeg", "gif"]:
        img_path = Path(f"avatar.{ext}")
        if img_path.exists():
            try:
                return Image.open(img_path)
            except Exception:
                pass
                
    # Fallback default green glowing dot
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    dc = ImageDraw.Draw(img)
    dc.ellipse([16, 16, 48, 48], fill=(16, 185, 129, 255))
    return img

def open_dashboard(icon, item):
    webbrowser.open(BASE_URL)

def quit_app(icon, item):
    icon.stop()

def main():
    start_ollama_background()
    print("[pip] Starting control panel server...")
    server_proc = start_server()

    if _TRACKER_AVAILABLE:
        pip_pc_tracker.start()
        print("[pip] PC usage tracker started")

    nightwatch_proc = None
    if os.environ.get("PIP_ENABLE_NIGHTWATCH") == "1":
        print("[pip] Starting Nightwatch background loop...")
        try:
            nightwatch_proc = subprocess.Popen(
                [sys.executable, "pip_nightwatch_loop.py"],
                cwd=str(Path(__file__).resolve().parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **pip_platform.hidden_subprocess_kwargs(),
            )
        except Exception as e:
            print("[pip] Failed to start Nightwatch:", e)
    else:
        print("[pip] Nightwatch is off. Set PIP_ENABLE_NIGHTWATCH=1 to opt in.")

    print("[pip] Starting Phone Relay background loop...")
    phone_relay_proc = None
    try:
        phone_relay_proc = subprocess.Popen(
            [sys.executable, "pip_phone_relay.py", "--background"],
            cwd=str(Path(__file__).resolve().parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **pip_platform.hidden_subprocess_kwargs(),
        )
    except Exception as e:
        print("[pip] Failed to start Phone Relay:", e)

    # Setup System Tray
    image = create_icon_image()
    menu = pystray.Menu(
        item('Open Dashboard', open_dashboard, default=True),
        item('Quit Pip', quit_app)
    )
    icon = pystray.Icon("pip", image, "Pip", menu)

    print("[pip] System tray icon ready.")
    try:
        # Blocks until icon.stop() is called
        icon.run()
    finally:
        print("[pip] Shutting down...")
        server_proc.terminate()
        if nightwatch_proc:
            try:
                nightwatch_proc.terminate()
            except Exception:
                pass
        if phone_relay_proc:
            try:
                phone_relay_proc.terminate()
            except Exception:
                pass

if __name__ == "__main__":
    main()
