# CipherSight: Anti-Quishing Security

Hardware-software solution to prevent QR Phishing using (2,2) Visual Cryptography.

## Project Structure
- `core/`: VC engine and utilities
- `simulation/`: AR scanner application
- `firmware/`: ESP32 source code
- `outputs/`: Generated shares

## Quick Start
1. Install dependencies:
   ```bash
   pip install qrcode[pil] pillow numpy opencv-python paho-mqtt opencv-contrib-python
   ```
2. Generate shares and publish:
   ```bash
   python core/orchestrator.py
   ```
3. Start AR Scanner:
   ```bash
   python simulation/ar_overlay.py
   ```

## Hardware
1. Update `WIFI_SSID` and `WIFI_PASS` in `firmware/esp32_mqtt.ino`.
2. Flash to ESP32 with SSD1306 OLED.

## Docker
```bash
docker-compose up --build
```
