from flask import Flask, render_template_string, request, redirect, Response, jsonify
import subprocess
import os
import time
import threading
import signal

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CRED_FILE = os.path.join(BASE_DIR, "wifi_credentials.conf")

# Captive portal probe URLs from Android, iOS, Windows, Firefox
CAPTIVE_PROBE_PATHS = [
    "/generate_204",
    "/gen_204",
    "/hotspot-detect.html",
    "/library/test/success.html",
    "/ncsi.txt",
    "/connecttest.txt",
    "/success.txt",
    "/canonical.html",
]

# -------------------------
# Scan cache (30s TTL)
# -------------------------
_scan_cache = {"networks": [], "ts": 0}
_scan_lock = threading.Lock()

def scan_wifi():
    now = time.time()
    with _scan_lock:
        if now - _scan_cache["ts"] < 30 and _scan_cache["networks"]:
            return _scan_cache["networks"]
    try:
        result = subprocess.check_output(
            ["nmcli", "-t", "-f", "SSID", "dev", "wifi", "list"],
            stderr=subprocess.DEVNULL,
            timeout=10
        ).decode()
        networks = sorted(set([line for line in result.splitlines() if line]))
    except Exception:
        networks = []
    with _scan_lock:
        _scan_cache["networks"] = networks
        _scan_cache["ts"] = time.time()
    return networks

# -------------------------
# Camera stream state
# -------------------------
_cam_lock    = threading.Lock()
_cam_proc    = None   # rpicam-vid subprocess
_cam_clients = 0      # number of active /stream consumers

