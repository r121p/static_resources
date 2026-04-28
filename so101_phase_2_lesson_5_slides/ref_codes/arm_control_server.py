#!/usr/bin/env python3
"""
Flask web UI for controlling an SO-100 robot arm.

Usage:
    source phosphobot/.venv/bin/activate
    python arm_control_server.py

Authentication:
    Pass ?token=<TOKEN> in the URL. Once validated, a session cookie is set.
    Set the ARM_CONTROL_TOKEN env var to override the randomly-generated token.
"""

import argparse
import asyncio
import os
import secrets
import socket
import threading
import time
from functools import wraps
from pathlib import Path
from typing import Dict, List, Optional

from flask import Flask, jsonify, make_response, render_template_string, request

from ik import ArmController

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
VALID_TOKEN = os.environ.get("ARM_CONTROL_TOKEN", secrets.token_urlsafe(16))

# Slider ranges derived from ik_evaluate_manipulation_area.py
RANGE_X = (-50, 25)
RANGE_Y = (-40, 40)
RANGE_Z = (-12, 20)
RANGE_RX = (-180, 180)
RANGE_RY = (-180, 180)
RANGE_RZ = (-180, 180)
RANGE_GRIPPER = (0, 100)
RANGE_DURATION = (0.5, 5.0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def resolve_arm_alias(alias: str) -> tuple[str, str]:
    dev_path = os.path.expanduser(f"~/dev/{alias}")
    if not os.path.exists(dev_path):
        raise FileNotFoundError(
            f"Alias '{alias}' not found at {dev_path}. "
            f"Make sure the symlink exists (e.g. white_1 -> /dev/ttyACM0)."
        )
    return alias, os.path.realpath(dev_path)


def discover_arm_aliases() -> List[str]:
    dev_path = Path("~/dev").expanduser()
    aliases: List[str] = []
    if not dev_path.exists():
        return aliases
    for link in dev_path.iterdir():
        if not link.is_symlink():
            continue
        name = link.name
        if not name.startswith("white"):
            continue
        target = str(link.resolve())
        if target.startswith("/dev/ttyACM") or target.startswith("/dev/ttyUSB"):
            aliases.append(name)
    return sorted(aliases)


def find_free_port(start: int = 5201) -> int:
    for port in range(start, 65535):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free TCP port found")


def _get_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


# ---------------------------------------------------------------------------
# Arm manager (background asyncio loop)
# ---------------------------------------------------------------------------
class ArmManager:
    def __init__(self, serial_id: str, device_name: str):
        self.arm = ArmController(serial_id=serial_id, device_name=device_name)
        self.serial_id = serial_id
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        self._ready.wait(timeout=30)
        if not self._ready.is_set():
            raise RuntimeError("Arm failed to connect within 30 seconds")

    def _run(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            connected = self.loop.run_until_complete(self.arm.connect())
            if not connected:
                print("[ERROR] Failed to connect to arm")
                return
            self.arm.torque_on()
            self.loop.run_until_complete(self.arm.initialize_pose())
            print("[INFO] Arm initialized and ready")
            self._ready.set()
        except Exception as e:
            print(f"[ERROR] Arm initialization failed: {e}")
            return
        self.loop.run_forever()

    def _dispatch(self, coro, timeout: float = 15):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout=timeout)

    def move_to_pose(self, **kwargs):
        async def _move():
            return await self.arm.move_to_pose(**kwargs)
        return self._dispatch(_move(), timeout=15)

    def set_gripper(self, opening: float):
        async def _grip():
            self.arm.set_gripper(opening)
        return self._dispatch(_grip(), timeout=5)

    def get_pose(self):
        async def _pose():
            return self.arm.get_pose()
        return self._dispatch(_pose(), timeout=5)

    def go_home(self, duration: float = 3.0):
        return self.move_to_pose(
            x=-20, y=0, z=0,
            rx=0, ry=0, rz=0,
            duration=duration,
        )

    def is_ready(self) -> bool:
        return self._ready.is_set() and self.arm.is_connected

    def stop(self):
        with self._lock:
            if self.loop is None or self._thread is None:
                return
            async def _shutdown():
                try:
                    self.arm.torque_off()
                    await self.arm.disconnect()
                except Exception as e:
                    print(f"[WARN] Error during shutdown: {e}")
            try:
                asyncio.run_coroutine_threadsafe(_shutdown(), self.loop)
                self.loop.call_soon_threadsafe(self.loop.stop)
                self._thread.join(timeout=5)
            except Exception as e:
                print(f"[WARN] Shutdown issue: {e}")
            self._thread = None
            self.loop = None
            self._ready.clear()


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)
arm_manager: Optional[ArmManager] = None
_manager_lock = threading.Lock()


