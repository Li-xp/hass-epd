"""
EPD BLE 电子墨水屏控制服务
============================
将 epd.py 封装为 HTTP API，供 Home Assistant 通过 RESTful 调用。

部署:
  1. 将 epd.py 和本文件放在同一目录
  2. pip install fastapi uvicorn python-multipart bleak Pillow numpy
  3. python epd_server.py

服务默认监听 0.0.0.0:8100
"""

import asyncio
import os
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

from epd import (
    EPDBleClient,
    EpdCmd,
    canvas_sizes,
    process_image,
    convert_uc8159,
)

# ===================== 全局状态 =====================
epd_client: Optional[EPDBleClient] = None
DEFAULT_DEVICE_NAME = os.getenv("EPD_DEVICE_NAME", "NRF_EPD_3D56")
DEFAULT_CANVAS = os.getenv("EPD_CANVAS", "7.5_800_480")
DEFAULT_DRIVER = os.getenv("EPD_DRIVER", "07")
DEFAULT_DITHER_MODE = os.getenv("EPD_DITHER_MODE", "threeColor")
UPLOAD_DIR = os.getenv("EPD_UPLOAD_DIR", "/tmp/epd_images")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ── 传输状态 ──────────────────────────────────────────────
class TransferState:
    def __init__(self):
        self.busy: bool = False          # 是否正在传输
        self.step: str = ""              # 当前步骤：bw / color / red
        self.chunk: int = 0             # 当前块序号
        self.total: int = 0             # 总块数
        self.elapsed: float = 0.0       # 已用时间(秒)
        self.started_at: float = 0.0    # 传输开始时间戳
        self.finished_at: float = 0.0   # 传输结束时间戳
        self.last_error: str = ""       # 最后一次错误信息
        self._lock = asyncio.Lock()

    def to_dict(self) -> dict:
        if self.busy:
            pct = round(self.chunk / self.total * 100) if self.total else 0
            step_cn = {"bw": "黑白", "color": "颜色", "red": "红色"}.get(self.step, self.step)
            return {
                "busy": True,
                "status": "transferring",
                "step": step_cn,
                "chunk": self.chunk,
                "total": self.total,
                "percent": pct,
                "elapsed": round(self.elapsed, 1),
                "message": f"{step_cn} {self.chunk}/{self.total} ({pct}%) {self.elapsed:.1f}s",
            }
        else:
            return {
                "busy": False,
                "status": "idle",
                "step": "",
                "chunk": 0,
                "total": 0,
                "percent": 0,
                "elapsed": round(self.finished_at - self.started_at, 1) if self.started_at else 0,
                "message": ("空闲" if not self.last_error else f"错误: {self.last_error}"),
                "last_error": self.last_error,
            }

transfer_state = TransferState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    auto_connect = os.getenv("EPD_AUTO_CONNECT", "false").lower() == "true"
    if auto_connect:
        try:
            await connect_device(DEFAULT_DEVICE_NAME)
        except Exception as e:
            print(f"[启动] 自动连接失败: {e}")
    yield
    if epd_client and epd_client.gatt_connected:
        await epd_client.disconnect()


app = FastAPI(
    title="EPD 电子墨水屏控制 API",
    description="HTTP 接口控制 BLE 电子墨水屏，可对接 Home Assistant",
    version="1.1.0",
    lifespan=lifespan,
)


async def connect_device(device_name: str):
    global epd_client
    if epd_client and epd_client.gatt_connected:
        await epd_client.disconnect()
    epd_client = EPDBleClient()
    await epd_client.connect(device_name=device_name)


def get_client() -> EPDBleClient:
    if not epd_client or not epd_client.gatt_connected:
        raise HTTPException(status_code=503, detail="BLE 设备未连接，请先调用 /connect")
    return epd_client


def check_not_busy():
    """如果正在传输，拒绝请求"""
    if transfer_state.busy:
        ts = transfer_state.to_dict()
        raise HTTPException(
            status_code=409,
            detail=f"设备正在传输中，请等待完成。当前: {ts['message']}"
        )


# 进度回调：由 epd.py 的 write_image 调用
def _progress_callback(step: str, chunk: int, total: int, elapsed: float):
    transfer_state.step = step
    transfer_state.chunk = chunk
    transfer_state.total = total
    transfer_state.elapsed = elapsed


# ===================== API 路由 =====================

@app.get("/status")
async def status():
    connected = epd_client is not None and epd_client.gatt_connected
    return {
        "connected": connected,
        "device": epd_client.ble_device.name if connected and epd_client.ble_device else None,
        "firmware": f"0x{epd_client.app_version:02x}" if connected else None,
        "mtu": epd_client.mtu_size if connected else None,
        "transfer": transfer_state.to_dict(),
    }


