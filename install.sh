#!/bin/bash

echo "Installing WiFi Provisioning System..."

sudo apt update
sudo apt install -y hostapd dnsmasq network-manager python3 python3-pip

pip3 install flask

# Copy scripts to system location
sudo cp wifi_boot.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/wifi_boot.sh
sudo cp wifi_ui.py /usr/local/bin/

# Copy systemd service
sudo cp systemd/wifi-provision.service /etc/systemd/system/

# Reload and enable service
sudo systemctl daemon-reload
sudo systemctl enable wifi-provision.service

echo "Installation complete. Rebooting..."
sudo reboot