def _json_unauthorized():
    return jsonify({"success": False, "error": "Unauthorized. Provide ?token=..."}), 401


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Accept auth from any source; an old invalid cookie must not block a valid token
        candidates = [
            request.cookies.get("auth_token"),
            request.headers.get("X-Auth-Token"),
            request.args.get("token"),
        ]
        if VALID_TOKEN in candidates:
            resp = make_response(f(*args, **kwargs))
            resp.set_cookie("auth_token", VALID_TOKEN, max_age=30 * 24 * 60 * 60)
            return resp
        if request.path.startswith("/api/"):
            return _json_unauthorized()
        return (
            "<h1>401 Unauthorized</h1>"
            "<p>Please provide a valid token, e.g. <code>?token=YOUR_TOKEN</code></p>",
            401,
        )
    return decorated


# ---------------------------------------------------------------------------
# HTML UI
# ---------------------------------------------------------------------------
CONTROL_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SO-100 Arm Control</title>
  <style>
    * { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      margin: 0; padding: 20px;
      background: #0d1117; color: #c9d1d9;
    }
    .container { max-width: 900px; margin: 0 auto; }
    h1 { margin-top: 0; color: #58a6ff; }
    .card {
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 10px;
      padding: 16px;
      margin-bottom: 16px;
    }
    .card h3 { margin-top: 0; color: #79c0ff; font-size: 1rem; }
    .row {
      display: flex; align-items: center; gap: 10px;
      margin-bottom: 10px;
    }
    .row label { width: 130px; font-weight: 600; }
    .row input[type="range"] { flex: 1; }
    .row .val { width: 70px; text-align: right; font-variant-numeric: tabular-nums; }
    .mode-btns { display: flex; gap: 8px; margin-bottom: 10px; }
    .mode-btn {
      background: #21262d; border: 1px solid #30363d; color: #c9d1d9;
      padding: 8px 14px; border-radius: 6px; cursor: pointer;
    }
    .mode-btn.active { background: #1f6feb; border-color: #1f6feb; color: #fff; }
    .checkbox-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
    .checkbox-row input[type="number"] {
      width: 70px; background: #0d1117; color: #c9d1d9;
      border: 1px solid #30363d; border-radius: 4px; padding: 4px;
    }
    .btn {
      background: #238636; color: #fff; border: none;
      padding: 10px 18px; border-radius: 6px; cursor: pointer;
      font-weight: 600; font-size: 1rem;
    }
    .btn:hover { background: #2ea043; }
    .btn-secondary {
      background: #1f6feb; margin-left: 10px;
    }
    .btn-secondary:hover { background: #388bfd; }
    .btn-warn {
      background: #da3633; margin-left: 10px;
    }
    .btn-warn:hover { background: #f85149; }
    .status {
      margin-top: 12px; padding: 10px; border-radius: 6px;
      font-weight: 500; display: none;
    }
    .status.ok { background: rgba(46, 160, 67, 0.2); color: #3fb950; border: 1px solid #3fb950; display: block; }
    .status.err { background: rgba(248, 81, 73, 0.2); color: #f85149; border: 1px solid #f85149; display: block; }
    .pose-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
    .pose-item { background: #0d1117; padding: 8px; border-radius: 6px; text-align: center; }
    .pose-item .k { font-size: 0.75rem; color: #8b949e; }
    .pose-item .v { font-size: 1.1rem; font-weight: 700; }
    select {
      background: #0d1117; color: #c9d1d9; border: 1px solid #30363d;
      padding: 6px 10px; border-radius: 6px;
    }
  </style>
</head>
<body>
<div class="container">
  <h1>SO-100 Arm Control</h1>

  <div class="card">
    <h3>Arm Selection</h3>
    <div class="row">
      <label>Arm</label>
      <select id="arm-select"></select>
      <button class="btn" onclick="connectArm()" style="margin-left:10px;">Connect</button>
      <button class="btn btn-warn" onclick="disconnectArm()">Disconnect</button>
    </div>
    <div id="conn-status" style="margin-top:8px;">Checking...</div>
  </div>

  <div class="card">
    <h3>Current Pose (relative to initial)</h3>
    <div id="pose-display" class="pose-grid">
      <div class="pose-item"><div class="k">X</div><div class="v">-</div></div>
      <div class="pose-item"><div class="k">Y</div><div class="v">-</div></div>
      <div class="pose-item"><div class="k">Z</div><div class="v">-</div></div>
      <div class="pose-item"><div class="k">RX</div><div class="v">-</div></div>
      <div class="pose-item"><div class="k">RY</div><div class="v">-</div></div>
      <div class="pose-item"><div class="k">RZ</div><div class="v">-</div></div>
    </div>
  </div>

  <div class="card">
    <h3>Control Mode</h3>
    <div class="mode-btns">
      <button class="mode-btn active" id="btn-pos-only" onclick="setMode('position_only')">Position Only IK</button>
      <button class="mode-btn" id="btn-full-pose" onclick="setMode('full_pose')">Full Pose (Pos + Ori)</button>
    </div>
  </div>

  <div class="card">
    <h3>Target Position (cm)</h3>
    <div class="row">
      <label>X</label>
      <input type="range" id="x" min="{{x_min}}" max="{{x_max}}" step="0.5" value="0" oninput="showVal('x')">
      <span class="val" id="x-val">0.0</span>
    </div>
    <div class="row">
      <label>Y</label>
      <input type="range" id="y" min="{{y_min}}" max="{{y_max}}" step="0.5" value="0" oninput="showVal('y')">
      <span class="val" id="y-val">0.0</span>
    </div>
    <div class="row">
      <label>Z</label>
      <input type="range" id="z" min="{{z_min}}" max="{{z_max}}" step="0.5" value="0" oninput="showVal('z')">
      <span class="val" id="z-val">0.0</span>
    </div>
  </div>

  <div class="card" id="ori-card" style="display:none;">
    <h3>Target Orientation (deg)</h3>
    <div class="row">
      <label>RX</label>
      <input type="range" id="rx" min="{{rx_min}}" max="{{rx_max}}" step="1" value="0" oninput="showVal('rx')">
      <span class="val" id="rx-val">0</span>
    </div>
    <div class="row">
      <label>RY</label>
      <input type="range" id="ry" min="{{ry_min}}" max="{{ry_max}}" step="1" value="-90" oninput="showVal('ry')">
      <span class="val" id="ry-val">-90</span>
    </div>
    <div class="row">
      <label>RZ</label>
      <input type="range" id="rz" min="{{rz_min}}" max="{{rz_max}}" step="1" value="0" oninput="showVal('rz')">
      <span class="val" id="rz-val">0</span>
    </div>
  </div>

  <div class="card">
    <h3>Joint Locks</h3>
    <div class="checkbox-row">
      <input type="checkbox" id="lock-wrist-flex">
      <label for="lock-wrist-flex">Lock Wrist Flex (joint 3) at</label>
      <input type="range" id="lock-wrist-flex-val" min="-90" max="90" step="1" value="0" oninput="document.getElementById('lock-wrist-flex-disp').textContent=this.value+'°'">
      <span id="lock-wrist-flex-disp" style="width:45px;text-align:right;">0°</span>
    </div>
    <div class="checkbox-row">
      <input type="checkbox" id="lock-wrist-roll">
      <label for="lock-wrist-roll">Lock Wrist Roll (joint 4) at</label>
      <input type="range" id="lock-wrist-roll-val" min="-90" max="90" step="1" value="90" oninput="document.getElementById('lock-wrist-roll-disp').textContent=this.value+'°'">
      <span id="lock-wrist-roll-disp" style="width:45px;text-align:right;">90°</span>
    </div>
  </div>

  <div class="card">
    <h3>Gripper</h3>
    <div class="row">
      <label>Opening</label>
      <input type="range" id="gripper" min="0" max="100" step="1" value="50"
             oninput="showVal('gripper'); sendGripper()">
      <span class="val" id="gripper-val">50%</span>
    </div>
  </div>

  <div class="card">
    <h3>Movement</h3>
    <div class="row">
      <label>Duration</label>
      <input type="range" id="duration" min="{{dur_min}}" max="{{dur_max}}" step="0.5" value="2.0" oninput="showVal('duration')">
      <span class="val" id="duration-val">2.0 s</span>
    </div>
    <div style="margin-top:10px;">
      <button class="btn" onclick="sendMove()">Move to Target</button>
      <button class="btn btn-secondary" onclick="goHome()">Go Home</button>
    </div>
    <div id="status" class="status"></div>
  </div>
</div>

<script>
  let mode = 'position_only';

  function setMode(m) {
    mode = m;
    document.getElementById('btn-pos-only').classList.toggle('active', m === 'position_only');
    document.getElementById('btn-full-pose').classList.toggle('active', m === 'full_pose');
    document.getElementById('ori-card').style.display = (m === 'full_pose') ? 'block' : 'none';
  }

  function showVal(id) {
    const el = document.getElementById(id);
    const val = el.value;
    const disp = document.getElementById(id + '-val');
    if (id === 'gripper') disp.textContent = val + '%';
    else if (id === 'duration') disp.textContent = val + ' s';
    else disp.textContent = val;
  }

  function setStatus(msg, isError) {
    const s = document.getElementById('status');
    s.textContent = msg;
    s.className = 'status ' + (isError ? 'err' : 'ok');
  }

  function clearStatus() {
    const s = document.getElementById('status');
    s.className = 'status';
    s.textContent = '';
  }

  const urlParams = new URLSearchParams(window.location.search);
  const pageToken = urlParams.get('token');
  if (pageToken) {
    localStorage.setItem('arm_token', pageToken);
  }
  const storedToken = localStorage.getItem('arm_token') || '';

  async function apiPost(path, payload) {
    const r = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Auth-Token': storedToken },
      credentials: 'same-origin',
      body: JSON.stringify(payload)
    });
    if (!r.ok) {
      const text = await r.text();
      throw new Error('HTTP ' + r.status + ': ' + text);
    }
    return r.json();
  }

  async function apiGet(path) {
    const r = await fetch(path, { credentials: 'same-origin', headers: { 'X-Auth-Token': storedToken } });
    if (!r.ok) {
      const text = await r.text();
      throw new Error('HTTP ' + r.status + ': ' + text);
    }
    return r.json();
  }

  async function sendMove() {
    clearStatus();
    const payload = {
      x: parseFloat(document.getElementById('x').value),
      y: parseFloat(document.getElementById('y').value),
      z: parseFloat(document.getElementById('z').value),
      position_only: mode === 'position_only',
      duration: parseFloat(document.getElementById('duration').value),
      lock_wrist_flex: document.getElementById('lock-wrist-flex').checked,
      lock_wrist_flex_val: parseFloat(document.getElementById('lock-wrist-flex-val').value),
      lock_wrist_roll: document.getElementById('lock-wrist-roll').checked,
      lock_wrist_roll_val: parseFloat(document.getElementById('lock-wrist-roll-val').value),
    };
    if (mode === 'full_pose') {
      payload.rx = parseFloat(document.getElementById('rx').value);
      payload.ry = parseFloat(document.getElementById('ry').value);
      payload.rz = parseFloat(document.getElementById('rz').value);
    }
    try {
      const data = await apiPost('/api/move', payload);
      if (data.success) {
        const err = data.result.error.position_cm;
        const errMag = Math.sqrt(err[0]**2 + err[1]**2 + err[2]**2).toFixed(2);
        setStatus('Move complete. Position error: ' + errMag + ' cm', false);
      } else {
        setStatus('Move failed: ' + data.error, true);
      }
    } catch (e) {
      setStatus('Request failed: ' + e.message, true);
    }
  }

  async function sendGripper() {
    const opening = parseFloat(document.getElementById('gripper').value);
    try {
      await apiPost('/api/gripper', { opening });
    } catch (e) { /* ignore gripper errors */ }
  }

  async function goHome() {
    clearStatus();
    try {
      const data = await apiPost('/api/home', {});
      setStatus(data.success ? 'Returned home' : 'Home failed: ' + data.error, !data.success);
    } catch (e) {
      setStatus('Request failed: ' + e.message, true);
    }
  }

  async function connectArm() {
    const alias = document.getElementById('arm-select').value;
    if (!alias) return;
    clearStatus();
    try {
      const data = await apiPost('/api/connect', { alias });
      setStatus(data.success ? 'Connected to ' + alias : 'Connect failed: ' + data.error, !data.success);
      updateStatus();
    } catch (e) {
      setStatus('Connect failed: ' + e.message, true);
    }
  }

  async function disconnectArm() {
    clearStatus();
    try {
      const data = await apiPost('/api/disconnect', {});
      setStatus(data.success ? 'Disconnected' : 'Disconnect failed: ' + data.error, !data.success);
      updateStatus();
    } catch (e) {
      setStatus('Disconnect failed: ' + e.message, true);
    }
  }

  async function updatePose() {
    try {
      const data = await apiGet('/api/pose');
      if (data.success && data.pose) {
        const p = data.pose.position_cm;
        const o = data.pose.orientation_deg || ['-', '-', '-'];
        const items = [
          {k:'X', v:p[0].toFixed(1)}, {k:'Y', v:p[1].toFixed(1)}, {k:'Z', v:p[2].toFixed(1)},
          {k:'RX', v:(typeof o[0]==='number'?o[0].toFixed(1):o[0])},
          {k:'RY', v:(typeof o[1]==='number'?o[1].toFixed(1):o[1])},
          {k:'RZ', v:(typeof o[2]==='number'?o[2].toFixed(1):o[2])},
        ];
        document.getElementById('pose-display').innerHTML = items.map(i =>
          '<div class="pose-item"><div class="k">' + i.k + '</div><div class="v">' + i.v + '</div></div>'
        ).join('');
      }
    } catch (e) {}
  }

  async function updateStatus() {
    try {
      const data = await apiGet('/api/status');
      document.getElementById('conn-status').textContent =
        data.connected ? 'Connected (' + (data.serial_id || 'unknown') + ')' : 'Disconnected';
    } catch (e) {
      document.getElementById('conn-status').textContent = 'Unable to reach server';
    }
  }

  async function loadArmList() {
    try {
      const data = await apiGet('/api/arms');
      const sel = document.getElementById('arm-select');
      sel.innerHTML = '';
      data.arms.forEach(a => {
        const opt = document.createElement('option');
        opt.value = a;
        opt.textContent = a;
        sel.appendChild(opt);
      });
    } catch (e) {}
  }

  loadArmList();
  setInterval(updatePose, 500);
  setInterval(updateStatus, 2000);
  updatePose();
  updateStatus();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
@require_auth
def index():
    return render_template_string(
        CONTROL_PAGE,
        x_min=RANGE_X[0], x_max=RANGE_X[1],
        y_min=RANGE_Y[0], y_max=RANGE_Y[1],
        z_min=RANGE_Z[0], z_max=RANGE_Z[1],
        rx_min=RANGE_RX[0], rx_max=RANGE_RX[1],
        ry_min=RANGE_RY[0], ry_max=RANGE_RY[1],
        rz_min=RANGE_RZ[0], rz_max=RANGE_RZ[1],
        dur_min=RANGE_DURATION[0], dur_max=RANGE_DURATION[1],
    )


@app.route("/api/arms")
@require_auth
def api_arms():
    return jsonify({"success": True, "arms": discover_arm_aliases()})


@app.route("/api/status")
@require_auth
def api_status():
    global arm_manager
    ready = arm_manager is not None and arm_manager.is_ready()
    serial_id = None
    if arm_manager is not None:
        serial_id = getattr(arm_manager.arm, "connection", None) and arm_manager.arm.connection.serial_id
    return jsonify({"success": True, "connected": ready, "serial_id": serial_id})


@app.route("/api/pose")
@require_auth
def api_pose():
    global arm_manager
    if arm_manager is None or not arm_manager.is_ready():
        return jsonify({"success": False, "error": "Arm not connected"}), 503
    try:
        pose = arm_manager.get_pose()
        return jsonify({"success": True, "pose": pose})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/connect", methods=["POST"])
@require_auth
def api_connect():
    global arm_manager
    data = request.get_json(force=True) or {}
    alias = data.get("alias", "white_1")
    try:
        serial_id, device_name = resolve_arm_alias(alias)
    except FileNotFoundError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    with _manager_lock:
        if arm_manager is not None:
            arm_manager.stop()
        arm_manager = ArmManager(serial_id=serial_id, device_name=device_name)
        try:
            arm_manager.start()
        except RuntimeError as e:
            arm_manager = None
            return jsonify({"success": False, "error": str(e)}), 500

    return jsonify({"success": True, "serial_id": serial_id})


@app.route("/api/disconnect", methods=["POST"])
@require_auth
def api_disconnect():
    global arm_manager
    with _manager_lock:
        if arm_manager is not None:
            arm_manager.stop()
            arm_manager = None
    return jsonify({"success": True})


@app.route("/api/gripper", methods=["POST"])
@require_auth
def api_gripper():
    global arm_manager
    if arm_manager is None or not arm_manager.is_ready():
        return jsonify({"success": False, "error": "Arm not connected"}), 503
    data = request.get_json(force=True) or {}
    try:
        opening = float(data.get("opening", 50))
        opening = max(0.0, min(100.0, opening))
        arm_manager.set_gripper(opening)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/move", methods=["POST"])
@require_auth
def api_move():
    global arm_manager
    if arm_manager is None or not arm_manager.is_ready():
        return jsonify({"success": False, "error": "Arm not connected"}), 503
    data = request.get_json(force=True) or {}
    try:
        locked = {}
        if data.get("lock_wrist_flex"):
            locked[3] = float(data.get("lock_wrist_flex_val", 0))
        if data.get("lock_wrist_roll"):
            locked[4] = float(data.get("lock_wrist_roll_val", 90))

        result = arm_manager.move_to_pose(
            x=float(data["x"]),
            y=float(data["y"]),
            z=float(data["z"]),
            rx=float(data.get("rx", 0)),
            ry=float(data.get("ry", -90)),
            rz=float(data.get("rz", 0)),
            position_only=bool(data.get("position_only", True)),
            duration=float(data.get("duration", 2.0)),
            locked_joints=locked if locked else None,
            max_position_error_cm=2.0,
        )
        return jsonify({"success": True, "result": result})
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": f"Unexpected error: {e}"}), 500


@app.route("/api/home", methods=["POST"])
@require_auth
def api_home():
    global arm_manager
    if arm_manager is None or not arm_manager.is_ready():
        return jsonify({"success": False, "error": "Arm not connected"}), 503
    try:
        result = arm_manager.go_home(duration=3.0)
        return jsonify({"success": True, "result": result})
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": f"Unexpected error: {e}"}), 500


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="SO-100 Arm Web Control Server")
    parser.add_argument("--alias", default=None, help="Auto-connect to this alias on startup")
    parser.add_argument("--device", default=None, help="Direct device path (overrides alias)")
    args = parser.parse_args()

    global arm_manager
    if args.device:
        arm_manager = ArmManager(serial_id="direct", device_name=args.device)
        arm_manager.start()
    elif args.alias:
        serial_id, device_name = resolve_arm_alias(args.alias)
        arm_manager = ArmManager(serial_id=serial_id, device_name=device_name)
        arm_manager.start()

    port = find_free_port(start=5201)
    local_ip = _get_local_ip()

    def _print_urls():
        time.sleep(0.5)
        print()
        print(f" * Arm control URL: http://127.0.0.1:{port}/?token={VALID_TOKEN}")
        print(f" * Arm control URL: http://{local_ip}:{port}/?token={VALID_TOKEN}")
        print("   (Ctrl+Click the URL in the VS Code terminal to open)")
        print()

    threading.Thread(target=_print_urls, daemon=True).start()

    try:
        app.run(host="0.0.0.0", port=port, threaded=True)
    finally:
        with _manager_lock:
            if arm_manager is not None:
                arm_manager.stop()


if __name__ == "__main__":
    main()