def _start_camera():
    """Launch rpicam-vid piping MJPEG to stdout. Idempotent."""
    global _cam_proc
    with _cam_lock:
        if _cam_proc and _cam_proc.poll() is None:
            return  # already running
        _cam_proc = subprocess.Popen(
            [
                "rpicam-vid",
                "--width",  "1920",
                "--height", "1080",
                "--framerate", "15",
                "--codec", "mjpeg",
                "--inline",          # embed JPEG headers in every frame
                "--nopreview",
                "-t", "0",           # run indefinitely
                "-o", "-",           # output to stdout
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

def _stop_camera():
    """Kill rpicam-vid if running."""
    global _cam_proc
    with _cam_lock:
        if _cam_proc and _cam_proc.poll() is None:
            _cam_proc.send_signal(signal.SIGTERM)
            try:
                _cam_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                _cam_proc.kill()
        _cam_proc = None

def _mjpeg_frames():
    """
    Generator that reads MJPEG frames from rpicam-vid stdout and
    yields them as multipart/x-mixed-replace parts.
    Stops automatically when the client disconnects.
    """
    global _cam_clients
    with _cam_lock:
        _cam_clients += 1

    try:
        buf = b""
        SOI = b"\xff\xd8"   # JPEG start
        EOI = b"\xff\xd9"   # JPEG end

        while True:
            with _cam_lock:
                proc = _cam_proc
            if proc is None or proc.poll() is not None:
                break

            chunk = proc.stdout.read(8192)
            if not chunk:
                break
            buf += chunk

            # Extract complete JPEG frames from the buffer
            while True:
                start = buf.find(SOI)
                if start == -1:
                    buf = b""
                    break
                end = buf.find(EOI, start + 2)
                if end == -1:
                    buf = buf[start:]   # keep partial frame
                    break
                frame = buf[start: end + 2]
                buf   = buf[end + 2:]
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                )
    finally:
        with _cam_lock:
            _cam_clients -= 1
            # Auto-stop camera when last viewer leaves
            if _cam_clients <= 0:
                _cam_clients = 0
        _stop_camera()

# -------------------------
# Utility functions
# -------------------------

def read_saved():
    if not os.path.exists(CRED_FILE):
        return {}
    data = {}
    with open(CRED_FILE) as f:
        for line in f:
            if "=" in line:
                ssid, pwd = line.strip().split("=", 1)
                data[ssid] = pwd
    return data

def write_saved(data):
    with open(CRED_FILE, "w") as f:
        for s, p in data.items():
            f.write(f"{s}={p}\n")

def connect_now(ssid, password):
    subprocess.run(["systemctl", "stop", "hostapd"], check=False)
    subprocess.run(["systemctl", "stop", "dnsmasq"], check=False)
    subprocess.run(["systemctl", "start", "NetworkManager"], check=False)
    time.sleep(3)
    result = subprocess.run(
        ["nmcli", "dev", "wifi", "connect", ssid, "password", password],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        return False, result.stdout + result.stderr

    # Confirm a routable IP was actually assigned (not link-local 169.254.x.x)
    for _ in range(10):
        time.sleep(2)
        ip_out = subprocess.run(
            ["ip", "-4", "addr", "show", "wlan0"],
            capture_output=True, text=True
        ).stdout
        import re
        ips = re.findall(r'inet\s(\d+\.\d+\.\d+\.\d+)', ip_out)
        routable = [ip for ip in ips if not ip.startswith("169.254.")]
        if routable:
            return True, routable[0]

    return False, "nmcli connected but no routable IP assigned (DHCP may have failed)"

def restore_hotspot():
    subprocess.run(["systemctl", "stop", "NetworkManager"], check=False)
    time.sleep(1)
    subprocess.run(["ip", "addr", "add", "10.0.0.5/24", "dev", "wlan0"], check=False)
    subprocess.run(["ip", "link", "set", "wlan0", "up"], check=False)
    subprocess.run(["systemctl", "restart", "dnsmasq"], check=False)
    subprocess.run(["systemctl", "restart", "hostapd"], check=False)

# -------------------------
# Captive portal intercept
# -------------------------

@app.before_request
def captive_portal_intercept():
    path = request.path
    host = request.host.split(":")[0]  # strip port so 10.0.0.5:80 still matches

    OUR_HOSTS = {"wifi.setup", "wifi-setup.local", "10.0.0.5"}

    # Never intercept camera or stream routes
    if path.startswith("/camera") or path.startswith("/stream"):
        return

    # Known OS probe paths — respond with 204/200 first so the OS
    # marks the portal as detected, then redirect to our page.
    # This avoids the race where the OS fires a 302 before DNS resolves.
    if path in ("/generate_204", "/gen_204"):
        # Android expects HTTP 204 to confirm internet; we return 302 to trigger browser popup
        return redirect("http://10.0.0.5/", 302)

    if path in CAPTIVE_PROBE_PATHS:
        return redirect("http://10.0.0.5/", 302)

    # Any request aimed at an external host → redirect to our IP directly
    # (avoids DNS resolution race on first request)
    if host not in OUR_HOSTS:
        return redirect("http://10.0.0.5/", 302)

# -------------------------
# API: Test connection (no reboot)
# -------------------------

@app.route("/test", methods=["POST"])
def test_connection():
    ssid = request.form.get("ssid_manual") or request.form.get("ssid_select")
    pwd = request.form.get("password", "")

    if not ssid or not pwd:
        return jsonify({"ok": False, "msg": "Please enter both SSID and password."})

    ok, result = connect_now(ssid, pwd)

    if ok:
        # Save credentials on successful test
        saved = read_saved()
        saved[ssid] = pwd
        write_saved(saved)
        restore_hotspot()
        return jsonify({"ok": True, "msg": f"✅ Connected successfully (IP: {result}). Credentials saved. You can now click Save & Connect to reboot."})
    else:
        restore_hotspot()
        return jsonify({"ok": False, "msg": f"❌ Connection failed: {result}"})

# -------------------------
# Camera page + stream routes
# -------------------------

CAMERA_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Camera View — StatCams</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: #111; color: #eee; font-family: sans-serif; min-height: 100vh; display: flex; flex-direction: column; }

    .topbar {
      display: flex; align-items: center; gap: 12px;
      padding: 12px 16px; background: #1a1a1a; border-bottom: 1px solid #333;
      flex-shrink: 0;
    }
    .topbar a { color: #aaa; text-decoration: none; font-size: 22px; line-height: 1; }
    .topbar a:hover { color: #fff; }
    .topbar h2 { font-size: 16px; font-weight: 600; flex: 1; }
    .badge {
      font-size: 11px; padding: 3px 8px; border-radius: 20px; font-weight: 600;
      background: #333; color: #aaa;
    }
    .badge.live { background: #c00; color: #fff; animation: pulse 1.4s infinite; }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.5} }

    .viewport {
      flex: 1; display: flex; align-items: center; justify-content: center;
      padding: 12px; background: #111;
    }
    #streamImg {
      display: none;
      max-width: 100%; max-height: calc(100vh - 130px);
      border-radius: 6px; border: 2px solid #333;
      object-fit: contain;
    }
    #placeholder {
      text-align: center; color: #555;
    }
    #placeholder .icon { font-size: 64px; margin-bottom: 12px; }
    #placeholder p { font-size: 14px; }

    .controls {
      padding: 12px 16px; background: #1a1a1a; border-top: 1px solid #333;
      display: flex; gap: 10px; justify-content: center; flex-shrink: 0;
    }
    button {
      padding: 10px 24px; font-size: 15px; border: none; border-radius: 6px; cursor: pointer; font-weight: 600;
    }
    #startBtn { background: #0070f3; color: #fff; }
    #startBtn:hover { background: #005cd1; }
    #startBtn:disabled { background: #444; color: #888; cursor: not-allowed; }
    #stopBtn  { background: #333; color: #eee; display: none; }
    #stopBtn:hover  { background: #444; }

    .hint { font-size: 12px; color: #555; text-align: center; padding: 6px 0 10px; }
  </style>
</head>
<body>

<div class="topbar">
  <a href="/" id="backBtn" title="Back to Wi-Fi Setup">←</a>
  <h2>📷 Camera View</h2>
  <span class="badge" id="liveBadge">STOPPED</span>
</div>

<div class="viewport">
  <div id="placeholder">
    <div class="icon">📷</div>
    <p>Tap <strong>Start Stream</strong> to preview camera angle</p>
  </div>
  <img id="streamImg" alt="Live camera feed">
</div>

<div class="controls">
  <button id="startBtn">▶ Start Stream</button>
  <button id="stopBtn">⏹ Stop Stream</button>
</div>
<p class="hint">1080p · 15 fps · Pi Camera v3</p>

<script>
  var streaming = false;

  function startStream() {
    streaming = true;
    document.getElementById('placeholder').style.display = 'none';
    document.getElementById('startBtn').disabled = true;
    document.getElementById('stopBtn').style.display = 'inline-block';
    document.getElementById('liveBadge').textContent = 'LIVE';
    document.getElementById('liveBadge').classList.add('live');

    // First call /stream/start to launch rpicam-vid on the Pi
    fetch('/stream/start', { method: 'POST' }).then(function() {
      // Give rpicam-vid ~800ms to open the sensor before connecting
      setTimeout(function() {
        var img = document.getElementById('streamImg');
        img.src = '/stream/feed?' + Date.now();
        img.style.display = 'block';
        img.onerror = function() {
          if (streaming) stopStream(true);
        };
      }, 800);
    });
  }

  function stopStream(isError) {
    streaming = false;
    var img = document.getElementById('streamImg');
    img.style.display = 'none';
    img.src = '';
    document.getElementById('placeholder').style.display = 'block';
    document.getElementById('startBtn').disabled = false;
    document.getElementById('stopBtn').style.display = 'none';
    document.getElementById('liveBadge').textContent = 'STOPPED';
    document.getElementById('liveBadge').classList.remove('live');
    fetch('/stream/stop', { method: 'POST' });
  }

  document.getElementById('startBtn').addEventListener('click', startStream);
  document.getElementById('stopBtn').addEventListener('click', function() { stopStream(false); });

  // Stop stream when leaving page (back button, close tab, navigate away)
  window.addEventListener('pagehide', function() {
    if (streaming) fetch('/stream/stop', { method: 'POST', keepalive: true });
  });

  // Back button: stop stream then navigate
  document.getElementById('backBtn').addEventListener('click', function(e) {
    e.preventDefault();
    if (streaming) {
      fetch('/stream/stop', { method: 'POST' }).finally(function() {
        window.location.href = '/';
      });
    } else {
      window.location.href = '/';
    }
  });
</script>
</body>
</html>
"""

@app.route("/camera")
def camera_page():
    return render_template_string(CAMERA_HTML)

@app.route("/stream/start", methods=["POST"])
def stream_start():
    _start_camera()
    return jsonify({"ok": True})

@app.route("/stream/stop", methods=["POST"])
def stream_stop():
    _stop_camera()
    return jsonify({"ok": True})

@app.route("/stream/feed")
def stream_feed():
    _start_camera()   # idempotent — safe if already running
    return Response(
        _mjpeg_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )

# -------------------------
# Main route
# -------------------------

HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Wi-Fi Setup</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: sans-serif; max-width: 420px; margin: 40px auto; padding: 0 16px; background: #f9f9f9; }
    h2 { margin-bottom: 4px; }
    .card { background: #fff; border-radius: 8px; padding: 16px; margin-bottom: 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.1); }
    input, select { width: 100%; padding: 10px; margin: 6px 0 14px; font-size: 16px; border: 1px solid #ccc; border-radius: 6px; }
    .pw-wrap { position: relative; }
    .pw-wrap input { padding-right: 48px; }
    .pw-toggle {
      position: absolute; right: 10px; top: 50%; transform: translateY(-80%);
      background: none; border: none; cursor: pointer; font-size: 18px; padding: 4px;
    }
    button { padding: 10px 18px; font-size: 15px; cursor: pointer; border: none; border-radius: 6px; }
    .btn-primary { background: #0070f3; color: #fff; width: 100%; margin-top: 4px; }
    .btn-primary:disabled { background: #aaa; cursor: not-allowed; }
    .btn-secondary { background: #eee; color: #333; }
    .btn-test { background: #e8f4fd; color: #0070f3; border: 1px solid #0070f3; width: 100%; margin-top: 4px; }
    .btn-test:disabled { opacity: 0.5; cursor: not-allowed; }
    .error { color: red; background: #fee; padding: 10px; border-radius: 6px; margin-bottom: 12px; }
    .success { color: green; background: #efe; padding: 10px; border-radius: 6px; margin-bottom: 12px; }
    .info { color: #555; background: #f0f0f0; padding: 10px; border-radius: 6px; margin-bottom: 12px; font-size: 14px; }
    .tip { font-size: 13px; color: #666; margin-top: 16px; background: #f5f5f5; padding: 10px; border-radius: 4px; }
    .spinner { display: none; text-align: center; padding: 16px; font-size: 14px; color: #555; }
    .spinner.active { display: block; }
    .spinner-icon { display: inline-block; width: 20px; height: 20px; border: 3px solid #ccc; border-top-color: #0070f3; border-radius: 50%; animation: spin 0.8s linear infinite; vertical-align: middle; margin-right: 8px; }
    @keyframes spin { to { transform: rotate(360deg); } }
    ul { padding-left: 18px; }
    li { margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
    .test-result { margin-top: 10px; padding: 10px; border-radius: 6px; font-size: 14px; display: none; }
    .test-result.ok { background: #efe; color: green; display: block; }
    .test-result.fail { background: #fee; color: red; display: block; }
  </style>
</head>
<body>
  <h2>📶 Wi-Fi Setup</h2>
  <p style="color:#888;font-size:13px;margin-top:0">StatCams Provisioning</p>

  {% if error %}
  <div class="error">{{ error }}</div>
  {% endif %}

  <div class="card">
    <form method="get" style="margin-bottom:10px">
      <button type="submit" class="btn-secondary">↻ Refresh Networks</button>
    </form>

    <form method="post" id="connectForm">
      <label>Available Networks:</label>
      <select name="ssid_select" id="ssid_select">
        <option value="">-- select --</option>
        {% for n in networks %}
        <option value="{{ n }}">{{ n }}</option>
        {% endfor %}
      </select>

      <label>Manual SSID (if not listed):</label>
      <input type="text" name="ssid_manual" id="ssid_manual" placeholder="Network name">

      <label>Password:</label>
      <div class="pw-wrap">
        <input type="password" name="password" id="password" placeholder="Password">
        <button type="button" class="pw-toggle" id="pwToggle" title="Show/hide password">👁</button>
      </div>

      <!-- Test Connection -->
      <button type="button" class="btn-test" id="testBtn">🔍 Test Connection (no reboot)</button>
      <div class="test-result" id="testResult"></div>

      <div class="spinner" id="connectSpinner">
        <span class="spinner-icon"></span> Connecting… this may take up to 30 seconds
      </div>

      <button type="submit" class="btn-primary" id="submitBtn">Save &amp; Connect</button>
    </form>
  </div>

  <div class="card">
    <h3 style="margin-top:0">Saved Networks</h3>
    {% if saved %}
    <ul>
      {% for s in saved %}
      <li>
        <span style="flex:1">{{ s }}</span>
        <form method="post" style="margin:0">
          <input type="hidden" name="forget" value="{{ s }}">
          <button class="btn-secondary" style="padding:4px 10px;font-size:13px">Forget</button>
        </form>
      </li>
      {% endfor %}
    </ul>
    {% else %}
    <p style="color:#888;font-size:14px">No saved networks.</p>
    {% endif %}
  </div>

  <div class="card" style="text-align:center">
    <p style="margin:0 0 10px;font-size:14px;color:#555">Need to check camera angle?</p>
    <a href="/camera" style="display:inline-block;padding:10px 24px;background:#1a1a1a;color:#fff;border-radius:6px;text-decoration:none;font-size:15px;font-weight:600">
      📷 Camera View
    </a>
  </div>

  <div class="tip">
    💡 Also reachable at <strong>http://wifi.setup</strong> or <strong>http://10.0.0.5</strong>
  </div>

<script>
  // Show/hide password toggle
  document.getElementById('pwToggle').addEventListener('click', function() {
    var pw = document.getElementById('password');
    if (pw.type === 'password') {
      pw.type = 'text';
      this.textContent = '🙈';
    } else {
      pw.type = 'password';
      this.textContent = '👁';
    }
  });

  // Loading spinner on form submit
  document.getElementById('connectForm').addEventListener('submit', function(e) {
    var ssid = document.getElementById('ssid_manual').value.trim()
              || document.getElementById('ssid_select').value;
    var pwd  = document.getElementById('password').value;
    if (!ssid || !pwd) return; // let server-side handle validation

    document.getElementById('connectSpinner').classList.add('active');
    document.getElementById('submitBtn').disabled = true;
    document.getElementById('testBtn').disabled   = true;
  });

  // Test connection (AJAX, no reboot)
  document.getElementById('testBtn').addEventListener('click', function() {
    var ssid = document.getElementById('ssid_manual').value.trim()
              || document.getElementById('ssid_select').value;
    var pwd  = document.getElementById('password').value;
    var resultEl = document.getElementById('testResult');

    if (!ssid || !pwd) {
      resultEl.className = 'test-result fail';
      resultEl.textContent = 'Please enter both SSID and password first.';
      return;
    }

    this.disabled = true;
    this.textContent = '⏳ Testing…';
    resultEl.className = 'test-result';
    resultEl.textContent = '';

    var form = new FormData();
    form.append('ssid_manual', document.getElementById('ssid_manual').value.trim());
    form.append('ssid_select', document.getElementById('ssid_select').value);
    form.append('password', pwd);

    fetch('/test', { method: 'POST', body: form })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        resultEl.className = 'test-result ' + (data.ok ? 'ok' : 'fail');
        resultEl.textContent = data.msg;
      })
      .catch(function() {
        resultEl.className = 'test-result fail';
        resultEl.textContent = '❌ Request failed. The Pi may have lost hotspot briefly — please refresh.';
      })
      .finally(function() {
        var btn = document.getElementById('testBtn');
        btn.disabled = false;
        btn.textContent = '🔍 Test Connection (no reboot)';
      });
  });
</script>
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    saved = read_saved()
    error = None

    if request.method == "POST":
        if "forget" in request.form:
            saved.pop(request.form["forget"], None)
            write_saved(saved)
            return redirect("/")

        ssid = request.form.get("ssid_manual") or request.form.get("ssid_select")
        pwd = request.form.get("password", "")

        if ssid and pwd:
            saved[ssid] = pwd
            write_saved(saved)
            ok, result = connect_now(ssid, pwd)
            if ok:
                subprocess.Popen(["reboot"])
                return "<h2>✅ Connected! Rebooting...</h2><p>IP confirmed: {}</p><p>You can close this tab.</p>".format(result)
            else:
                restore_hotspot()
                error = f"Connection failed. Check SSID/password. Detail: {result}"
        else:
            error = "Please enter both SSID and password."

    return render_template_string(
        HTML,
        networks=scan_wifi(),
        saved=saved.keys(),
        error=error
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
