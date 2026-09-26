# 📡 RPi Wi-Fi Provisioning via Hotspot

A self-hosted Wi-Fi provisioning system for Raspberry Pi — automatically creates a hotspot when no known network is found, serving a browser-based UI to configure Wi-Fi credentials on the fly. Built for headless deployments like **StatCams** (AI-powered sports recording cameras on RPi Zero 2W / RPi 4).

---

## 🧰 Prerequisites

Before cloning, install the required system packages:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip hostapd dnsmasq network-manager git ffmpeg
```

Unmask `hostapd` (required on Raspberry Pi OS):

```bash
sudo systemctl unmask hostapd
```

Disable auto-start — both services are managed by the provisioning script:

```bash
sudo systemctl disable hostapd
sudo systemctl disable dnsmasq
```

---

## 🚀 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/ManasYadu06/rpi-wifi-connectivity-through-hotspot.git
cd rpi-wifi-connectivity-through-hotspot
```

### 2. Create a Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate
```

### 3. Copy Configuration Files

```bash
sudo cp configs/hostapd.conf /etc/hostapd/hostapd.conf
sudo cp configs/dnsmasq.conf /etc/dnsmasq.conf
```

### 4. Install and Enable Systemd Services

```bash
sudo cp systemd/wifi-provision.service /etc/systemd/system/
sudo cp systemd/wifi-ui.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable wifi-provision.service
sudo systemctl enable wifi-ui.service
```

### 5. Reboot

```bash
sudo reboot
```

---

## ⚡ Post-Boot Recommendation

Disable Wi-Fi power saving to ensure stable hotspot behaviour:

```bash
sudo iw dev wlan0 set power_save off
```

---

## 🌐 Accessing the Provisioning UI

When no known network is available, the Pi automatically activates the hotspot. Connect from any device:

| Parameter | Value |
|-----------|-------|
| **SSID** | `RPiHotspot` |
| **Password** | `1234567890` |
| **URL** | `http://10.0.0.5:8080` |

Open the URL in your browser to enter your Wi-Fi credentials. Once saved, the Pi will connect to your network and disable the hotspot.

---

## 🔄 How It Works

```
Boot
 └─► Known Wi-Fi found? ──Yes──► Connect normally
           │
           No
           ▼
     Start Hotspot (RPiHotspot)
           │
     User opens http://10.0.0.5:8080
           │
     Enter Wi-Fi credentials
           │
     Connect to network & disable hotspot
```

---

## 📁 Project Structure

```
rpi-wifi-connectivity-through-hotspot/
├── configs/
│   ├── hostapd.conf       # Hotspot configuration
│   └── dnsmasq.conf       # DHCP/DNS configuration
├── systemd/
│   ├── wifi-provision.service
│   └── wifi-ui.service
├── requirements.txt
└── README.md
```

---

## 🛠 Tested On

- Raspberry Pi Zero 2W
- Raspberry Pi 4
- Raspberry Pi OS (Bookworm / Bullseye)

---

## 📄 License

MIT
