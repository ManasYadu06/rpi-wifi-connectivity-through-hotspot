#!/bin/bash

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$BASE_DIR/wifi_boot.log"
echo "===== BOOT START $(date) =====" >> $LOG

# Stop hotspot services first
systemctl stop hostapd >> $LOG 2>&1
systemctl stop dnsmasq >> $LOG 2>&1

# Start NetworkManager
systemctl start NetworkManager >> $LOG 2>&1

echo "Waiting for WiFi..." >> $LOG
sleep 10

# Check if wlan0 got IP
IP=$(ip -4 addr show wlan0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}')

if [ ! -z "$IP" ]; then
    echo "WiFi connected with IP $IP" >> $LOG
    exit 0
fi

echo "WiFi failed. Starting hotspot..." >> $LOG

# Stop NetworkManager before AP mode
systemctl stop NetworkManager >> $LOG 2>&1

# Give static IP for hotspot
ip addr flush dev wlan0
ip addr add 10.0.0.5/24 dev wlan0
ip link set wlan0 up

# Start hotspot services
systemctl start dnsmasq >> $LOG 2>&1
systemctl start hostapd >> $LOG 2>&1

echo "Hotspot started. Launching UI..." >> $LOG

# Start Flask UI in background
"$BASE_DIR/venv/bin/python" "$BASE_DIR/wifi_ui.py" >> "$LOG" 2>&1 &

exit 0

