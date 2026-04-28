#!/usr/bin/env python3
"""
Flask server that streams live video from all cameras in ~/dev.

Usage:
    source phosphobot/.venv/bin/activate
    python camera_stream_server.py

Authentication:
    Pass ?token=<TOKEN> in the URL. Once validated, a session cookie is set
    so subsequent requests do not need the token.
    Set the CAM_STREAM_TOKEN env var to override the default token.

Endpoints:
    /                  – grid view of all cameras (2 columns)
    /cam/<cam_id>      – full-page view of a single camera
    /video_feed/<id>   – MJPEG stream for a single camera
"""

import os
import secrets
import socket
import threading
import time
from functools import wraps
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np
from flask import Flask, Response, make_response, redirect, render_template_string, request

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
VALID_TOKEN = os.environ.get("CAM_STREAM_TOKEN", secrets.token_urlsafe(16))
STREAM_FPS = 15
JPEG_QUALITY = 80
FRAME_WIDTH = 640
FRAME_HEIGHT = 480


# ---------------------------------------------------------------------------
# Port discovery
# ---------------------------------------------------------------------------
def find_free_port(start: int = 5201) -> int:
    """Return the first unused TCP port at or after *start*."""
    for port in range(start, 65535):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free TCP port found")


# ---------------------------------------------------------------------------
# Camera discovery
# ---------------------------------------------------------------------------
def discover_cameras() -> Dict[str, int]:
    """
    Return {symlink_name: video_index} for all cameras in ~/dev.
    Skips *-metadata symlinks.
    """
    dev_path = Path("~/dev").expanduser()
    cameras: Dict[str, int] = {}
    if not dev_path.exists():
        return cameras

    for link in dev_path.iterdir():
        if not link.is_symlink():
            continue
        name = link.name
        if not name.startswith("cam") or name.endswith("-metadata"):
            continue
        try:
            target = link.resolve()
            target_str = str(target)
            if target_str.startswith("/dev/video"):
                num_str = target_str.removeprefix("/dev/video")
                if num_str.isdigit():
                    cameras[name] = int(num_str)
        except (OSError, ValueError):
            continue
    return dict(sorted(cameras.items(), key=lambda item: item[0]))


# ---------------------------------------------------------------------------
# Camera manager (runs capture threads)
# ---------------------------------------------------------------------------
class CameraManager:
    def __init__(self) -> None:
        self._caps: Dict[str, cv2.VideoCapture] = {}
        self._latest: Dict[str, Optional[np.ndarray]] = {}
        self._threads: List[threading.Thread] = []
        self._stop_event = threading.Event()

    def start(self) -> List[str]:
        """Open all discovered cameras and start reader threads."""
        cam_map = discover_cameras()
        for cam_id, video_idx in cam_map.items():
            cap = cv2.VideoCapture(video_idx)
            if not cap.isOpened():
                print(f"[WARN] Could not open {cam_id} (/dev/video{video_idx})")
                cap.release()
                continue

            # Force MJPG to stay within USB bandwidth when multiple cams are active
            cap.set(
                cv2.CAP_PROP_FOURCC,
                cv2.VideoWriter_fourcc("M", "J", "P", "G"),
            )
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
            cap.set(cv2.CAP_PROP_FPS, STREAM_FPS)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            self._caps[cam_id] = cap
            self._latest[cam_id] = None

            t = threading.Thread(
                target=self._capture_loop, args=(cam_id, cap), daemon=True
            )
            t.start()
            self._threads.append(t)
            print(f"[INFO] Started {cam_id} (/dev/video{video_idx})")

        if not self._caps:
            print("[WARN] No cameras found in ~/dev")
        return list(self._caps.keys())

    def _capture_loop(self, cam_id: str, cap: cv2.VideoCapture) -> None:
        while not self._stop_event.is_set():
            ret, frame = cap.read()
            if ret and frame is not None:
                self._latest[cam_id] = frame
            else:
                time.sleep(0.01)

    def get_frame(self, cam_id: str) -> Optional[np.ndarray]:
        return self._latest.get(cam_id)

    def stop(self) -> None:
        self._stop_event.set()
        for t in self._threads:
            t.join(timeout=1.0)
        for cap in self._caps.values():
            cap.release()
        self._caps.clear()
        print("[INFO] Camera manager stopped")


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)
camera_manager = CameraManager()


