# RuloSec
### *// Explota tu conocimiento — Educational Cybersecurity Platform*

> **Live demo platform that executes real cyberattacks in a controlled environment and explains them in real time, so anyone can understand how to protect themselves.**

---

## Overview

RuloSec is an interactive educational cybersecurity platform built in Python + Flask. It does not *simulate* attacks — it *executes* them in a local, controlled environment, showing exactly what happens at the technical level while teaching users how to defend themselves.

The project was developed for **FEPRO 2026** (XVIII Competencia de Proyectos Tecnológicos, BUAP), Category B — Digital Innovation, aligned with **UN SDG 4: Quality Education**.

> In Mexico, **73% of internet users have never received cybersecurity education**. RuloSec addresses that gap by making invisible threats visible.

---

## Modules

### 01 · Educational Keylogger
JavaScript captures every keystroke typed into the login form and sends it to the Flask backend in real time — before the user presses Enter, even in password fields. Demonstrates how JS-based keyloggers work without installing anything on the victim's device.

### 02 · IP Geolocation & Device Fingerprinting
On button click, the server queries the visitor's public IP via ip-api.com and combines it with browser fingerprint data (CPU cores, RAM, battery, screen resolution) to build a unique profile — visible on a satellite map. Works even in incognito mode.

### 03 · ARP Network Scanner
Three-phase local network discovery:
1. **ARP Layer 2** — detects all active IPs and MAC addresses
2. **SSDP / UPnP / mDNS / NetBIOS** — identifies device types
3. **TCP Fingerprinting** — probes 40+ ports and performs vendor lookup by MAC prefix

Results render on a live radar UI with synchronized sonar audio (`sonarPing()` every 3 seconds).

### 04 · Behavioral Biometrics
Mouse movement coordinates are sampled every 15 events and sent to `/api/raton`. Movement speed, trajectory, and click patterns are as unique as a fingerprint — logged without cookies, login, or permissions.

### 05 · Ultrasonic Radar (Air-Gap Defeat)
The browser emits an inaudible **19,500 Hz** tone via the Web Audio API on every user interaction. `radar_audio.py` listens via microphone, applies FFT analysis with SNR filtering, and alerts on detection — demonstrating acoustic side-channel communication without WiFi or Bluetooth.

### 06 · Tor Hidden Service
The entire platform runs as a `.onion` Tor hidden service via Docker Compose, demonstrating that technical anonymity has limits: the keylogger still captures keystrokes even over Tor.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11 · Flask · REST API |
| Frontend | Vanilla JavaScript · HTML5 · CSS3 |
| Network scanning | Scapy · ARP · SSDP · mDNS · NetBIOS |
| Audio / Signal | NumPy · sounddevice · FFT |
| Anonymity layer | Tor · Docker Compose |
| Geolocation | ip-api.com |

---

## Architecture

```
Browser (visitor)
      │
      ├── script.js ──────────────────────────────────────────┐
      │   ├── Keylogger     → POST /api/keylogger             │
      │   ├── Mouse tracker → POST /api/raton                 │
      │   ├── IP request    → POST /api/ip                    │
      │   ├── ARP scanner   → GET  /api/scan_arp              │
      │   └── Ultrasonic    → Web Audio API (19,500 Hz)       │
      │                                                        │
      └── Flask servidor.py :5001 ◄──────────────────────────┘
            │
            ├── /api/ip        → ip-api.com (geolocation)
            ├── /api/scan_arp  → ARP + TCP fingerprinting
            ├── /api/keylogger → evidencia_quetzalcoatl.txt
            └── /api/raton     → /tmp/rulosec.log

radar_audio.py (separate process)
      └── Microphone → FFT → DETECCIÓN #1 (19,500 Hz detected)

Docker Compose
      ├── tor container    → .onion hidden service (port 80)
      └── app_python       → Flask :5001 (internal bridge)
```

---

## Running Locally

**Requirements:** Python 3.11+, Docker Desktop

```bash
# 1. Clone and set up environment
git clone https://github.com/RuloSEC999/RuloSec.git
cd RuloSec
python3 -m venv venv && source venv/bin/activate
pip install flask flask-cors numpy sounddevice

# 2. Start Flask server
python servidor.py
# → http://localhost:5001

# 3. Start ultrasonic radar (separate terminal)
python radar_audio.py

# 4. Start Tor hidden service (separate terminal)
docker compose up
```

---

## Educational Purpose & Ethics

RuloSec operates exclusively in a **local, controlled network environment**. No captured data leaves the machine. All visitors at live demos are informed that the platform is an educational demonstration.

The distinction between RuloSec and a malicious tool is the same as between a scalpel and a weapon: **purpose and context**. RuloSec shows the attack and explains it — a malicious tool hides it.

Every module includes:
- What the attack does technically
- Why it is dangerous in the real world
- How to protect yourself

---

## Design Philosophy

The project's visual identity is built around **Quetzalcóatl** — the Mesoamerican deity who, unlike other gods, opposed human sacrifice and instead offered knowledge, jade, and butterflies. An animated Quetzalcóatl serpent follows the cursor throughout the interface, embodying the project's core idea: *a guardian that reveals hidden knowledge, not to harm, but to protect.*

---

## Author

**Ángel Raúl Sedano Matías**
Ingeniería en Ciberseguridad — BUAP (Benemérita Universidad Autónoma de Puebla)
FEPRO 2026 · Category B · Digital Innovation · SDG 4

📧 bulletproofRul000@pm.me

---

*"La serpiente que vigila el código." / "The serpent that watches over the code."*
