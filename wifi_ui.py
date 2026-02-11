from flask import Flask, render_template_string, request, redirect
import subprocess
import os
import time

app = Flask(__name__)

CRED_FILE = "/home/pi/wifi_credentials.conf"

HTML = """
<!doctype html>
<html>
<head>
<title>Wi-Fi Setup</title>
</head>
<body>
<h2>Wi-Fi Configuration</h2>

<form method="get">
<button type="submit">Refresh Networks</button>
</form>

<form method="post">
<p>
<label>Available Networks:</label><br>
<select name="ssid_select">
<option value="">-- select --</option>
{% for n in networks %}
<option value="{{n}}">{{n}}</option>
{% endfor %}
</select>
</p>

<p>
<label>Manual SSID (overrides selection):</label><br>
<input type="text" name="ssid_manual">
</p>

<p>
<label>Password:</label><br>
<input type="password" name="password">
</p>

<button type="submit">Save & Connect</button>
</form>

<hr>
<h3>Saved Networks</h3>

{% if saved %}
<ul>
{% for s in saved %}
<li>
{{s}}
<form method="post" style="display:inline">
<input type="hidden" name="forget" value="{{s}}">
<button>Forget</button>
</form>
</li>
{% endfor %}
</ul>
{% else %}
<p>No saved networks</p>
{% endif %}

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
        ssids = sorted(set([line for line in result.splitlines() if line]))
        return ssids
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
    # Stop hotspot
    subprocess.run(["systemctl", "stop", "hostapd"], check=False)
    subprocess.run(["systemctl", "stop", "dnsmasq"], check=False)

    # Start NetworkManager
    subprocess.run(["systemctl", "start", "NetworkManager"], check=False)
    time.sleep(3)

    # Attempt connection
    result = subprocess.run(
        ["nmcli", "dev", "wifi", "connect", ssid, "password", password],
        capture_output=True,
        text=True
    )

    return result.returncode == 0, result.stdout + result.stderr


# -------------------------
# Routes
# -------------------------

@app.route("/", methods=["GET", "POST"])
def index():
    saved = read_saved()

    if request.method == "POST":

        # Forget logic
        if "forget" in request.form:
            saved.pop(request.form["forget"], None)
            write_saved(saved)
            return redirect("/")

        ssid = request.form["ssid_manual"] or request.form["ssid_select"]
        pwd = request.form["password"]

        if ssid and pwd:
            saved[ssid] = pwd
            write_saved(saved)

            ok, msg = connect_now(ssid, pwd)

            if ok:
                subprocess.run(["reboot"])
                import os
                os._exit(0)
            else:
                # Fallback to hotspot
                subprocess.run(["systemctl", "stop", "NetworkManager"], check=False)
                subprocess.run(["systemctl", "restart", "dnsmasq"], check=False)
                subprocess.run(["systemctl", "restart", "hostapd"], check=False)

                return f"""
                <h3>Connection failed.</h3>
                <pre>{msg}</pre>
                <p>Hotspot restored.</p>
                """

        return redirect("/")

    return render_template_string(
        HTML,
        networks=scan_wifi(),
        saved=saved.keys()
    )


# -------------------------
# Start server
# -------------------------

app.run(host="0.0.0.0", port=8080)
