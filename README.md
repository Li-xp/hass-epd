# EPD E-Paper Display - Home Assistant Integration

## Architecture

```
HA (epd_display integration) --> HTTP --> Server (epd_server.py) --> BLE --> E-Paper
```

## Installation

### Step 1: Deploy EPD Server

On a Bluetooth-capable machine near the e-paper display:

```bash
mkdir -p ~/epd && cd ~/epd
python3 -m venv venv && source venv/bin/activate
pip install fastapi uvicorn python-multipart bleak Pillow numpy
# Place epd.py + epd_server.py here
python epd_server.py
```

Server listens on port 8100. Visit http://<server-ip>:8100/docs to verify.

### Step 2: Install HA Integration

1. Copy custom_components/epd_display/ to your HA config/custom_components/
2. Restart Home Assistant
3. Settings > Devices & Services > Add Integration > EPD E-Paper Display
4. Enter server IP, port, device name, screen size, etc.

## Entities Created

**Sensors:** Connection status, Firmware version, MTU size
**Buttons:** Connect, Disconnect, Clear, Refresh, Sleep

## Services

- epd_display.connect - Connect BLE
- epd_display.disconnect - Disconnect
- epd_display.clear - Clear screen
- epd_display.refresh - Refresh
- epd_display.sleep - Sleep
- epd_display.display_image - Show local image (image_path, canvas, dither_mode, contrast)
- epd_display.display_url - Show URL image (image_url, canvas, dither_mode, contrast)

## Automation Example

```yaml
automation:
  - alias: EPD Morning Update
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: epd_display.display_url
        data:
          image_url: "http://HA_IP:8123/local/epd/dashboard.png"
          canvas: "7.5_800_480"
          dither_mode: "threeColor"
```

## Lovelace Card

```yaml
type: entities
title: E-Paper Display
entities:
  - entity: sensor.epd_display_connection
  - entity: button.epd_display_connect
  - entity: button.epd_display_clear_screen
  - entity: button.epd_display_refresh
```
