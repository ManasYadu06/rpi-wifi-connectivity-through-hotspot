Raspberry Pi WiFi Provisioning via Hotspot
Overview

This project enables automatic WiFi provisioning on a Raspberry Pi.

Behavior at boot:

If saved WiFi connects successfully → system joins normal network.

If WiFi connection fails → device starts a hotspot.

A web UI is exposed to configure WiFi credentials.

After successful configuration → system reboots and connects to selected network.


Tested on:

Raspberry Pi OS (Bookworm)

Raspberry Pi with onboard WiFi (wlan0)

NetworkManager enabled

No dhcpcd


Project Structure
rpi-wifi-connectivity-through-hotspot/
│
├── wifi_boot.sh
├── wifi_ui.py
├── wifi_credentials.conf
├── requirements.txt
├── README.md
│
├── systemd/
│   └── wifi-provision.service
│
└── configs/
    ├── hostapd.conf
    └── dnsmasq.conf


System Requirements

Install required packages:

sudo apt update
sudo apt install -y hostapd dnsmasq network-manager python3 python3-pip


Enable NetworkManager:

sudo systemctl enable NetworkManager


Disable hotspot services by default:

sudo systemctl disable hostapd
sudo systemctl disable dnsmasq


Do NOT install or use:

dhcpcd

Other hotspot management tools

Installation
1. Clone Repository
git clone https://github.com/ManasYadu06/rpi-wifi-connectivity-through-hotspot.git
cd rpi-wifi-connectivity-through-hotspot

2. Install Python Dependency
pip3 install -r requirements.txt

3. Copy Configuration Files
sudo mkdir -p /etc/hostapd
sudo cp configs/hostapd.conf /etc/hostapd/hostapd.conf
sudo cp configs/dnsmasq.conf /etc/dnsmasq.conf

4. Install Systemd Service
sudo cp systemd/wifi-provision.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable wifi-provision.service

5. Make Boot Script Executable
chmod +x wifi_boot.sh


If required:

sudo chmod +x /home/pi/rpi-wifi-connectivity-through-hotspot/wifi_boot.sh

Reboot
sudo reboot

Expected Behavior
Case 1 – WiFi connects successfully

wlan0 receives router IP

Hotspot does not start

Case 2 – WiFi fails

wlan0 assigned static IP: 10.0.0.5

Hotspot SSID: RPiHotspot

Web UI available at:

http://10.0.0.5:8080


After entering valid credentials:

NetworkManager connects

System reboots

Hotspot stops


Verification Commands

Check provisioning service:

systemctl status wifi-provision.service


Check wlan0:

ip addr show wlan0


Check NetworkManager:

systemctl status NetworkManager


Check service states:

systemctl is-enabled hostapd
systemctl is-enabled dnsmasq
systemctl is-enabled wifi-provision.service
systemctl is-enabled NetworkManager


Expected:

disabled
disabled
enabled
enabled

Important Notes

Designed for Raspberry Pi OS Bookworm.

Requires NetworkManager.

wlan0 must be available.

Clean OS installation strongly recommended.

Absolute paths inside systemd service must match your clone directory.

If cloning into a different path, update:

ExecStart=/home/pi/rpi-wifi-connectivity-through-hotspot/wifi_boot.sh


inside:

/etc/systemd/system/wifi-provision.service

Security Notice

Default hotspot credentials are defined in:

configs/hostapd.conf


Change:

SSID

WPA passphrase

before production deployment.
