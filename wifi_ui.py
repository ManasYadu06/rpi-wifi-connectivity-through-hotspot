from flask import Flask, render_template_string, request, redirect, Response
import subprocess
import os
import time

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CRED_FILE = os.path.join(BASE_DIR, "wifi_credentials.conf")

# Captive portal probe URLs from Android, iOS, Windows, Firefox
CAPTIVE_PROBE_PATHS = [
    "/generate_204",           # Android
    "/gen_204",                # Android alternate
    "/hotspot-detect.html",    # Apple iOS/macOS
    "/library/test/success.html",  # Apple alternate
    "/ncsi.txt",               # Windows
    "/connecttest.txt",        # Windows 11
    "/success.txt",            # Firefox
    "/canonical.html",         # Ubuntu
]

HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Wi-Fi Setup</title>
  <style>
    body { font-family: sans-serif; max-width: 420px; margin: 40px auto; padding: 0 16px; }
    input, select { width: 100%; padding: 8px; margin: 6px 0 14px; box-sizing: border-box; font-size: 16px; }
    button { padding: 10px 20px; font-size: 16px; cursor: pointer; }
    .error { color: red; background: #fee; padding: 10px; border-radius: 4px; }
    .tip { font-size: 13px; color: #666; margin-top: 20px; background: #f5f5f5; padding: 10px; border-radius: 4px; }
  </style>
</head>
<body>
  <h2>📶 Wi-Fi Setup</h2>

  {% if error %}
  <p class="error">{{ error }}</p>
  {% endif %}

  <form method="get">
    <button type="submit">↻ Refresh Networks</button>
  </form>
  <br>
  <form method="post">
    <label>Available Networks:</label>
    <select name="ssid_select">
      <option value="">-- select --</option>
      {% for n in networks %}
      <option value="{{ n }}">{{ n }}</option>
      {% endfor %}
    </select>

    <label>Manual SSID (if not listed above):</label>
    <input type="text" name="ssid_manual" placeholder="Network name">

    <label>Password:</label>
    <input type="password" name="password" placeholder="Password">

    <button type="submit">Save &amp; Connect</button>
  </form>

  <hr>
  <h3>Saved Networks</h3>
  {% if saved %}
  <ul>
    {% for s in saved %}
    <li>
      {{ s }}
      <form method="post" style="display:inline">
        <input type="hidden" name="forget" value="{{ s }}">
        <button>Forget</button>
      </form>
    </li>
    {% endfor %}
  </ul>
  {% else %}
  <p>No saved networks.</p>
  {% endif %}

  <div class="tip">
    💡 You can also reach this page at <strong>http://wifi.setup</strong>
  </div>
</body>
</html>
"""

# -------------------------
# Utility functions
# -------------------------

def scan_wifi():
    try:
        result = subprocess.check_output(
            ["nmcli", "-t", "-f", "SSID", "dev", "wifi", "list"],
            stderr=subprocess.DEVNULL
        ).decode()
        return sorted(set([line for line in result.splitlines() if line]))
    except:
        return []

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
        capture_output=True, text=True
    )
    return result.returncode == 0, result.stdout + result.stderr

# -------------------------
# Captive portal intercept
# -------------------------

@app.before_request
def captive_portal_intercept():
    """
    Intercept OS captive portal probes and redirect to setup page.
    This triggers the automatic popup on Android, iOS, Windows.
    """
    path = request.path
    host = request.host

    # If it's a known probe path, redirect to our page
    if path in CAPTIVE_PROBE_PATHS:
        return redirect("http://wifi.setup/", 302)

    # If it's a request to any external host (not our Pi), redirect
    # This catches typing any URL in browser
    if host not in ("wifi.setup", "wifi-setup.local", "10.0.0.5"):
        return redirect("http://wifi.setup/", 302)

# -------------------------
# Routes
# -------------------------

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
            ok, msg = connect_now(ssid, pwd)
            if ok:
                subprocess.Popen(["reboot"])
                return "<h2>✅ Connected! Rebooting...</h2><p>You can close this tab.</p>"
            else:
                # Restore hotspot so user can try again
                subprocess.run(["systemctl", "stop", "NetworkManager"], check=False)
                time.sleep(1)
                subprocess.run(["ip", "addr", "add", "10.0.0.5/24", "dev", "wlan0"], check=False)
                subprocess.run(["ip", "link", "set", "wlan0", "up"], check=False)
                subprocess.run(["systemctl", "restart", "dnsmasq"], check=False)
                subprocess.run(["systemctl", "restart", "hostapd"], check=False)
                error = f"Connection failed. Check SSID/password. Detail: {msg}"
        else:
            error = "Please enter both SSID and password."

    return render_template_string(
        HTML,
        networks=scan_wifi(),
        saved=saved.keys(),
        error=error
    )

# -------------------------
# Start server on port 80
# -------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