def require_auth(f):
    """Decorator that enforces token auth (query param or cookie)."""

    @wraps(f)
    def decorated(*args, **kwargs):
        # 1. Already authenticated via cookie?
        if request.cookies.get("auth_token") == VALID_TOKEN:
            return f(*args, **kwargs)

        # 2. Token provided in query string?
        token = request.args.get("token")
        if token == VALID_TOKEN:
            resp = make_response(f(*args, **kwargs))
            resp.set_cookie("auth_token", VALID_TOKEN, max_age=30 * 24 * 60 * 60)
            return resp

        # 3. Deny
        return (
            "<h1>401 Unauthorized</h1>"
            "<p>Please provide a valid token, e.g. <code>?token=YOUR_TOKEN</code></p>",
            401,
        )

    return decorated


# ---------------------------------------------------------------------------
# HTML templates (inline so the script is self-contained)
# ---------------------------------------------------------------------------
INDEX_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }}</title>
  <style>
    body { font-family: sans-serif; margin: 0; padding: 20px; background: #111; color: #eee; }
    h1 { margin-top: 0; }
    a { color: #4af; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .camera-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 12px;
    }
    .camera-item {
      background: #222;
      border-radius: 8px;
      overflow: hidden;
      text-align: center;
    }
    .camera-item h3 {
      margin: 8px 0;
      font-size: 1rem;
    }
    .camera-item img {
      width: 100%;
      height: auto;
      display: block;
      background: #000;
    }
  </style>
</head>
<body>
<h1>Camera Grid</h1>
{% if cam_ids %}
  <div class="camera-grid">
    {% for cam_id in cam_ids %}
    <div class="camera-item">
      <h3>{{ cam_id }}</h3>
      <a href="/cam/{{ cam_id }}">
        <img src="/video_feed/{{ cam_id }}" alt="{{ cam_id }}">
      </a>
    </div>
    {% endfor %}
  </div>
{% else %}
  <p>No cameras found in ~/dev.</p>
{% endif %}
</body>
</html>
"""

CAMERA_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }}</title>
  <style>
    body { font-family: sans-serif; margin: 0; padding: 20px; background: #111; color: #eee; }
    h2 { margin-top: 0; }
    a { color: #4af; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .single-view img {
      max-width: 100%;
      height: auto;
      background: #000;
    }
  </style>
</head>
<body>
<h2>{{ cam_id }}</h2>
<p><a href="/">&larr; Back to grid</a></p>
<div class="single-view">
  <img src="/video_feed/{{ cam_id }}" alt="{{ cam_id }}">
</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
@require_auth
def index():
    cam_ids = list(camera_manager._latest.keys())
    return render_template_string(
        INDEX_TEMPLATE, title="Camera Grid", cam_ids=cam_ids
    )


@app.route("/cam/<cam_id>")
@require_auth
def single_camera(cam_id):
    if cam_id not in camera_manager._latest:
        return f"<h1>Camera '{cam_id}' not found</h1><a href='/'>Back</a>", 404
    return render_template_string(
        CAMERA_TEMPLATE, title=cam_id, cam_id=cam_id
    )


def _generate_mjpeg(cam_id: str):
    """Generator that yields JPEG frames for the MJPEG stream."""
    interval = 1.0 / STREAM_FPS
    while True:
        frame = camera_manager.get_frame(cam_id)
        if frame is not None:
            ret, buf = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
            )
            if ret:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
                )
        time.sleep(interval)


@app.route("/video_feed/<cam_id>")
@require_auth
def video_feed(cam_id):
    if cam_id not in camera_manager._latest:
        return "Camera not found", 404
    return Response(
        _generate_mjpeg(cam_id),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def _get_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def main():
    print("[INFO] Discovering and starting cameras...")
    cam_ids = camera_manager.start()
    print(f"[INFO] Active cameras: {cam_ids}")

    port = find_free_port(start=5201)
    local_ip = _get_local_ip()

    # Print the token-tipped URLs shortly after Flask prints its own startup lines
    def _print_access_urls():
        time.sleep(0.5)
        print()
        print(f" * Access with token: http://127.0.0.1:{port}/?token={VALID_TOKEN}")
        print(f" * Access with token: http://{local_ip}:{port}/?token={VALID_TOKEN}")
        print("   (Ctrl+Click the URL in the VS Code terminal to open)")
        print()

    threading.Thread(target=_print_access_urls, daemon=True).start()

    try:
        app.run(host="0.0.0.0", port=port, threaded=True)
    finally:
        camera_manager.stop()


if __name__ == "__main__":
    main()
