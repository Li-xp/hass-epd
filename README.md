# EPD E-Paper Display — Home Assistant Integration
## Deployment & Usage Guide

> [中文文档](/docs/README-cn.md)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Hardware & System Requirements](#2-hardware--system-requirements)
3. [Step 1: Deploy the EPD Control Server](#3-step-1-deploy-the-epd-control-server)
4. [Step 2: Configure the systemd Background Service](#4-step-2-configure-the-systemd-background-service)
5. [Step 3: Install the HA Integration](#5-step-3-install-the-ha-integration)
6. [Step 4: Configure the Integration](#6-step-4-configure-the-integration)
7. [Entity Reference](#7-entity-reference)
8. [Service Call Reference](#8-service-call-reference)
9. [Image Editor Guide](#9-image-editor-guide)
10. [Template Management](#10-template-management)
11. [Automation Examples](#11-automation-examples)
12. [Lovelace Card Example](#12-lovelace-card-example)
13. [Supported Screen Sizes](#13-supported-screen-sizes)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Architecture Overview

This integration uses a two-layer architecture that decouples Bluetooth communication from Home Assistant:

```
Home Assistant (epd_display integration)
        │  HTTP API
        ▼
EPD Control Server (epd_server.py)      ← runs on any Bluetooth-capable Linux device
        │  BLE (Bluetooth Low Energy)
        ▼
E-Paper Display (NRF52 firmware)
```

**How it works:**

1. The HA integration communicates with the control server via a REST HTTP API
2. The control server communicates with the e-paper display over BLE
3. Image processing (dithering, format conversion) is performed on the control server
4. HA handles data aggregation, template rendering, and automation triggers

**Key advantage:** Home Assistant itself does not need Bluetooth hardware. The control server can be a Raspberry Pi, NAS, or any Linux device within Bluetooth range of the display.

---

## 2. Hardware & System Requirements

### Control Server (running epd_server.py)

| Item | Requirement |
|------|-------------|
| Operating System | Linux (Raspberry Pi OS, Ubuntu, Debian, etc.) |
| Python | 3.10 or higher |
| Bluetooth | BLE 4.0+ adapter |
| Network | Same LAN as Home Assistant |

### Home Assistant Host

| Item | Requirement |
|------|-------------|
| HA Version | 2023.1 or higher |
| Network | Can reach port 8100 on the control server |
| Font (optional) | Place a CJK font at `/config/www/epd_font.ttf` for Chinese text |

### E-Paper Display

- NRF52-series MCU with firmware version **≥ 0x16**
- Supports BLE GATT service UUID: `62750001-d828-918d-fb46-b6c11c675aec`

---

## 3. Step 1: Deploy the EPD Control Server

### 3.1 Create Directory and Virtual Environment

```bash
# Create working directory
mkdir -p ~/epd && cd ~/epd

# Create Python virtual environment
python3 -m venv venv
source venv/bin/activate
```

### 3.2 Install Dependencies

```bash
pip install fastapi uvicorn python-multipart bleak Pillow numpy
```

### 3.3 Place the Files

Copy the two files from the `server/` directory of the release package into `~/epd/`:

```
~/epd/
├── epd.py          # BLE communication & image processing core
├── epd_server.py   # FastAPI HTTP server
└── venv/           # Python virtual environment
```

### 3.4 Verify the Server Starts

```bash
cd ~/epd
source venv/bin/activate
python epd_server.py
```

A successful startup looks like:

```
INFO:     Started server process [XXXXX]
INFO:     Uvicorn running on http://0.0.0.0:8100 (Press CTRL+C to quit)
```

Open `http://<server-ip>:8100/docs` in a browser to see the Swagger API documentation. Once confirmed, press `Ctrl+C` to stop.

### 3.5 Environment Variables

The server reads the following environment variables for default configuration:

| Variable | Default | Description |
|----------|---------|-------------|
| `EPD_DEVICE_NAME` | `NRF_EPD_3D56` | BLE device name (partial match supported) |
| `EPD_CANVAS` | `7.5_800_480` | Default canvas size |
| `EPD_DRIVER` | `07` | Default driver code |
| `EPD_DITHER_MODE` | `threeColor` | Default color mode |
| `EPD_AUTO_CONNECT` | `false` | Auto-connect on startup |
| `EPD_UPLOAD_DIR` | `/tmp/epd_images` | Temporary image storage directory |

---

## 4. Step 2: Configure the systemd Background Service

Using systemd ensures the control server starts on boot and automatically restarts if it crashes.

### 4.1 Create the Service File

Use the `epd.service` file from the release package, or create `/etc/systemd/system/epd.service` with the following content:

```ini
[Unit]
Description=EPD E-Paper Display BLE Control Server
After=network.target bluetooth.target
Wants=bluetooth.target

[Service]
# Change to the actual runtime user
User=pi
Group=pi

# Change to the actual working directory
WorkingDirectory=/home/pi/epd

# Change to the actual Python path in the virtual environment
ExecStart=/home/pi/epd/venv/bin/python epd_server.py

# Environment variables (modify as needed)
Environment="EPD_DEVICE_NAME=NRF_EPD_3D56"
Environment="EPD_CANVAS=7.5_800_480"
Environment="EPD_DRIVER=07"
Environment="EPD_DITHER_MODE=threeColor"
Environment="EPD_AUTO_CONNECT=false"
Environment="EPD_UPLOAD_DIR=/tmp/epd_images"

# Restart policy
Restart=on-failure
RestartSec=10s
StartLimitIntervalSec=60s
StartLimitBurst=3

StandardOutput=journal
StandardError=journal
SyslogIdentifier=epd-server

[Install]
WantedBy=multi-user.target
```

> **Important:** You must update `User`, `WorkingDirectory`, and `ExecStart` to match your actual server paths and username.

### 4.2 Enable the Service

```bash
# Reload systemd configuration
sudo systemctl daemon-reload

# Enable auto-start on boot
sudo systemctl enable epd.service

# Start immediately
sudo systemctl start epd.service

# Check status
sudo systemctl status epd.service
```

### 4.3 Viewing Logs

```bash
# Follow logs in real time
sudo journalctl -u epd.service -f

# View the last 100 lines
sudo journalctl -u epd.service -n 100

# View today's logs
sudo journalctl -u epd.service --since today
```

### 4.4 Bluetooth Permission Issues

If Bluetooth permission errors appear in the logs, add the runtime user to the `bluetooth` group:

```bash
sudo usermod -aG bluetooth pi
# Re-login or reboot for this to take effect
sudo systemctl restart epd.service
```

If the issue persists, temporarily change `User=pi` to `User=root` for testing.

---

## 5. Step 3: Install the HA Integration

### 5.1 Manual Installation (Recommended)

Copy the entire `custom_components/epd_display/` directory from the release package into your HA configuration directory:

```
<HA config dir>/
└── custom_components/
    └── epd_display/
        ├── __init__.py
        ├── api.py
        ├── button.py
        ├── config_flow.py
        ├── const.py
        ├── editor.html
        ├── image_editor.py
        ├── manifest.json
        ├── sensor.py
        ├── services.yaml
        ├── strings.json
        ├── en.json
        └── zh-Hans.json
```

### 5.2 Restart Home Assistant

After installation, restart HA to load the integration:

- Go to **Settings → System → Restart**
- Or restart from the Developer Tools panel

### 5.3 Install a Font (Optional but Strongly Recommended)

For correct CJK (Chinese/Japanese/Korean) text rendering, place a font file in the HA `www` directory:

```bash
# Copy a CJK font to the HA www directory
cp NotoSansCJKsc-Regular.ttf <HA config dir>/www/epd_font.ttf
```

The integration searches for fonts in this priority order:

1. `/config/www/epd_font.ttf` (user-defined, highest priority)
2. `/config/www/epd_font.ttc`
3. `/config/www/epd_font.otf`
4. System CJK fonts (auto-scanned at runtime)
5. DejaVu Sans and other system fonts
6. PIL default font (lowest priority — does not support CJK)

---

## 6. Step 4: Configure the Integration

### 6.1 Add the Integration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **EPD E-Paper Display**
3. Fill in the configuration:

| Field | Description | Example |
|-------|-------------|---------|
| Server Host | IP address of the control server | `192.168.1.100` |
| Port | Server port | `8100` |
| BLE Device Name | Bluetooth device name (partial match) | `NRF_EPD_3D56` |
| Canvas Size | Screen resolution profile | `7.5_800_480` |
| Driver Code | Driver code (reported by device) | `07` |
| Color Mode | Dithering color mode | `threeColor` |

4. Click Submit. HA will automatically test the connection to the server.

### 6.2 Changing Integration Options

After setup, click **Configure** on the integration card at any time to modify:

- Canvas size
- Driver code
- Color mode
- Contrast (0.1 – 3.0)
- Dither strength (0.0 – 2.0)

---

## 7. Entity Reference

After successful configuration, the integration creates the following entities automatically.

### Sensor Entities

| Entity | Description | Example Values |
|--------|-------------|----------------|
| `sensor.epd_display_connection` | BLE connection status | `Connected` / `Disconnected` |
| `sensor.epd_display_firmware` | Device firmware version | `0x17` |
| `sensor.epd_display_mtu` | Bluetooth MTU size (bytes) | `244` |
| `sensor.epd_display_transfer` | Image transfer progress | `Idle` / `Sending 68%` / `Error` |

> The Transfer sensor polls every 10 seconds (every 2 seconds during active transfers). Extra attributes include: `busy`, `step` (bw/red/color), `chunk`, `total`, `percent`, `elapsed_s`.

### Button Entities

| Entity | Description |
|--------|-------------|
| `button.epd_display_connect` | Connect to BLE device |
| `button.epd_display_disconnect` | Disconnect from BLE |
| `button.epd_display_clear_screen` | Clear the display |
| `button.epd_display_refresh` | Refresh the screen |
| `button.epd_display_sleep` | Put device into sleep mode |
| `button.epd_display_sync_clock` | Sync time (clock mode, partial refresh) |
| `button.epd_display_sync_calendar` | Sync time (calendar mode, full refresh) |
| `button.epd_display_system_reset` | System reset |

---

## 8. Service Call Reference

### 8.1 Connection & Control

```yaml
# Connect to device
service: epd_display.connect
data:
  device_name: "NRF_EPD_3D56"  # optional, defaults to integration config

# Disconnect
service: epd_display.disconnect

# Clear screen
service: epd_display.clear

# Refresh
service: epd_display.refresh

# Sleep
service: epd_display.sleep

# Sync time (mode: 1 = clock partial refresh, 2 = calendar full refresh)
service: epd_display.sync_time
data:
  mode: 1

# System reset
service: epd_display.sys_reset
```

### 8.2 Display a Local Image

```yaml
service: epd_display.display_image
data:
  image_path: "/config/www/epd/my_image.png"
  canvas: "7.5_800_480"        # optional, defaults to integration config
  driver: "07"                 # optional
  dither_mode: "threeColor"    # optional: blackWhiteColor/threeColor/fourColor/sixColor
  contrast: 1.2                # optional, default 1.0
  dither_strength: 1.0         # optional, default 1.0
```

### 8.3 Display an Image from URL

```yaml
service: epd_display.display_url
data:
  image_url: "http://192.168.1.10:8123/local/dashboard.png"
  canvas: "7.5_800_480"
  dither_mode: "blackWhiteColor"
```

### 8.4 Generate an Image (Programmatic Drawing)

```yaml
service: epd_display.generate_image
data:
  width: 800
  height: 480
  background_color: "white"
  output_filename: "my_dashboard.png"
  elements:
    - type: text
      x: 20
      y: 20
      text: "Home Status"
      color: "black"
      font_size: 36

    - type: rectangle
      x: 0
      y: 70
      width: 800
      height: 2
      outline: "#333333"
      line_width: 2

    - type: entity_text
      x: 20
      y: 90
      entity_id: sensor.outdoor_temperature
      prefix: "Outdoor: "
      suffix: "°C"
      color: "black"
      font_size: 28

    - type: textbox
      x: 20
      y: 150
      width: 380
      height: 120
      text: "This text auto-wraps and will never overflow the bounding box."
      color: "black"
      font_size: 20
      padding: 8
      align: "left"
      valign: "top"
      bg_color: "#f5f5f5"
      border_color: "#999999"
      border_width: 1

    - type: computed_text
      x: 420
      y: 90
      font_size: 22
      color: "black"
      template: >-
        Open windows: {{ states.binary_sensor
          | selectattr('state','eq','on')
          | selectattr('attributes.device_class','eq','window')
          | list | count }}

    - type: image
      x: 700
      y: 20
      width: 80
      height: 80
      path: "/config/www/epd_icons/weather_sunny.svg"
```

### 8.5 Render and Send a Template

```yaml
service: epd_display.render_template
data:
  template_name: "morning_dashboard"  # template name without .json extension
  send_after_render: true             # send to screen after generating
```

---

## 9. Image Editor Guide

The integration includes a built-in visual image editor, accessible at:

```
http://<HA address>:8123/epd_display/editor
```

The editor has three tabs: **Send Image**, **Canvas Editor**, and **Template Manager**.

### 9.1 Send Image Tab

- **Upload local image:** Drag and drop or click to select a file, choose canvas size and color mode, then click Send
- **Send from URL:** Enter an image URL (HA camera snapshots, external URLs, etc.) and send directly to the screen

### 9.2 Canvas Editor

A visual drag-and-drop editor supporting the following tools:

| Tool | Shortcut | Description |
|------|----------|-------------|
| ↖ Select | `V` | Select, move, and resize elements |
| ▭ Rectangle | `R` | Drag to draw a rectangle (fill and border supported) |
| ╱ Line | `L` | Draw a straight line |
| ● Point | `P` | Place a filled circle |
| T Text | `T` | Click to place single-line text |
| {} Code | — | Place a Jinja2 template text element (supports icon path rendering) |
| ☰ Text Box | — | **Drag to draw an auto-wrapping text box** |
| 🖼 Image | — | Place an image or SVG icon |
| 📅 Calendar | — | Place a monthly calendar component |

**Text Box Tool Details:**

After selecting the ☰ Text Box tool, configure options in the sidebar:

1. Set font size, padding, line spacing, horizontal and vertical alignment
2. Choose content source:
   - **📝 Static Text:** Type directly; use `\n` for line breaks
   - **📊 Entity:** Bind to a HA entity with optional prefix/suffix
   - **{} Code:** Use a Jinja2 template for dynamic content
3. Optionally enable background color and border
4. **Drag on the canvas** to draw the text box area

**Element Operations:**

- Drag selected elements to reposition them
- Drag corner handles to resize
- `Delete` key removes the selected element
- `Escape` deselects
- The layer list on the left allows quick selection

### 9.3 Bottom Toolbar

| Button | Description |
|--------|-------------|
| 📋 Export YAML | Generate YAML code ready for a service call |
| 💾 JSON | Export the project file (can be re-imported) |
| 📂 Import | Import a previously saved JSON project |
| ⬇ PNG | Download the current canvas as a PNG |
| 🖨 Generate to HA | Generate the image on the HA server and save |
| 🚀 Generate & Send | Generate and immediately send to the e-paper display |

---

## 10. Template Management

Templates are server-side image layout configurations that can include dynamic HA entity data. They are ideal for scheduled automation that periodically refreshes the screen.

### 10.1 Save a Template from the Editor

1. Design a layout in the Canvas Editor
2. Click **🖨 Generate to HA** to confirm the result
3. Switch to the **Template Manager** tab
4. Click **💾 Save Current as Template** and enter a name

### 10.2 Create a Template with the YAML Editor

Write YAML directly in the Template Manager's code editor. Example:

```yaml
width: 800
height: 480
background_color: white
elements:
  - type: text
    x: 20
    y: 15
    text: Home Status
    color: black
    font_size: 36

  - type: textbox_computed
    x: 20
    y: 70
    width: 400
    height: 100
    font_size: 20
    color: black
    padding: 8
    align: left
    valign: top
    bg_color: "#f0f0f0"
    border_color: "#cccccc"
    border_width: 1
    template: >-
      Weather: {{ states('sensor.weather_condition') }}
      Temp: {{ states('sensor.outdoor_temp') }}°C
      Humidity: {{ states('sensor.outdoor_humidity') }}%

  - type: entity_text
    x: 20
    y: 190
    entity_id: sensor.indoor_temperature
    prefix: "Indoor: "
    suffix: "°C"
    font_size: 26
    color: black
```

Click **▶ Preview** to generate on the server and verify the result. Click **💾 Save as Template** to save with a name.

### 10.3 Test Jinja2 Templates

Click **🔍 Test Template Expression** to open a testing window where you can evaluate any Jinja2 expression in real time.

### 10.4 Storage Locations

Templates are saved to: `<HA config dir>/epd_templates/<name>.json`

Generated images are saved to: `<HA config dir>/epd_images/<filename>.png`

---

## 11. Automation Examples

### 11.1 Hourly Screen Refresh

```yaml
automation:
  - alias: "Hourly e-paper refresh"
    trigger:
      - platform: time_pattern
        minutes: "0"
    action:
      - service: epd_display.render_template
        data:
          template_name: "home_dashboard"
          send_after_render: true
```

### 11.2 Morning Briefing

```yaml
automation:
  - alias: "Morning e-paper update"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: epd_display.connect
      - delay: "00:00:05"
      - service: epd_display.render_template
        data:
          template_name: "morning_brief"
          send_after_render: true
```

### 11.3 Update on Sensor Change

```yaml
automation:
  - alias: "Refresh screen on temperature change"
    trigger:
      - platform: state
        entity_id: sensor.outdoor_temperature
    condition:
      - condition: template
        value_template: >
          {{ (trigger.to_state.state | float - trigger.from_state.state | float) | abs > 1 }}
    action:
      - service: epd_display.display_url
        data:
          image_url: "http://localhost:8123/local/epd/sensor_display.png"
          canvas: "7.5_800_480"
          dither_mode: "blackWhiteColor"
```

### 11.4 Display a Camera Snapshot

```yaml
automation:
  - alias: "Show doorbell camera on e-paper"
    trigger:
      - platform: state
        entity_id: binary_sensor.doorbell
        to: "on"
    action:
      - service: camera.snapshot
        target:
          entity_id: camera.front_door
        data:
          filename: "/config/www/epd/doorbell.jpg"
      - delay: "00:00:01"
      - service: epd_display.display_image
        data:
          image_path: "/config/www/epd/doorbell.jpg"
          dither_mode: "blackWhiteColor"
          contrast: 1.3
```

---

## 12. Lovelace Card Example

```yaml
type: entities
title: E-Paper Display Control
entities:
  - entity: sensor.epd_display_connection
    name: Connection Status
  - entity: sensor.epd_display_transfer
    name: Transfer Progress
  - entity: sensor.epd_display_firmware
    name: Firmware Version
  - entity: sensor.epd_display_mtu
    name: MTU Size
  - type: divider
  - entity: button.epd_display_connect
    name: Connect
  - entity: button.epd_display_disconnect
    name: Disconnect
  - entity: button.epd_display_clear_screen
    name: Clear Screen
  - entity: button.epd_display_refresh
    name: Refresh
  - entity: button.epd_display_sleep
    name: Sleep
  - entity: button.epd_display_sync_clock
    name: Sync Clock
  - entity: button.epd_display_system_reset
    name: System Reset
```

---

## 13. Supported Screen Sizes

| Profile Name | Resolution | Physical Size |
|--------------|------------|---------------|
| `1.54_152_152` | 152 × 152 | 1.54 inch |
| `1.54_200_200` | 200 × 200 | 1.54 inch |
| `2.13_212_104` | 212 × 104 | 2.13 inch |
| `2.13_250_122` | 250 × 122 | 2.13 inch |
| `2.66_296_152` | 296 × 152 | 2.66 inch |
| `2.9_296_128` | 296 × 128 | 2.9 inch |
| `2.9_384_168` | 384 × 168 | 2.9 inch |
| `3.5_384_184` | 384 × 184 | 3.5 inch |
| `3.7_416_240` | 416 × 240 | 3.7 inch |
| `3.97_800_480` | 800 × 480 | 3.97 inch |
| `4.2_400_300` | 400 × 300 | 4.2 inch |
| `4E_600_400` | 600 × 400 | 4 inch E-type |
| `5.79_792_272` | 792 × 272 | 5.79 inch |
| `5.83_600_448` | 600 × 448 | 5.83 inch |
| `5.83_648_480` | 648 × 480 | 5.83 inch |
| `7.3E6` | 480 × 800 | 7.3 inch six-color |
| `7.5_640_384` | 640 × 384 | 7.5 inch |
| `7.5_800_480` | 800 × 480 | 7.5 inch **(most common)** |
| `7.5_880_528` | 880 × 528 | 7.5 inch |
| `10.2_960_640` | 960 × 640 | 10.2 inch |
| `10.85_1360_480` | 1360 × 480 | 10.85 inch |
| `11.6_960_640` | 960 × 640 | 11.6 inch |

### Color Mode Reference

| Mode | Description | Compatible Screens |
|------|-------------|-------------------|
| `blackWhiteColor` | Black & white, 1 bit per pixel, fastest transfer | All screens |
| `threeColor` | Black, white, and red — two data planes | Screens with red channel |
| `fourColor` | Black, white, red, yellow — 2 bits per pixel | Four-color screens |
| `sixColor` | Full six-color (black, white, red, yellow, green, blue) — column-major | Color E-Ink screens |

---

## 14. Troubleshooting

### Cannot Connect to the BLE Device

**Diagnostic steps:**

1. Confirm the device is powered on and within Bluetooth range (typically within 10 m)
2. Check Bluetooth status on the control server:
   ```bash
   sudo hciconfig
   bluetoothctl show
   ```
3. Verify the runtime user has Bluetooth permissions:
   ```bash
   groups pi | grep bluetooth
   ```
4. Check that firmware version is ≥ 0x16 (shown in the server log on connect)
5. Restart the Bluetooth stack and the service:
   ```bash
   sudo systemctl restart bluetooth
   sudo systemctl restart epd.service
   ```

### HA Cannot Reach the Control Server

**Diagnostic steps:**

1. Confirm the server is running:
   ```bash
   sudo systemctl status epd.service
   curl http://<server-ip>:8100/status
   ```
2. Check whether the firewall is blocking port 8100:
   ```bash
   sudo ufw status
   sudo ufw allow 8100
   ```
3. Verify the IP address and port in the HA integration configuration are correct

### CJK Text Displays as Boxes or Garbled Characters

**Solution:**

1. Copy a CJK font to the HA www directory:
   ```bash
   cp /usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc \
      <HA config dir>/www/epd_font.ttc
   ```
2. Restart HA and regenerate the image

### Image Transfer Stalls or Times Out

**Diagnostic steps:**

1. Check the Transfer sensor state to confirm the transfer is genuinely stuck
2. Check the MTU size — a smaller MTU results in slower transfers
3. Reduce the `interleaved_count` parameter (default 5) and retry
4. Disconnect and reconnect, then retry:
   ```yaml
   service: epd_display.disconnect
   # wait a moment
   service: epd_display.connect
   ```

### Screen Shows Ghosting or Incomplete Refresh

**Diagnostic steps:**

1. Run a clear operation: `service: epd_display.clear`
2. Confirm you are using the correct `driver` code for your specific screen
3. Confirm the `canvas` size matches the physical screen resolution
4. For three-color screens, ensure you are using `threeColor` mode rather than `blackWhiteColor`

### How to Find the Driver Code

When the device first connects, the control server logs the device-reported pin configuration and driver code:

```bash
sudo journalctl -u epd.service | grep -i "driver\|epd_driver\|驱动"
```

---

*Documentation version: v4.17 | Last updated: 2025*
