# EPD 电子墨水屏 Home Assistant 集成
## 部署与使用文档

>[英文文档](/README.md)

---

## 目录

1. [架构概述](#1-架构概述)
2. [硬件与系统要求](#2-硬件与系统要求)
3. [第一步：部署 EPD 控制服务器](#3-第一步部署-epd-控制服务器)
4. [第二步：配置 systemd 后台服务](#4-第二步配置-systemd-后台服务)
5. [第三步：安装 HA 集成](#5-第三步安装-ha-集成)
6. [第四步：配置集成](#6-第四步配置集成)
7. [实体说明](#7-实体说明)
8. [服务调用参考](#8-服务调用参考)
9. [图片编辑器使用指南](#9-图片编辑器使用指南)
10. [模板管理](#10-模板管理)
11. [自动化示例](#11-自动化示例)
12. [Lovelace 卡片示例](#12-lovelace-卡片示例)
13. [支持的屏幕尺寸](#13-支持的屏幕尺寸)
14. [故障排查](#14-故障排查)

---

## 1. 架构概述

本集成采用两层架构，将蓝牙通信与 Home Assistant 解耦：

```
Home Assistant (epd_display 集成)
        │  HTTP API
        ▼
EPD 控制服务器 (epd_server.py)      ← 运行于蓝牙可达的设备上
        │  BLE (蓝牙低能耗)
        ▼
电子墨水屏 (NRF52 固件)
```

**工作流程：**

1. HA 集成通过 HTTP 调用控制服务器的 REST API
2. 控制服务器通过 BLE 与电子墨水屏通信
3. 图像处理（抖动算法、格式转换）在控制服务器端完成
4. HA 负责数据聚合、模板渲染与自动化触发

**优势：** HA 本身不需要蓝牙硬件；控制服务器可以是树莓派、NAS 或任意 Linux 设备。

---

## 2. 硬件与系统要求

### 控制服务器（运行 epd_server.py 的设备）

| 项目 | 要求 |
|------|------|
| 操作系统 | Linux（Raspberry Pi OS、Ubuntu、Debian 等） |
| Python | 3.10 或更高版本 |
| 蓝牙 | 支持 BLE 4.0+ 的蓝牙适配器 |
| 网络 | 与 Home Assistant 在同一局域网内 |

### Home Assistant 主机

| 项目 | 要求 |
|------|------|
| HA 版本 | 2023.1 或更高版本 |
| 网络 | 可访问控制服务器的 8100 端口 |
| 字体（可选） | 将 CJK 字体放置于 `/config/www/epd_font.ttf` |

### 电子墨水屏

- 搭载 NRF52 系列主控，固件版本 **≥ 0x16**
- 支持 BLE GATT 服务 UUID：`62750001-d828-918d-fb46-b6c11c675aec`

---

## 3. 第一步：部署 EPD 控制服务器

### 3.1 创建目录与虚拟环境

```bash
# 创建工作目录
mkdir -p ~/epd && cd ~/epd

# 创建 Python 虚拟环境
python3 -m venv venv
source venv/bin/activate
```

### 3.2 安装依赖

```bash
pip install fastapi uvicorn python-multipart bleak Pillow numpy
```

### 3.3 放置文件

将发布包中 `server/` 目录下的两个文件复制到 `~/epd/`：

```
~/epd/
├── epd.py          # BLE 通信与图像处理核心
├── epd_server.py   # FastAPI HTTP 服务器
└── venv/           # Python 虚拟环境
```

### 3.4 验证启动

```bash
cd ~/epd
source venv/bin/activate
python epd_server.py
```

服务器成功启动后，终端显示：

```
INFO:     Started server process [XXXXX]
INFO:     Uvicorn running on http://0.0.0.0:8100 (Press CTRL+C to quit)
```

在浏览器中访问 `http://<服务器IP>:8100/docs` 即可看到 Swagger API 文档界面，确认服务正常运行后按 `Ctrl+C` 退出。

### 3.5 环境变量说明

服务器支持以下环境变量进行默认值配置：

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `EPD_DEVICE_NAME` | `NRF_EPD_3D56` | BLE 设备名称（模糊匹配） |
| `EPD_CANVAS` | `7.5_800_480` | 默认画布尺寸 |
| `EPD_DRIVER` | `07` | 默认驱动代码 |
| `EPD_DITHER_MODE` | `threeColor` | 默认颜色模式 |
| `EPD_AUTO_CONNECT` | `false` | 启动时是否自动连接设备 |
| `EPD_UPLOAD_DIR` | `/tmp/epd_images` | 图片临时存储目录 |

---

## 4. 第二步：配置 systemd 后台服务

使用 systemd 可让控制服务器开机自启并在崩溃时自动重启。

### 4.1 创建服务文件

使用发布包中的 `epd.service` 文件，或按以下内容创建 `/etc/systemd/system/epd.service`：

```ini
[Unit]
Description=EPD E-Paper Display BLE Control Server
After=network.target bluetooth.target
Wants=bluetooth.target

[Service]
# 修改为实际运行用户
User=pi
Group=pi

# 修改为实际工作目录
WorkingDirectory=/home/pi/epd

# 修改为虚拟环境中 Python 的实际路径
ExecStart=/home/pi/epd/venv/bin/python epd_server.py

# 环境变量（按需修改）
Environment="EPD_DEVICE_NAME=NRF_EPD_3D56"
Environment="EPD_CANVAS=7.5_800_480"
Environment="EPD_DRIVER=07"
Environment="EPD_DITHER_MODE=threeColor"
Environment="EPD_AUTO_CONNECT=false"
Environment="EPD_UPLOAD_DIR=/tmp/epd_images"

# 重启策略
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

> **注意：** 必须将 `User`、`WorkingDirectory`、`ExecStart` 三项修改为你服务器上的实际路径和用户名。

### 4.2 启用服务

```bash
# 重新加载 systemd 配置
sudo systemctl daemon-reload

# 设置开机自启
sudo systemctl enable epd.service

# 立即启动
sudo systemctl start epd.service

# 查看运行状态
sudo systemctl status epd.service
```

### 4.3 日志查看

```bash
# 实时查看日志
sudo journalctl -u epd.service -f

# 查看最近 100 行日志
sudo journalctl -u epd.service -n 100

# 查看今日日志
sudo journalctl -u epd.service --since today
```

### 4.4 蓝牙权限问题

若日志中出现蓝牙权限错误，将运行用户加入 `bluetooth` 组：

```bash
sudo usermod -aG bluetooth pi
# 重新登录后生效，或重启系统
sudo systemctl restart epd.service
```

若问题依然存在，可临时将 `User=pi` 改为 `User=root` 进行测试。

---

## 5. 第三步：安装 HA 集成

### 5.1 手动安装（推荐）

将发布包中的 `custom_components/epd_display/` 目录完整复制到 HA 的配置目录：

```
<HA配置目录>/
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

### 5.2 重启 Home Assistant

安装完成后必须重启 HA 才能加载集成：

- 进入 **设置 → 系统 → 重启**
- 或在开发者工具中执行重启

### 5.3 安装字体（可选，强烈推荐）

若需要正确显示中文，请将 CJK 字体文件放置于 HA 的 www 目录：

```bash
# 将字体文件复制到 HA www 目录（以 NotoSansCJK 为例）
cp NotoSansCJKsc-Regular.ttf <HA配置目录>/www/epd_font.ttf
```

集成会按以下优先级查找字体：

1. `/config/www/epd_font.ttf`（用户自定义，最高优先级）
2. `/config/www/epd_font.ttc`
3. `/config/www/epd_font.otf`
4. 系统内置 CJK 字体（自动扫描）
5. DejaVu Sans 等系统字体
6. PIL 默认字体（最低优先级，不支持中文）

---

## 6. 第四步：配置集成

### 6.1 添加集成

1. 进入 **设置 → 设备与服务 → 添加集成**
2. 搜索 **EPD E-Paper Display**
3. 填写配置信息：

| 字段 | 说明 | 示例 |
|------|------|------|
| Server Host | 控制服务器的 IP 地址 | `192.168.1.100` |
| Port | 服务器端口 | `8100` |
| BLE Device Name | 蓝牙设备名称（支持模糊匹配） | `NRF_EPD_3D56` |
| Canvas Size | 屏幕尺寸规格 | `7.5_800_480` |
| Driver Code | 驱动代码（从设备获取） | `07` |
| Color Mode | 颜色模式 | `threeColor` |

4. 点击提交，HA 将自动测试与服务器的连接

### 6.2 修改集成选项

配置完成后，可随时在集成页面点击 **配置** 修改以下选项：

- 画布尺寸
- 驱动代码
- 颜色模式
- 对比度（0.1 ~ 3.0）
- 抖动强度（0.0 ~ 2.0）

---

## 7. 实体说明

成功配置后，集成将自动创建以下实体：

### 传感器实体

| 实体名称 | 说明 | 可能的值 |
|----------|------|---------|
| `sensor.epd_display_connection` | BLE 连接状态 | `Connected` / `Disconnected` |
| `sensor.epd_display_firmware` | 设备固件版本 | `0x17` 等 |
| `sensor.epd_display_mtu` | 蓝牙 MTU 大小（字节） | `244` 等 |
| `sensor.epd_display_transfer` | 图像传输进度 | `空闲` / `传输中 68%` / `错误` |

> `Transfer` 传感器每 10 秒轮询一次（传输中时每 2 秒更新），附加属性包含：`busy`、`step`（bw/red/color）、`chunk`、`total`、`percent`、`elapsed_s`。

### 按钮实体

| 实体名称 | 说明 |
|----------|------|
| `button.epd_display_connect` | 连接 BLE 设备 |
| `button.epd_display_disconnect` | 断开 BLE 连接 |
| `button.epd_display_clear_screen` | 清空屏幕显示 |
| `button.epd_display_refresh` | 刷新屏幕 |
| `button.epd_display_sleep` | 让设备进入睡眠模式 |
| `button.epd_display_sync_clock` | 同步时间（时钟模式，局部刷新） |
| `button.epd_display_sync_calendar` | 同步时间（日历模式，全刷新） |
| `button.epd_display_system_reset` | 系统重置 |

---

## 8. 服务调用参考

### 8.1 连接与控制

```yaml
# 连接设备
service: epd_display.connect
data:
  device_name: "NRF_EPD_3D56"  # 可选，默认使用集成配置

# 断开连接
service: epd_display.disconnect

# 清屏
service: epd_display.clear

# 刷新
service: epd_display.refresh

# 进入睡眠
service: epd_display.sleep

# 同步时间（mode: 1=时钟局刷, 2=日历全刷）
service: epd_display.sync_time
data:
  mode: 1

# 系统重置
service: epd_display.sys_reset
```

### 8.2 显示本地图片

```yaml
service: epd_display.display_image
data:
  image_path: "/config/www/epd/my_image.png"
  canvas: "7.5_800_480"           # 可选，默认使用集成配置
  driver: "07"                    # 可选
  dither_mode: "threeColor"       # 可选：blackWhiteColor/threeColor/fourColor/sixColor
  contrast: 1.2                   # 可选，默认 1.0
  dither_strength: 1.0            # 可选，默认 1.0
```

### 8.3 显示 URL 图片

```yaml
service: epd_display.display_url
data:
  image_url: "http://192.168.1.10:8123/local/dashboard.png"
  canvas: "7.5_800_480"
  dither_mode: "blackWhiteColor"
```

### 8.4 生成图片（编程式绘图）

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
      text: "家庭状态面板"
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
      prefix: "室外温度: "
      suffix: "°C"
      color: "black"
      font_size: 28

    - type: textbox
      x: 20
      y: 150
      width: 380
      height: 120
      text: "这段文字会自动换行，不会超出文本框范围。"
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
        开窗数量: {{ states.binary_sensor
          | selectattr('state','eq','on')
          | selectattr('attributes.device_class','eq','window')
          | list | count }} 扇

    - type: image
      x: 700
      y: 20
      width: 80
      height: 80
      path: "/config/www/epd_icons/weather_sunny.svg"
```

### 8.5 渲染并发送模板

```yaml
service: epd_display.render_template
data:
  template_name: "morning_dashboard"   # 模板文件名（不含 .json）
  send_after_render: true              # 生成后自动发送到屏幕
```

---

## 9. 图片编辑器使用指南

集成内置了可视化图片编辑器，访问地址：

```
http://<HA地址>:8123/epd_display/editor
```

编辑器分为三个页面：**发送图片**、**画面编辑**、**模板管理**。

### 9.1 发送图片页

- **上传本地图片**：拖拽或点击选择图片文件，选择画布尺寸和颜色模式后点击发送
- **URL 发送**：输入图片 URL（支持 HA 截图、外部图片等），直接发送到屏幕

### 9.2 画面编辑器

可视化拖拽编辑器，支持以下工具：

| 工具 | 快捷键 | 说明 |
|------|--------|------|
| ↖ 选择 | `V` | 选中、移动、缩放元素 |
| ▭ 矩形 | `R` | 拖拽绘制矩形（可设置填充色和边框） |
| ╱ 线段 | `L` | 绘制直线 |
| ● 点 | `P` | 绘制实心圆点 |
| T 文字 | `T` | 点击放置单行文字 |
| {} 代码 | — | 放置 Jinja2 模板文字（支持渲染图标路径） |
| ☰ 文本框 | — | **拖拽绘制自动换行文本框** |
| 🖼 图标 | — | 放置图片/SVG 图标 |
| 📅 日历 | — | 放置月历组件 |

**文本框工具详解：**

选择 ☰ 文本框工具后，在工具选项中：

1. 设置字号、内边距、行间距、对齐方式、垂直对齐
2. 选择内容来源：
   - **📝 静态文字**：直接输入文字，`\n` 表示换行
   - **📊 传感器**：绑定 HA 实体，支持前缀/后缀
   - **{} 代码**：使用 Jinja2 模板动态生成内容
3. 可选启用背景色和边框
4. 在画布上**拖拽绘制**文本框区域

**元素操作：**

- 选中元素后可拖动位置
- 拖动四角控制点缩放尺寸
- `Delete` 键删除选中元素
- `Escape` 取消选中
- 左侧图层列表可快速定位元素

### 9.3 底部工具栏

| 按钮 | 说明 |
|------|------|
| 📋 导出YAML | 生成可用于服务调用的 YAML 代码 |
| 💾 JSON | 导出项目文件（可重新导入编辑） |
| 📂 导入 | 导入之前保存的 JSON 项目文件 |
| ⬇ PNG | 将当前画面下载为 PNG 图片 |
| 🖨 生成到HA | 在 HA 服务器端生成图片并保存 |
| 🚀 生成发送 | 生成图片并立即发送到电子墨水屏 |

---

## 10. 模板管理

模板是保存在服务器端的图像布局配置，支持包含动态 HA 实体数据，非常适合用于定时自动化刷新屏幕。

### 10.1 通过编辑器保存模板

1. 在画面编辑器中完成布局设计
2. 点击底部 **🖨 生成到HA** 确认布局正确
3. 切换到 **模板管理** 页
4. 点击 **💾 保存当前编辑为模板**，输入模板名称

### 10.2 通过 YAML 编辑器创建模板

在模板管理页的 YAML 编辑器中直接编写，示例：

```yaml
width: 800
height: 480
background_color: white
elements:
  - type: text
    x: 20
    y: 15
    text: 家庭状态
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
      天气: {{ states('sensor.weather_condition') }}
      温度: {{ states('sensor.outdoor_temp') }}°C
      湿度: {{ states('sensor.outdoor_humidity') }}%

  - type: entity_text
    x: 20
    y: 190
    entity_id: sensor.indoor_temperature
    prefix: "室内温度: "
    suffix: "°C"
    font_size: 26
    color: black
```

点击 **▶ 预览生成** 可在服务器端生成并确认效果，点击 **💾 保存为模板** 输入名称保存。

### 10.3 测试 Jinja2 模板

点击 **🔍 测试模板表达式** 打开测试窗口，可实时测试任意 Jinja2 表达式。

### 10.4 模板存储位置

模板文件保存在：`<HA配置目录>/epd_templates/<模板名>.json`

生成的图片保存在：`<HA配置目录>/epd_images/<文件名>.png`

---

## 11. 自动化示例

### 11.1 定时刷新屏幕

```yaml
automation:
  - alias: "每小时刷新墨水屏"
    trigger:
      - platform: time_pattern
        minutes: "0"
    action:
      - service: epd_display.render_template
        data:
          template_name: "home_dashboard"
          send_after_render: true
```

### 11.2 早晨显示日程信息

```yaml
automation:
  - alias: "早晨墨水屏更新"
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

### 11.3 传感器变化时更新

```yaml
automation:
  - alias: "温度变化时刷新屏幕"
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

### 11.4 显示摄像头截图

```yaml
automation:
  - alias: "门铃响时显示摄像头画面"
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

## 12. Lovelace 卡片示例

```yaml
type: entities
title: 电子墨水屏控制
entities:
  - entity: sensor.epd_display_connection
    name: 连接状态
  - entity: sensor.epd_display_transfer
    name: 传输进度
  - entity: sensor.epd_display_firmware
    name: 固件版本
  - entity: sensor.epd_display_mtu
    name: MTU
  - type: divider
  - entity: button.epd_display_connect
    name: 连接设备
  - entity: button.epd_display_disconnect
    name: 断开连接
  - entity: button.epd_display_clear_screen
    name: 清空屏幕
  - entity: button.epd_display_refresh
    name: 刷新屏幕
  - entity: button.epd_display_sleep
    name: 进入睡眠
  - entity: button.epd_display_sync_clock
    name: 同步时钟
  - entity: button.epd_display_system_reset
    name: 系统重置
```

---

## 13. 支持的屏幕尺寸

| 规格名称 | 分辨率 | 物理尺寸 |
|----------|--------|----------|
| `1.54_152_152` | 152 × 152 | 1.54 寸 |
| `1.54_200_200` | 200 × 200 | 1.54 寸 |
| `2.13_212_104` | 212 × 104 | 2.13 寸 |
| `2.13_250_122` | 250 × 122 | 2.13 寸 |
| `2.66_296_152` | 296 × 152 | 2.66 寸 |
| `2.9_296_128` | 296 × 128 | 2.9 寸 |
| `2.9_384_168` | 384 × 168 | 2.9 寸 |
| `3.5_384_184` | 384 × 184 | 3.5 寸 |
| `3.7_416_240` | 416 × 240 | 3.7 寸 |
| `3.97_800_480` | 800 × 480 | 3.97 寸 |
| `4.2_400_300` | 400 × 300 | 4.2 寸 |
| `4E_600_400` | 600 × 400 | 4 寸 E 型 |
| `5.79_792_272` | 792 × 272 | 5.79 寸 |
| `5.83_600_448` | 600 × 448 | 5.83 寸 |
| `5.83_648_480` | 648 × 480 | 5.83 寸 |
| `7.3E6` | 480 × 800 | 7.3 寸 六色 |
| `7.5_640_384` | 640 × 384 | 7.5 寸 |
| `7.5_800_480` | 800 × 480 | 7.5 寸（最常用） |
| `7.5_880_528` | 880 × 528 | 7.5 寸 |
| `10.2_960_640` | 960 × 640 | 10.2 寸 |
| `10.85_1360_480` | 1360 × 480 | 10.85 寸 |
| `11.6_960_640` | 960 × 640 | 11.6 寸 |

### 颜色模式说明

| 模式 | 说明 | 适用屏幕 |
|------|------|----------|
| `blackWhiteColor` | 黑白双色，每像素 1bit，传输最快 | 所有屏幕 |
| `threeColor` | 黑白红三色，两路数据传输 | 含红色通道的屏幕 |
| `fourColor` | 四色（黑白红黄），每像素 2bit | 四色屏 |
| `sixColor` | 六色全彩（黑白红黄绿蓝），列优先 | 彩色 E-Ink 屏 |

---

## 14. 故障排查

### 问题：无法连接到 BLE 设备

**排查步骤：**

1. 确认设备已开机且在蓝牙范围内（通常 10 米以内）
2. 检查控制服务器的蓝牙状态：
   ```bash
   sudo hciconfig
   bluetoothctl show
   ```
3. 确认运行用户有蓝牙权限：
   ```bash
   groups pi | grep bluetooth
   ```
4. 检查固件版本是否 ≥ 0x16（日志中有显示）
5. 尝试重启蓝牙服务：
   ```bash
   sudo systemctl restart bluetooth
   sudo systemctl restart epd.service
   ```

### 问题：HA 无法连接到控制服务器

**排查步骤：**

1. 确认服务器正在运行：
   ```bash
   sudo systemctl status epd.service
   curl http://服务器IP:8100/status
   ```
2. 检查防火墙是否开放 8100 端口：
   ```bash
   sudo ufw status
   sudo ufw allow 8100
   ```
3. 确认 HA 配置中的 IP 地址和端口正确

### 问题：中文字体显示为方块或乱码

**解决方案：**

1. 将 CJK 字体复制到 HA www 目录：
   ```bash
   cp /usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc \
      <HA配置目录>/www/epd_font.ttc
   ```
2. 重启 HA 后重新生成图片

### 问题：图片传输卡住或超时

**排查步骤：**

1. 查看 Transfer 传感器状态，确认传输是否真的卡住
2. 检查 MTU 大小，较小的 MTU 会导致传输变慢
3. 适当减小 `interleaved_count` 参数（默认为 5）
4. 断开重连后重试：
   ```yaml
   service: epd_display.disconnect
   service: epd_display.connect
   ```

### 问题：屏幕显示残影或刷新不完整

**排查步骤：**

1. 执行清屏操作：`service: epd_display.clear`
2. 确认使用了正确的 `driver` 驱动代码
3. 确认 `canvas` 尺寸与物理屏幕匹配
4. 对于三色屏，确认使用 `threeColor` 模式而非 `blackWhiteColor`

### 获取驱动代码

设备首次连接时，控制服务器会在日志中打印设备上报的引脚配置和驱动代码：

```bash
sudo journalctl -u epd.service | grep "驱动\|driver\|epd_driver"
```

---

*文档版本：v4.17 | 最后更新：2025 年*
