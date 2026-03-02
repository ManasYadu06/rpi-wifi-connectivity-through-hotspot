#!/bin/bash

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$BASE_DIR/wifi_boot.log"

echo "===== BOOT START $(date) =====" >> "$LOG"

# -------------------------------------------------
# Stop hotspot services first
# -------------------------------------------------
systemctl stop hostapd >> "$LOG" 2>&1
systemctl stop dnsmasq >> "$LOG" 2>&1

# -------------------------------------------------
# Start NetworkManager
# -------------------------------------------------
systemctl start NetworkManager >> "$LOG" 2>&1

echo "Waiting up to 2 minutes for WiFi connection..." >> "$LOG"

MAX_WAIT=120       # 2 minutes
INTERVAL=5         # check every 5 seconds
ELAPSED=0

while [ $ELAPSED -lt $MAX_WAIT ]; do
    STATE=$(nmcli -t -f GENERAL.STATE device show wlan0 | cut -d: -f2)

    if echo "$STATE" | grep -q "100 (connected)"; then
        IP=$(ip -4 addr show wlan0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
        echo "WiFi connected successfully with IP $IP" >> "$LOG"
        exit 0
    fi

    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
done

echo "WiFi did not connect within 2 minutes." >> "$LOG"
echo "Starting hotspot..." >> "$LOG"

# -------------------------------------------------
# Stop NetworkManager before AP mode
# -------------------------------------------------
systemctl stop NetworkManager >> "$LOG" 2>&1

# -------------------------------------------------
# Configure static IP for hotspot
# -------------------------------------------------
ip addr flush dev wlan0
ip addr add 10.0.0.5/24 dev wlan0
ip link set wlan0 up

# -------------------------------------------------
# Start hotspot services
# -------------------------------------------------
systemctl start dnsmasq >> "$LOG" 2>&1
systemctl start hostapd >> "$LOG" 2>&1

echo "Hotspot started. Launching UI..." >> "$LOG"

# -------------------------------------------------
# Start Flask UI in background
# -------------------------------------------------
"$BASE_DIR/venv/bin/python" "$BASE_DIR/wifi_ui.py" >> "$LOG" 2>&1 &

exit 0
