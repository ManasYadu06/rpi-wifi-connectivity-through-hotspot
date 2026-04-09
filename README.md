📦 System Requirements

Install required system packages:

sudo apt update
sudo apt install -y python3 python3-venv python3-pip hostapd dnsmasq network-manager git

Unmask hostapd:

sudo systemctl unmask hostapd

Disable services (managed internally by the provisioning script):

sudo systemctl disable hostapd
sudo systemctl disable dnsmasq

📂 Clone Repository
git clone https://github.com/ManasYadu06/rpi-wifi-connectivity-through-hotspot.git
cd rpi-wifi-connectivity-through-hotspot

🐍 Create Virtual Environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate

⚙️ Copy Configuration Files
sudo cp configs/hostapd.conf /etc/hostapd/hostapd.conf
sudo cp configs/dnsmasq.conf /etc/dnsmasq.conf

🔧 Install Systemd Service
sudo cp systemd/wifi-provision.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable wifi-provision.service

🔁 Reboot
sudo reboot

🔋 Disable Wi-Fi Power Save (Recommended)
sudo iw dev wlan0 set power_save off

🌐 Access Provisioning UI

When hotspot mode is active:

Parameter	Value
SSID	RPiHotspot
Password	1234567890
URL	http://10.0.0.5:8080
