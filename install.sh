#!/bin/bash

set -e

PROJECT_DIR="/home/pi/rpi-wifi-connectivity-through-hotspot"
SERVICE_NAME="wifi-provision.service"

echo "Updating system..."
sudo apt update

echo "Installing required packages..."
sudo apt install -y \
    python3 \
    python3-venv \
    hostapd \
    dnsmasq \
    network-manager

echo "Stopping conflicting services..."
sudo systemctl stop hostapd || true
sudo systemctl stop dnsmasq || true
sudo systemctl stop NetworkManager || true

echo "Creating Python virtual environment..."
cd $PROJECT_DIR
python3 -m venv venv

echo "Installing Python dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

echo "Setting permissions..."
chmod +x wifi_boot.sh

echo "Installing systemd service..."
sudo cp systemd/$SERVICE_NAME /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME

echo "Installation complete. Rebooting..."
sudo reboot
