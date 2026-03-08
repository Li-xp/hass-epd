# EPD 电子墨水屏集成 API 文档

- **在线文档** — 服务器部署后可以通过 `http://<服务器IP>:8100/docs`访问

本文档描述两组 API：
- **控制服务器 API**（`epd_server.py`）— 标准 HTTP REST，监听于 `http://<服务器IP>:8100`
- **HA 集成内部 API**（`__init__.py`）— 由编辑器前端调用，需 HA 登录鉴权，前缀为 `http://<HA地址>:8123`

---

## 目录

**控制服务器 API**
- [通用约定](#通用约定)
- [GET /status](#get-status)
- [POST /connect](#post-connect)
- [POST /disconnect](#post-disconnect)
- [POST /clear](#post-clear)
- [POST /refresh](#post-refresh)
- [POST /sleep](#post-sleep)
- [POST /sync_time](#post-sync_time)
- [POST /sys_reset](#post-sys_reset)
- [POST /display](#post-display)
- [POST /display_url](#post-display_url)
- [GET /canvases](#get-canvases)

**HA 集成内部 API**
- [POST /api/epd_display/upload](#post-apiepdisplayupload)
- [POST /api/epd_display/display_url](#post-apiepdisplaydisplay_url)
- [GET /api/epd_display/entities](#get-apiepdisplayentities)
- [GET /api/epd_display/config](#get-apiepdisplayconfig)
- [GET /api/epd_display/media_list](#get-apiepdisplaymedia_list)
- [GET /api/epd_display/media_proxy](#get-apiepdisplaymedia_proxy)
- [GET /api/epd_display/calendar_events](#get-apiepdisplaycalendar_events)
- [POST /api/epd_display/generate](#post-apiepdisplaygenerate)
- [GET /api/epd_display/templates](#get-apiepdisplaytemplates)
- [GET /api/epd_display/templates/{name}](#get-apiepdisplaytemplatesname)
- [PUT /api/epd_display/templates/{name}](#put-apiepdisplaytemplatesname)
- [DELETE /api/epd_display/templates/{name}](#delete-apiepdisplaytemplatesname)
- [POST /api/epd_display/template_preview](#post-apiepdisplaytemplate_preview)
- [POST /api/epd_display/parse_yaml](#post-apiepdisplayparse_yaml)

**附录**
- [元素类型参数参考](#元素类型参数参考)
- [颜色模式说明](#颜色模式说明)
- [错误码说明](#错误码说明)

---

## 通用约定

### 控制服务器

| 项目 | 说明 |
|------|------|
| 基础 URL | `http://<服务器IP>:8100` |
| 请求格式 | `application/x-www-form-urlencoded` 或 `multipart/form-data` |
| 响应格式 | `application/json` |
| 鉴权 | 无（建议仅在内网使用） |

### 忙碌锁机制

当设备正在传输图像时，所有写操作（`/connect`、`/disconnect`、`/clear`、`/refresh`、`/sleep`、`/sync_time`、`/sys_reset`、`/display`、`/display_url`）会返回 **409 Conflict**，防止并发操作损坏传输。

### HA 集成内部 API

| 项目 | 说明 |
|------|------|
| 基础 URL | `http://<HA地址>:8123` |
| 请求格式 | `application/json`（上传接口除外） |
| 响应格式 | `application/json` |
| 鉴权 | 需要 HA 长期访问令牌（Bearer Token），通过 `Authorization: Bearer <token>` 请求头传递 |

---

## 控制服务器 API

---

### GET /status

获取设备连接状态及当前传输进度。

**请求**

```
GET http://<服务器IP>:8100/status
```

无请求参数。

**响应示例（已连接，空闲）**

```json
{
  "connected": true,
  "device": "NRF_EPD_3D56",
  "firmware": "0x17",
  "mtu": 244,
  "transfer": {
    "busy": false,
    "step": "",
    "chunk": 0,
    "total": 0,
    "percent": 0,
    "elapsed": 12.3,
    "message": "空闲",
    "last_error": ""
  }
}
```

**响应示例（传输中）**

```json
{
  "connected": true,
  "device": "NRF_EPD_3D56",
  "firmware": "0x17",
  "mtu": 244,
  "transfer": {
    "busy": true,
    "step": "黑白",
    "chunk": 142,
    "total": 210,
    "percent": 68,
    "elapsed": 4.2,
    "message": "黑白 142/210 (68%) 4.2s"
  }
}
```

**响应字段说明**

| 字段 | 类型 | 说明 |
|------|------|------|
| `connected` | boolean | BLE 是否已连接 |
| `device` | string \| null | 已连接的设备名称 |
| `firmware` | string \| null | 固件版本（十六进制字符串），要求 ≥ `0x16` |
| `mtu` | integer \| null | 当前 BLE MTU 大小（字节），影响传输速度 |
| `transfer.busy` | boolean | 是否正在传输图像 |
| `transfer.step` | string | 当前传输步骤：`黑白` / `颜色` / `红色` |
| `transfer.chunk` | integer | 当前已发送的分块序号 |
| `transfer.total` | integer | 总分块数 |
| `transfer.percent` | integer | 传输进度百分比（0-100） |
| `transfer.elapsed` | number | 本次传输已用时间（秒） |
| `transfer.message` | string | 可读状态描述 |
| `transfer.last_error` | string | 最后一次错误信息（无错误时为空字符串） |

---

### POST /connect

扫描并连接指定 BLE 设备。扫描超时为 30 秒。

**请求**

```
POST http://<服务器IP>:8100/connect
Content-Type: application/x-www-form-urlencoded
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `device_name` | string | 否 | 设备名称（支持模糊匹配）。省略时使用环境变量 `EPD_DEVICE_NAME` |

**curl 示例**

```bash
curl -X POST http://192.168.1.100:8100/connect \
  -d "device_name=NRF_EPD_3D56"
```

**成功响应** `200 OK`

```json
{
  "status": "ok",
  "device": "NRF_EPD_3D56"
}
```

**失败响应** `500 Internal Server Error`

```json
{
  "detail": "未找到目标BLE设备"
}
```

---

### POST /disconnect

断开当前 BLE 连接。

**请求**

```
POST http://<服务器IP>:8100/disconnect
```

无请求参数。

**成功响应** `200 OK`

```json
{
  "status": "ok"
}
```

---

### POST /clear

向设备发送清屏指令，清除屏幕上的所有内容。

> **注意：** 清屏会让屏幕闪烁刷新，完成需要数秒。

**请求**

```
POST http://<服务器IP>:8100/clear
```

无请求参数。

**成功响应** `200 OK`

```json
{
  "status": "ok",
  "message": "清屏指令已发送"
}
```

---

### POST /refresh

向设备发送刷新指令，触发屏幕重新绘制当前缓冲区内容。

**请求**

```
POST http://<服务器IP>:8100/refresh
```

无请求参数。

**成功响应** `200 OK`

```json
{
  "status": "ok"
}
```

---

### POST /sleep

向设备发送睡眠指令，降低功耗。唤醒需重新连接。

**请求**

```
POST http://<服务器IP>:8100/sleep
```

无请求参数。

**成功响应** `200 OK`

```json
{
  "status": "ok"
}
```

---

### POST /sync_time

同步系统时间到设备，并启动屏幕内置时钟或日历显示模式。

**请求**

```
POST http://<服务器IP>:8100/sync_time
Content-Type: application/x-www-form-urlencoded
```

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `mode` | integer | 否 | `1` | `1` = 日历全刷模式（完整日期+时间，会闪烁一次）；`2` = 时钟局刷模式（仅更新分针，无闪烁，适合持续运行） |

**curl 示例**

```bash
# 启动时钟局刷模式
curl -X POST http://192.168.1.100:8100/sync_time -d "mode=2"
```

**成功响应** `200 OK`

```json
{
  "status": "ok",
  "mode": 2,
  "mode_name": "时钟（局刷）",
  "message": "时间同步成功，已启动时钟（局刷）模式"
}
```

> 时间和时区由服务器系统时钟自动获取，无需手动传入。

---

### POST /sys_reset

向设备发送系统重置指令。

**请求**

```
POST http://<服务器IP>:8100/sys_reset
```

无请求参数。

**成功响应** `200 OK`

```json
{
  "status": "ok",
  "message": "系统重置指令已发送"
}
```

---

### POST /display

上传图片文件，经服务器处理后发送到电子墨水屏显示。

请求体为 `multipart/form-data`。

**请求**

```
POST http://<服务器IP>:8100/display
Content-Type: multipart/form-data
```

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `image` | file | **是** | — | 图片文件，支持 JPEG、PNG、BMP、WEBP 等常见格式 |
| `canvas` | string | 否 | `EPD_CANVAS` 环境变量 | 画布尺寸规格，如 `7.5_800_480` |
| `driver` | string | 否 | `EPD_DRIVER` 环境变量 | 驱动代码，如 `07`、`08`（UC8159） |
| `dither_mode` | string | 否 | `EPD_DITHER_MODE` 环境变量 | 颜色模式，见[颜色模式说明](#颜色模式说明) |
| `contrast` | float | 否 | `1.0` | 对比度系数，范围 `0.1` ~ `3.0` |
| `dither_strength` | float | 否 | `1.0` | 抖动强度，`0.0` 表示无抖动，`1.0` 为标准 |
| `interleaved_count` | integer | 否 | `5` | BLE 无响应写入交错次数，影响传输稳定性 |

**curl 示例**

```bash
curl -X POST http://192.168.1.100:8100/display \
  -F "image=@/path/to/photo.jpg" \
  -F "canvas=7.5_800_480" \
  -F "dither_mode=threeColor" \
  -F "contrast=1.2"
```

**成功响应** `200 OK`

```json
{
  "status": "ok",
  "canvas": "7.5_800_480",
  "mode": "threeColor"
}
```

**失败响应** `409 Conflict`（设备忙）

```json
{
  "detail": "设备正在传输中，请等待完成。当前: 黑白 98/210 (47%) 3.1s"
}
```

**失败响应** `503 Service Unavailable`（未连接）

```json
{
  "detail": "BLE 设备未连接，请先调用 /connect"
}
```

> **图像处理流程：** 服务器接收图片后依次执行：缩放至画布尺寸 → 调整对比度 → Floyd-Steinberg 抖动算法 → 转换为 EPD 字节格式 → BLE 分块传输。

---

### POST /display_url

从指定 URL 下载图片并发送到电子墨水屏显示。适合与 HA 摄像头截图、外部图片服务等场景配合使用。

**请求**

```
POST http://<服务器IP>:8100/display_url
Content-Type: application/x-www-form-urlencoded
```

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `image_url` | string | **是** | — | 图片 URL，服务器端直接下载 |
| `canvas` | string | 否 | `EPD_CANVAS` | 画布尺寸规格 |
| `driver` | string | 否 | `EPD_DRIVER` | 驱动代码 |
| `dither_mode` | string | 否 | `EPD_DITHER_MODE` | 颜色模式 |
| `contrast` | float | 否 | `1.0` | 对比度 |
| `dither_strength` | float | 否 | `1.0` | 抖动强度 |
| `interleaved_count` | integer | 否 | `5` | BLE 交错写入次数 |

**curl 示例**

```bash
curl -X POST http://192.168.1.100:8100/display_url \
  -d "image_url=http://192.168.1.10:8123/local/epd/dashboard.png" \
  -d "canvas=7.5_800_480" \
  -d "dither_mode=blackWhiteColor"
```

**成功响应** `200 OK`

```json
{
  "status": "ok"
}
```

**失败响应** `400 Bad Request`（URL 下载失败）

```json
{
  "detail": "下载图片失败: <urlopen error ...>"
}
```

---

### GET /canvases

返回所有受支持的画布尺寸列表。

**请求**

```
GET http://<服务器IP>:8100/canvases
```

**响应示例** `200 OK`

```json
[
  { "name": "1.54_152_152", "width": 152, "height": 152 },
  { "name": "1.54_200_200", "width": 200, "height": 200 },
  { "name": "2.13_212_104", "width": 212, "height": 104 },
  { "name": "7.5_800_480",  "width": 800, "height": 480 },
  { "name": "10.2_960_640", "width": 960, "height": 640 }
]
```

共 22 种规格，完整列表见[支持的屏幕尺寸](EPD显示屏集成-部署与使用文档.md#13-支持的屏幕尺寸)。

---

## HA 集成内部 API

以下接口由 HA 集成注册，运行于 HA 进程内部。所有请求均需要有效的 HA Bearer Token。

**获取长期访问令牌：**  
在 HA 界面 → 左下角头像 → 安全 → 长期访问令牌 → 创建令牌。

---

### POST /api/epd_display/upload

上传图片字节并直接发送到电子墨水屏（通过 HA 转发到控制服务器）。编辑器"发送图片"页使用此接口。

**请求**

```
POST http://<HA地址>:8123/api/epd_display/upload
Authorization: Bearer <token>
Content-Type: multipart/form-data
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `image` | file | **是** | 图片文件 |
| `canvas` | string | 否 | 画布尺寸，省略时使用集成默认配置 |
| `driver` | string | 否 | 驱动代码 |
| `dither_mode` | string | 否 | 颜色模式 |
| `contrast` | float | 否 | 对比度，默认 `1.0` |
| `dither_strength` | float | 否 | 抖动强度，默认 `1.0` |

**成功响应** `200 OK`

```json
{
  "status": "ok",
  "result": { "status": "ok", "canvas": "7.5_800_480", "mode": "threeColor" }
}
```

---

### POST /api/epd_display/display_url

通过 HA 转发 URL 图片发送请求到控制服务器。请求体为 JSON。

**请求**

```
POST http://<HA地址>:8123/api/epd_display/display_url
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{
  "image_url": "http://192.168.1.10:8123/local/epd/dashboard.png",
  "canvas": "7.5_800_480",
  "driver": "07",
  "dither_mode": "threeColor",
  "contrast": 1.0,
  "dither_strength": 1.0
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `image_url` | string | **是** | 图片 URL |
| `canvas` | string | 否 | 画布尺寸 |
| `driver` | string | 否 | 驱动代码 |
| `dither_mode` | string | 否 | 颜色模式 |
| `contrast` | float | 否 | 对比度 |
| `dither_strength` | float | 否 | 抖动强度 |

**成功响应** `200 OK`

```json
{
  "status": "ok",
  "result": { "status": "ok" }
}
```

---

### GET /api/epd_display/entities

返回当前 HA 中所有实体的状态列表，供编辑器实体选择器使用。

**请求**

```
GET http://<HA地址>:8123/api/epd_display/entities
Authorization: Bearer <token>
```

**响应示例** `200 OK`

```json
[
  {
    "entity_id": "sensor.outdoor_temperature",
    "state": "22.3",
    "name": "室外温度",
    "unit": "°C",
    "device_class": "temperature"
  },
  {
    "entity_id": "binary_sensor.front_door",
    "state": "off",
    "name": "前门",
    "unit": "",
    "device_class": "door"
  }
]
```

**响应字段说明**

| 字段 | 类型 | 说明 |
|------|------|------|
| `entity_id` | string | 实体 ID |
| `state` | string | 当前状态值 |
| `name` | string | 友好名称（`friendly_name` 属性） |
| `unit` | string | 单位（`unit_of_measurement` 属性），无则为空字符串 |
| `device_class` | string | 设备类型（`device_class` 属性），无则为空字符串 |

---

### GET /api/epd_display/config

返回集成的当前配置信息及可选值列表，供编辑器初始化下拉菜单使用。

**请求**

```
GET http://<HA地址>:8123/api/epd_display/config
Authorization: Bearer <token>
```

**响应示例** `200 OK`

```json
{
  "canvas_options": [
    "1.54_152_152",
    "7.5_800_480",
    "10.2_960_640"
  ],
  "dither_modes": [
    "blackWhiteColor",
    "threeColor",
    "fourColor",
    "sixColor"
  ],
  "defaults": {
    "canvas": "7.5_800_480",
    "driver": "07",
    "dither_mode": "threeColor",
    "contrast": 1.0,
    "dither_strength": 1.0
  }
}
```

---

### GET /api/epd_display/media_list

扫描 HA 服务器上的图片文件，供编辑器"从 HA 选择图片"功能使用。

扫描目录：
- `<config>/www/`（可通过 `/local/` URL 访问）
- `<config>/epd_images/`（集成生成的图片，通过代理访问）

**请求**

```
GET http://<HA地址>:8123/api/epd_display/media_list
Authorization: Bearer <token>
```

| 查询参数 | 类型 | 必填 | 说明 |
|----------|------|------|------|
| `subdir` | string | 否 | 在 `www/` 内的子目录路径，如 `epd_icons` |
| `search` | string | 否 | 文件名过滤关键词（不区分大小写） |

**请求示例**

```
GET /api/epd_display/media_list?subdir=epd_icons&search=weather
```

**响应示例** `200 OK`

```json
{
  "files": [
    {
      "name": "weather_sunny.svg",
      "path": "www/epd_icons/weather_sunny.svg",
      "abs_path": "/config/www/epd_icons/weather_sunny.svg",
      "size": 1248,
      "preview_url": "/local/epd_icons/weather_sunny.svg",
      "source": "www/epd_icons"
    },
    {
      "name": "dashboard.png",
      "path": "epd_images/dashboard.png",
      "abs_path": "/config/epd_images/dashboard.png",
      "size": 54320,
      "preview_url": "/api/epd_display/media_proxy?path=epd_images/dashboard.png",
      "source": "epd_images"
    }
  ],
  "dirs": [
    {
      "name": "icons",
      "path": "www/icons",
      "type": "dir"
    }
  ],
  "current": "epd_icons"
}
```

**响应字段说明**

| 字段 | 类型 | 说明 |
|------|------|------|
| `files[].name` | string | 文件名 |
| `files[].path` | string | 相对于 HA config 目录的路径（可用于 `background_image` 等字段） |
| `files[].abs_path` | string | 文件绝对路径 |
| `files[].size` | integer | 文件大小（字节） |
| `files[].preview_url` | string | 可在浏览器中直接访问的预览 URL |
| `files[].source` | string | 来源目录 |
| `dirs` | array | 同级子目录列表 |
| `current` | string | 当前浏览的 subdir 路径 |

---

### GET /api/epd_display/media_proxy

代理访问 HA 服务器本地图片文件（仅限 `www/`、`epd_images/`、`epd_templates/` 目录内）。

**请求**

```
GET http://<HA地址>:8123/api/epd_display/media_proxy?path=epd_images/dashboard.png
Authorization: Bearer <token>
```

| 查询参数 | 类型 | 必填 | 说明 |
|----------|------|------|------|
| `path` | string | **是** | 相对于 HA config 目录的文件路径，必须以 `www/`、`epd_images/` 或 `epd_templates/` 开头 |

**成功响应** `200 OK`

返回图片二进制内容，`Content-Type` 根据文件扩展名自动设置（`image/png`、`image/jpeg` 等）。

**失败响应**

| 状态码 | 原因 |
|--------|------|
| `400` | 文件扩展名不是图片格式 |
| `403` | 路径不在允许的安全目录内 |
| `404` | 文件不存在 |

---

### GET /api/epd_display/calendar_events

从 HA 日历实体获取指定月份的事件列表，供编辑器日历组件预览使用。

**请求**

```
GET http://<HA地址>:8123/api/epd_display/calendar_events
Authorization: Bearer <token>
```

| 查询参数 | 类型 | 必填 | 说明 |
|----------|------|------|------|
| `entity_id` | string | **是** | 日历实体 ID，可重复传入多个 |
| `year` | integer | 否 | 年份，默认当前年 |
| `month` | integer | 否 | 月份（1-12），默认当前月 |

**请求示例**

```
GET /api/epd_display/calendar_events?entity_id=calendar.home&entity_id=calendar.work&year=2025&month=3
```

**响应示例** `200 OK`

```json
{
  "events": [
    {
      "summary": "团队会议",
      "start": "2025-03-10T09:00:00+08:00",
      "end": "2025-03-10T10:00:00+08:00",
      "all_day": false
    },
    {
      "summary": "春节假期",
      "start": "2025-01-28",
      "end": "2025-02-04",
      "all_day": true
    }
  ],
  "year": 2025,
  "month": 3
}
```

**失败响应** `400 Bad Request`

```json
{
  "error": "No entity_id provided"
}
```

---

### POST /api/epd_display/generate

根据元素列表在 HA 服务器端生成图片并保存到 `<config>/epd_images/` 目录。

**请求**

```
POST http://<HA地址>:8123/api/epd_display/generate
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{
  "width": 800,
  "height": 480,
  "background_color": "white",
  "background_image": "/config/www/epd/bg.jpg",
  "output_filename": "my_dashboard.png",
  "elements": [ ]
}
```

**请求字段说明**

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `width` | integer | **是** | — | 画布宽度（像素） |
| `height` | integer | **是** | — | 画布高度（像素） |
| `background_color` | string | 否 | `"white"` | 背景色，支持颜色名称或 `#RRGGBB` 十六进制 |
| `background_image` | string | 否 | — | 背景图片的绝对路径，会被缩放至画布尺寸 |
| `output_filename` | string | 否 | `"epd_editor_output.png"` | 输出文件名 |
| `elements` | array | 否 | `[]` | 绘图元素列表，详见[元素类型参数参考](#元素类型参数参考) |

**成功响应** `200 OK`

```json
{
  "status": "ok",
  "path": "/config/epd_images/my_dashboard.png"
}
```

**失败响应** `200 OK`（注意：错误仍返回 200）

```json
{
  "error": "不支持的颜色模式: unknownMode"
}
```

> **注意：** `entity_text`、`textbox_entity`、`computed_text`、`textbox_computed` 和 `calendar` 元素中的动态数据（HA 实体状态、Jinja2 模板）会在生成图片时由 HA 实时解析并注入。

---

### GET /api/epd_display/templates

返回已保存的模板名称列表。

**请求**

```
GET http://<HA地址>:8123/api/epd_display/templates
Authorization: Bearer <token>
```

**响应示例** `200 OK`

```json
{
  "templates": [
    "home_dashboard",
    "morning_brief",
    "sensor_panel"
  ]
}
```

---

### GET /api/epd_display/templates/{name}

获取指定名称的模板内容（JSON 格式）。

**请求**

```
GET http://<HA地址>:8123/api/epd_display/templates/home_dashboard
Authorization: Bearer <token>
```

**成功响应** `200 OK`

返回模板 JSON 对象，结构与 `/api/epd_display/generate` 的请求体相同。

```json
{
  "width": 800,
  "height": 480,
  "background_color": "white",
  "output_filename": "home_dashboard.png",
  "elements": [
    {
      "type": "text",
      "x": 20,
      "y": 20,
      "text": "家庭状态",
      "color": "black",
      "font_size": 36
    }
  ]
}
```

**失败响应** `404 Not Found`

```json
{
  "error": "not found"
}
```

---

### PUT /api/epd_display/templates/{name}

保存或覆盖指定名称的模板。模板文件存储于 `<config>/epd_templates/<name>.json`。

**请求**

```
PUT http://<HA地址>:8123/api/epd_display/templates/home_dashboard
Authorization: Bearer <token>
Content-Type: application/json
```

请求体为模板 JSON 对象，结构与 `/api/epd_display/generate` 请求体相同。

**成功响应** `200 OK`

```json
{
  "status": "ok",
  "path": "/config/epd_templates/home_dashboard.json"
}
```

---

### DELETE /api/epd_display/templates/{name}

删除指定名称的模板文件。

**请求**

```
DELETE http://<HA地址>:8123/api/epd_display/templates/home_dashboard
Authorization: Bearer <token>
```

**成功响应** `200 OK`

```json
{
  "status": "ok"
}
```

**模板不存在时响应** `200 OK`

```json
{
  "status": "not_found"
}
```

---

### POST /api/epd_display/template_preview

在 HA 上下文中实时渲染一段 Jinja2 模板字符串，返回计算结果。供编辑器"测试模板"和"computed_text 预览"功能使用。

**请求**

```
POST http://<HA地址>:8123/api/epd_display/template_preview
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{
  "template": "室外温度: {{ states('sensor.outdoor_temperature') }}°C"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `template` | string | **是** | 要渲染的 Jinja2 模板字符串 |

**成功响应** `200 OK`

```json
{
  "result": "室外温度: 22.3°C"
}
```

**失败响应** `400 Bad Request`（模板语法错误）

```json
{
  "error": "UndefinedError: 'sensor.nonexistent' is undefined"
}
```

---

### POST /api/epd_display/parse_yaml

将 YAML 字符串解析为 JSON 对象，供编辑器"YAML 代码编辑器"功能使用。

**请求**

```
POST http://<HA地址>:8123/api/epd_display/parse_yaml
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{
  "yaml": "width: 800\nheight: 480\nelements:\n  - type: text\n    x: 20\n    y: 20\n    text: Hello"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `yaml` | string | **是** | 要解析的 YAML 字符串 |

**成功响应** `200 OK`

```json
{
  "result": {
    "width": 800,
    "height": 480,
    "elements": [
      { "type": "text", "x": 20, "y": 20, "text": "Hello" }
    ]
  }
}
```

**失败响应** `400 Bad Request`

```json
{
  "error": "YAML 根节点必须是字典"
}
```

---

## 元素类型参数参考

以下所有元素类型均用于 `/api/epd_display/generate` 和 `render_template` 服务的 `elements` 数组中。

### rectangle — 矩形

```json
{
  "type": "rectangle",
  "x": 10,
  "y": 10,
  "width": 200,
  "height": 100,
  "outline": "#000000",
  "fill": "#f0f0f0",
  "line_width": 2
}
```

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `x`, `y` | integer | **是** | — | 左上角坐标 |
| `width`, `height` | integer | **是** | — | 宽高（像素） |
| `outline` | string | 否 | `"black"` | 边框颜色 |
| `fill` | string | 否 | 无填充 | 填充颜色，省略或为空表示透明 |
| `line_width` | integer | 否 | `1` | 边框线宽（像素） |

---

### line — 线段

```json
{
  "type": "line",
  "points": [0, 100, 800, 100],
  "color": "#333333",
  "line_width": 2
}
```

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `points` | array | **是** | — | 坐标数组 `[x1, y1, x2, y2]`，至少 4 个元素 |
| `color` | string | 否 | `"black"` | 线段颜色 |
| `line_width` | integer | 否 | `1` | 线宽（像素） |

---

### point — 圆点

```json
{
  "type": "point",
  "x": 100,
  "y": 100,
  "radius": 6,
  "color": "#ff0000"
}
```

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `x`, `y` | integer | **是** | — | 圆心坐标 |
| `radius` | integer | 否 | `3` | 半径（像素） |
| `color` | string | 否 | `"black"` | 填充颜色 |

---

### text — 单行文字

```json
{
  "type": "text",
  "x": 20,
  "y": 50,
  "text": "Hello, 世界！",
  "color": "black",
  "font_size": 28,
  "font_path": "/config/www/epd_font.ttf"
}
```

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `x`, `y` | integer | **是** | — | 文字左上角坐标 |
| `text` | string | **是** | — | 文字内容，不自动换行 |
| `color` | string | 否 | `"black"` | 文字颜色 |
| `font_size` | integer | 否 | `20` | 字号（像素） |
| `font_path` | string | 否 | 自动查找 | 字体文件绝对路径 |

---

### textbox — 自动换行文本框

文字超过宽度时自动换行，超过高度时截断并显示省略号。

```json
{
  "type": "textbox",
  "x": 20,
  "y": 50,
  "width": 350,
  "height": 150,
  "text": "这是一段会自动换行的文字，不会超出文本框范围。",
  "color": "black",
  "font_size": 22,
  "padding": 8,
  "line_spacing": 3,
  "align": "left",
  "valign": "top",
  "bg_color": "#f5f5f5",
  "border_color": "#999999",
  "border_width": 1,
  "clip": true,
  "font_path": ""
}
```

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `x`, `y` | integer | **是** | — | 文本框左上角坐标 |
| `width`, `height` | integer | **是** | — | 文本框尺寸（像素） |
| `text` | string | **是** | — | 文字内容，`\n` 表示强制换行 |
| `color` | string | 否 | `"black"` | 文字颜色 |
| `font_size` | integer | 否 | `20` | 字号（像素） |
| `padding` | integer | 否 | `4` | 内边距（像素） |
| `line_spacing` | integer | 否 | `2` | 行间距（像素，叠加在字号之上） |
| `align` | string | 否 | `"left"` | 水平对齐：`left` / `center` / `right` |
| `valign` | string | 否 | `"top"` | 垂直对齐：`top` / `middle` / `bottom` |
| `bg_color` | string | 否 | 无背景 | 背景填充颜色，省略或为空则透明 |
| `border_color` | string | 否 | 无边框 | 边框颜色，省略或为空则不绘制边框 |
| `border_width` | integer | 否 | `1` | 边框线宽（像素） |
| `clip` | boolean | 否 | `true` | 超出高度时是否截断并加省略号 |
| `font_path` | string | 否 | 自动查找 | 字体文件路径 |

---

### textbox_entity — 实体状态文本框

与 `textbox` 参数相同，但文字内容来自 HA 实体，额外支持：

```json
{
  "type": "textbox_entity",
  "x": 20, "y": 50, "width": 350, "height": 100,
  "entity_id": "sensor.weather_description",
  "prefix": "天气: ",
  "suffix": "",
  "color": "black",
  "font_size": 22,
  "padding": 8
}
```

| 额外参数 | 类型 | 必填 | 说明 |
|----------|------|------|------|
| `entity_id` | string | **是** | HA 实体 ID |
| `prefix` | string | 否 | 文字前缀 |
| `suffix` | string | 否 | 文字后缀 |

最终显示内容为：`{prefix}{实体状态}{suffix}`

---

### textbox_computed — 代码模板文本框

与 `textbox` 参数相同，但文字内容来自 Jinja2 模板渲染结果，额外支持：

```json
{
  "type": "textbox_computed",
  "x": 20, "y": 160, "width": 760, "height": 120,
  "template": "今日天气: {{ states('sensor.weather') }}\n气温: {{ states('sensor.outdoor_temp') }}°C",
  "color": "black",
  "font_size": 20,
  "padding": 8,
  "align": "left"
}
```

| 额外参数 | 类型 | 必填 | 说明 |
|----------|------|------|------|
| `template` | string | **是** | Jinja2 模板字符串，可使用所有 HA 模板函数 |

---

### entity_text — 实体状态单行文字

```json
{
  "type": "entity_text",
  "x": 20,
  "y": 100,
  "entity_id": "sensor.outdoor_temperature",
  "prefix": "室外: ",
  "suffix": "°C",
  "color": "black",
  "font_size": 26
}
```

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `x`, `y` | integer | **是** | — | 文字坐标 |
| `entity_id` | string | **是** | — | HA 实体 ID |
| `prefix` | string | 否 | `""` | 前缀文字 |
| `suffix` | string | 否 | `""` | 后缀文字 |
| `color` | string | 否 | `"black"` | 文字颜色 |
| `font_size` | integer | 否 | `20` | 字号 |
| `font_path` | string | 否 | 自动查找 | 字体路径 |

---

### computed_text — Jinja2 模板文字 / 图标

输出内容可以是文字，也可以是图片路径（自动以图片方式渲染）或 SVG XML 内容。

```json
{
  "type": "computed_text",
  "x": 600,
  "y": 20,
  "template": "{{ states('sensor.outdoor_temperature') }}°C",
  "color": "black",
  "font_size": 28
}
```

**图标模式（输出图片路径）：**

```json
{
  "type": "computed_text",
  "x": 700,
  "y": 20,
  "width": 80,
  "height": 80,
  "template": "/config/www/icons/{{ states('sensor.weather') }}.svg",
  "opacity": 1.0,
  "keep_aspect": true
}
```

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `x`, `y` | integer | **是** | — | 坐标 |
| `template` | string | **是** | — | Jinja2 模板，输出文字则显示文字，输出图片路径则渲染图片，输出 `<svg...>` 则渲染 SVG |
| `color` | string | 否 | `"black"` | 文字模式下的字色 |
| `font_size` | integer | 否 | `20` | 文字模式下的字号 |
| `width`, `height` | integer | 否 | — | 图片模式下的尺寸 |
| `opacity` | float | 否 | `1.0` | 图片模式下的透明度（0.0-1.0） |
| `keep_aspect` | boolean | 否 | `true` | 图片模式下是否保持宽高比 |

---

### image — 静态图片/图标

```json
{
  "type": "image",
  "x": 700,
  "y": 20,
  "width": 80,
  "height": 80,
  "path": "/config/www/epd_icons/weather_sunny.svg",
  "opacity": 1.0,
  "keep_aspect": true
}
```

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `x`, `y` | integer | **是** | — | 左上角坐标 |
| `width`, `height` | integer | **是** | — | 显示尺寸（像素） |
| `path` | string | 是* | — | 图片绝对路径，支持 PNG/JPEG/BMP/WEBP/GIF/SVG |
| `svg_content` | string | 是* | — | SVG XML 字符串（与 `path` 二选一） |
| `opacity` | float | 否 | `1.0` | 透明度（0.0-1.0） |
| `keep_aspect` | boolean | 否 | `true` | 是否保持宽高比 |

*`path` 和 `svg_content` 至少提供一个。

---

### calendar — 月历组件

```json
{
  "type": "calendar",
  "x": 400,
  "y": 20,
  "width": 380,
  "height": 280,
  "lang": "zh",
  "first_weekday": 0,
  "year": null,
  "month": null,
  "calendar_entities": ["calendar.home", "calendar.work"],
  "show_event_text": true,
  "max_events_per_cell": 2,
  "header_font_size": 18,
  "weekday_font_size": 12,
  "day_font_size": 15,
  "event_font_size": 9,
  "font_path": ""
}
```

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `x`, `y` | integer | **是** | — | 左上角坐标 |
| `width`, `height` | integer | **是** | — | 日历尺寸 |
| `lang` | string | 否 | `"zh"` | 语言：`zh`（中文）/ `en`（英文） |
| `first_weekday` | integer | 否 | `0` | 每周第一天：`0` = 周一，`6` = 周日 |
| `year` | integer\|null | 否 | 当前年 | 显示年份，`null` 为当前年 |
| `month` | integer\|null | 否 | 当前月 | 显示月份（1-12），`null` 为当前月 |
| `calendar_entities` | array | 否 | `[]` | HA 日历实体 ID 列表，用于显示事件 |
| `show_event_text` | boolean | 否 | `true` | 是否在日期格内显示事件标题 |
| `max_events_per_cell` | integer | 否 | `2` | 每个日期格最多显示几条事件 |
| `header_font_size` | integer | 否 | `18` | 标题（年月）字号 |
| `weekday_font_size` | integer | 否 | `12` | 星期行字号 |
| `day_font_size` | integer | 否 | `15` | 日期数字字号 |
| `event_font_size` | integer | 否 | `9` | 事件文字字号 |
| `font_path` | string | 否 | 自动查找 | 字体路径 |

---

## 颜色模式说明

| 模式值 | 说明 | BLE 传输路数 | 适用屏幕 |
|--------|------|-------------|---------|
| `blackWhiteColor` | 黑白，每像素 1 bit，传输最快 | 1 路（bw） | 所有屏幕 |
| `threeColor` | 黑白红三色，两平面分别传输 | 2 路（bw + red） | 含红色通道 |
| `fourColor` | 黑白红黄，每像素 2 bit | 1 路（color） | 四色屏 |
| `sixColor` | 六色（黑白红黄绿蓝），列优先编码 | 1 路（color） | 彩色 E-Ink 屏 |

**驱动代码特殊处理：**  
当 `driver` 为 `08` 或 `09`（UC8159 驱动）时，三色和黑白模式会将双平面数据合并为 UC8159 专用的 4-bit per pixel 格式后再传输。

---

## 错误码说明

### 控制服务器

| HTTP 状态码 | 含义 |
|-------------|------|
| `200 OK` | 请求成功 |
| `400 Bad Request` | 请求参数错误（如 URL 无法下载） |
| `409 Conflict` | 设备正在传输图像，请等待完成后重试 |
| `500 Internal Server Error` | 服务器内部错误（BLE 通信失败、图像处理失败等） |
| `503 Service Unavailable` | BLE 设备未连接，请先调用 `/connect` |

### HA 集成内部 API

| HTTP 状态码 | 含义 |
|-------------|------|
| `200 OK` | 请求成功（部分接口即使出错也返回 200，需检查响应体中的 `error` 字段） |
| `400 Bad Request` | 参数缺失或格式错误 |
| `401 Unauthorized` | 未提供或令牌无效 |
| `403 Forbidden` | 访问了不允许的目录（media_proxy） |
| `404 Not Found` | 模板或文件不存在 |
| `500 Internal Server Error` | 服务器内部错误 |

---

*API 文档版本：v4.17 | 最后更新：2025 年*
