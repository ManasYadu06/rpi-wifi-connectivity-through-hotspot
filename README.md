Installation Guide — Fresh Raspberry Pi Setup
1️⃣ Flash OS

Install Raspberry Pi OS (Lite).
Enable SSH during flashing.

2️⃣ First boot → Update system
sudo apt update
sudo apt upgrade -y

3️⃣ Install required packages
sudo apt install -y git hostapd dnsmasq python3 python3-pip
pip3 install flask


Disable services (they will be controlled by script):

sudo systemctl disable hostapd
sudo systemctl disable dnsmasq

4️⃣ Clone your repository
cd /home/pi
git clone https://github.com/ManasYadu06/rpi-wifi-connectivity-through-hotspot.git
cd rpi-wifi-connectivity-through-hotspot

5️⃣ Make boot script executable
chmod +x wifi_boot.sh

6️⃣ Run manually (test mode)
sudo ./wifi_boot.sh


Then connect to:

http://10.0.0.5:8080

7️⃣ After verification → Optional auto-start at boot

(We will add systemd service later.)
