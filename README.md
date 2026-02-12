Installation (Tested Working Procedure)
1. Install System Dependencies
sudo apt update
sudo apt install -y python3 python3-venv python3-pip hostapd dnsmasq network-manager git


Unmask hostapd:

sudo systemctl unmask hostapd


Disable services (managed by script):

sudo systemctl disable hostapd
sudo systemctl disable dnsmasq

2. Clone Repository
git clone https://github.com/YOUR_USERNAME/rpi-wifi-connectivity-through-hotspot.git
cd rpi-wifi-connectivity-through-hotspot

3. Create Virtual Environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate

4. Copy Configuration Files
sudo cp configs/hostapd.conf /etc/hostapd/hostapd.conf
sudo cp configs/dnsmasq.conf /etc/dnsmasq.conf

5. Install Systemd Service
sudo cp systemd/wifi-provision.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable wifi-provision.service

6. Reboot
sudo reboot

Access UI

If hotspot starts:

SSID: RPiHotspot
Password: 1234567890
URL: http://10.0.0.5:8080


After editing README:

git add README.md
git commit -m "Update README with verified clean installation steps"
git push
