#!/bin/bash

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$BASE_DIR/wifi_boot.log"
DEPLOY_FLAG="$BASE_DIR/deployed.flag"

echo "===== BOOT START $(date) =====" >> "$LOG"

# ------------------------------------------------
# Wait for NetworkManager to be ready
# ------------------------------------------------
echo "Waiting for NetworkManager..." >> "$LOG"

while ! systemctl is-active --quiet NetworkManager; do
    sleep 2
done

echo "NetworkManager ready." >> "$LOG"


# ------------------------------------------------
# Deployment Mode Check
# ------------------------------------------------
if [ -f "$DEPLOY_FLAG" ]; then
    echo "Deployment mode detected. Hotspot disabled." >> "$LOG"

    systemctl stop hostapd >> "$LOG" 2>&1
    systemctl stop dnsmasq >> "$LOG" 2>&1
    systemctl start NetworkManager >> "$LOG" 2>&1

    echo "Waiting for venue WiFi..." >> "$LOG"

    while true; do
        STATE=$(nmcli -t -f GENERAL.STATE device show wlan0 | cut -d: -f2)

        if echo "$STATE" | grep -q "100 (connected)"; then
            IP=$(ip -4 addr show wlan0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
            echo "Venue WiFi connected with IP $IP" >> "$LOG"
            exit 0
        fi

        sleep 10
    done
fi


# ------------------------------------------------
# Function: Check if any client is connected to hotspot
# ------------------------------------------------
hotspot_has_clients() {
    # iw station dump lists all connected stations on wlan0
    local clients
    clients=$(iw dev wlan0 station dump 2>/dev/null | grep -c "^Station")
    [ "$clients" -gt 0 ]
}


# ------------------------------------------------
# Function: Try WiFi
# ------------------------------------------------
try_wifi() {

    systemctl stop hostapd >> "$LOG" 2>&1
    systemctl stop dnsmasq >> "$LOG" 2>&1
    systemctl start NetworkManager >> "$LOG" 2>&1

    echo "Trying WiFi for 2 minutes..." >> "$LOG"

    MAX_WAIT=120
    INTERVAL=5
    ELAPSED=0

    while [ $ELAPSED -lt $MAX_WAIT ]; do

        STATE=$(nmcli -t -f GENERAL.STATE device show wlan0 | cut -d: -f2)

        if echo "$STATE" | grep -q "100 (connected)"; then
            # Confirm an IP was actually assigned via DHCP, not just link-local
            IP=$(ip -4 addr show wlan0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | grep -v '^169\.254\.')
            if [ -n "$IP" ]; then
                echo "WiFi connected with IP $IP" >> "$LOG"
                return 0
            else
                echo "nmcli reports connected but no routable IP yet, waiting..." >> "$LOG"
            fi
        fi

        sleep $INTERVAL
        ELAPSED=$((ELAPSED + INTERVAL))

    done

    return 1
}


# ------------------------------------------------
# Function: Start Hotspot
# ------------------------------------------------
start_hotspot() {

    echo "Starting hotspot..." >> "$LOG"
   
    systemctl stop NetworkManager >> "$LOG" 2>&1
    sleep 3
    ip addr flush dev wlan0
    ip addr add 10.0.0.5/24 dev wlan0
    ip link set wlan0 up

    systemctl start dnsmasq >> "$LOG" 2>&1
    systemctl start hostapd >> "$LOG" 2>&1

    # wifi_ui.py is now managed by wifi-ui.service (Restart=always)
    # Just ensure it's running; systemd will keep it alive
    systemctl start wifi-ui >> "$LOG" 2>&1
}


# ------------------------------------------------
# Initial WiFi Attempt
# ------------------------------------------------
if try_wifi; then
    exit 0
fi


# ------------------------------------------------
# If WiFi Failed → Start Hotspot Mode
# ------------------------------------------------
start_hotspot

HOTSPOT_RETRY_INTERVAL=600   # 10 minutes

while true; do

    echo "Hotspot active. Retrying WiFi in 10 minutes..." >> "$LOG"

    sleep $HOTSPOT_RETRY_INTERVAL

    # ── Don't interrupt an active provisioning session ──
    if hotspot_has_clients; then
        echo "Hotspot has active clients. Skipping WiFi retry to avoid interruption." >> "$LOG"
        continue
    fi

    echo "No clients on hotspot. Stopping hotspot to retry WiFi..." >> "$LOG"

    systemctl stop hostapd >> "$LOG" 2>&1
    systemctl stop dnsmasq >> "$LOG" 2>&1
    systemctl stop wifi-ui >> "$LOG" 2>&1

    if try_wifi; then
        echo "WiFi restored. Exiting hotspot mode." >> "$LOG"
        exit 0
    fi

    echo "WiFi still unavailable. Restarting hotspot..." >> "$LOG"
    start_hotspot

done