@app.post("/connect")
async def api_connect(device_name: str = Form(default=None)):
    check_not_busy()
    name = device_name or DEFAULT_DEVICE_NAME
    try:
        await connect_device(name)
        return {"status": "ok", "device": name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/disconnect")
async def api_disconnect():
    check_not_busy()
    if epd_client and epd_client.gatt_connected:
        await epd_client.disconnect()
    return {"status": "ok"}


@app.post("/clear")
async def api_clear():
    check_not_busy()
    client = get_client()
    success = await client.write(EpdCmd.CLEAR)
    if success:
        return {"status": "ok", "message": "清屏指令已发送"}
    raise HTTPException(status_code=500, detail="清屏失败")


@app.post("/refresh")
async def api_refresh():
    check_not_busy()
    client = get_client()
    success = await client.write(EpdCmd.REFRESH)
    if success:
        return {"status": "ok"}
    raise HTTPException(status_code=500, detail="刷新失败")


@app.post("/sleep")
async def api_sleep():
    check_not_busy()
    client = get_client()
    success = await client.write(EpdCmd.SLEEP)
    if success:
        return {"status": "ok"}
    raise HTTPException(status_code=500, detail="失败")


@app.post("/sync_time")
async def api_sync_time(mode: int = Form(default=1)):
    """
    同步时间并启动屏幕内置时钟/日历。
    mode=1: 全刷日历（完整日期+时间，画面清晰但会闪烁一次）
    mode=2: 局刷时钟（分针更新，无闪烁，推荐持续运行）
    """
    import struct
    check_not_busy()
    client = get_client()
    timestamp = int(time.time())
    timezone_offset = -(time.timezone // 3600)
    data = struct.pack(">Ibb", timestamp, timezone_offset, mode)
    success = await client.write(EpdCmd.SET_TIME, data)
    if success:
        mode_name = "日历（全刷）" if mode == 1 else "时钟（局刷）"
        return {"status": "ok", "mode": mode, "mode_name": mode_name,
                "message": f"时间同步成功，已启动{mode_name}模式"}
    raise HTTPException(status_code=500, detail="时间同步失败")


@app.post("/sys_reset")
async def api_sys_reset():
    """系统重置"""
    check_not_busy()
    client = get_client()
    success = await client.write(EpdCmd.SYS_RESET)
    if success:
        return {"status": "ok", "message": "系统重置指令已发送"}
    raise HTTPException(status_code=500, detail="系统重置失败")


async def _do_display(client, tmp_path, canvas_name, drv, mode,
                      contrast, dither_strength, interleaved_count):
    """执行传输，维护 transfer_state，完成后释放锁"""
    async with transfer_state._lock:
        transfer_state.busy = True
        transfer_state.started_at = time.time()
        transfer_state.last_error = ""
        transfer_state.chunk = 0
        transfer_state.total = 0
        transfer_state.elapsed = 0.0
    try:
        # 注入进度回调
        client._progress_cb = _progress_callback
        await client.send_image(
            image_path=tmp_path,
            canvas_size_name=canvas_name,
            epd_driver=drv,
            dither_mode=mode,
            contrast=contrast,
            dither_strength=dither_strength,
            interleaved_count=interleaved_count,
        )
    except Exception as e:
        transfer_state.last_error = str(e)
        raise
    finally:
        transfer_state.busy = False
        transfer_state.finished_at = time.time()
        client._progress_cb = None
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.post("/display")
async def api_display(
    image: UploadFile = File(...),
    canvas: str = Form(default=None),
    driver: str = Form(default=None),
    dither_mode: str = Form(default=None),
    contrast: float = Form(default=1.0),
    dither_strength: float = Form(default=1.0),
    interleaved_count: int = Form(default=5),
):
    """上传图片并显示到电子墨水屏"""
    check_not_busy()
    client = get_client()
    canvas_name = canvas or DEFAULT_CANVAS
    drv = driver or DEFAULT_DRIVER
    mode = dither_mode or DEFAULT_DITHER_MODE

    suffix = os.path.splitext(image.filename)[1] or ".jpg"
    tmp_path = os.path.join(UPLOAD_DIR, f"epd_{int(time.time())}{suffix}")
    with open(tmp_path, "wb") as f:
        f.write(await image.read())

    try:
        await _do_display(client, tmp_path, canvas_name, drv, mode,
                          contrast, dither_strength, interleaved_count)
        return {"status": "ok", "canvas": canvas_name, "mode": mode}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/display_url")
async def api_display_url(
    image_url: str = Form(...),
    canvas: str = Form(default=None),
    driver: str = Form(default=None),
    dither_mode: str = Form(default=None),
    contrast: float = Form(default=1.0),
    dither_strength: float = Form(default=1.0),
    interleaved_count: int = Form(default=5),
):
    """通过 URL 下载图片并显示（适合 HA 摄像头截图等场景）"""
    import urllib.request
    check_not_busy()
    client = get_client()
    canvas_name = canvas or DEFAULT_CANVAS
    drv = driver or DEFAULT_DRIVER
    mode = dither_mode or DEFAULT_DITHER_MODE

    tmp_path = os.path.join(UPLOAD_DIR, f"epd_{int(time.time())}.jpg")
    try:
        urllib.request.urlretrieve(image_url, tmp_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"下载图片失败: {e}")

    try:
        await _do_display(client, tmp_path, canvas_name, drv, mode,
                          contrast, dither_strength, interleaved_count)
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/canvases")
async def list_canvases():
    return canvas_sizes


if __name__ == "__main__":
    uvicorn.run("epd_server:app", host="0.0.0.0", port=8100, reload=False)
