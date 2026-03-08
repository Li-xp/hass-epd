import asyncio
import struct
import time
import math
from typing import Optional, List, Dict, Any
from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from PIL import Image, ImageEnhance, ImageOps
import numpy as np

# ===================== 核心常量定义 =====================
class EpdCmd:
    SET_PINS = 0x00
    INIT = 0x01
    CLEAR = 0x02
    SEND_CMD = 0x03
    SEND_DATA = 0x04
    REFRESH = 0x05
    SLEEP = 0x06
    SET_TIME = 0x20
    WRITE_IMG = 0x30  # v1.6
    SET_CONFIG = 0x90
    SYS_RESET = 0x91
    SYS_SLEEP = 0x92
    CFG_ERASE = 0x99

# 电子纸尺寸配置
canvas_sizes = [
    {"name": "1.54_152_152", "width": 152, "height": 152},
    {"name": "1.54_200_200", "width": 200, "height": 200},
    {"name": "2.13_212_104", "width": 212, "height": 104},
    {"name": "2.13_250_122", "width": 250, "height": 122},
    {"name": "2.66_296_152", "width": 296, "height": 152},
    {"name": "2.9_296_128", "width": 296, "height": 128},
    {"name": "2.9_384_168", "width": 384, "height": 168},
    {"name": "3.5_384_184", "width": 384, "height": 184},
    {"name": "3.7_416_240", "width": 416, "height": 240},
    {"name": "3.97_800_480", "width": 800, "height": 480},
    {"name": "4.2_400_300", "width": 400, "height": 300},
    {"name": "5.79_792_272", "width": 792, "height": 272},
    {"name": "5.83_600_448", "width": 600, "height": 448},
    {"name": "5.83_648_480", "width": 648, "height": 480},
    {"name": "7.5_640_384", "width": 640, "height": 384},
    {"name": "7.5_800_480", "width": 800, "height": 480},
    {"name": "7.5_880_528", "width": 880, "height": 528},
    {"name": "10.2_960_640", "width": 960, "height": 640},
    {"name": "10.85_1360_480", "width": 1360, "height": 480},
    {"name": "11.6_960_640", "width": 960, "height": 640},
    {"name": "4E_600_400", "width": 600, "height": 400},
    {"name": "7.3E6", "width": 480, "height": 800}
]

# BLE服务和特征值UUID（和原JS一致）
EPD_SERVICE_UUID = "62750001-d828-918d-fb46-b6c11c675aec"
EPD_CHAR_UUID = "62750002-d828-918d-fb46-b6c11c675aec"
VERSION_CHAR_UUID = "62750003-d828-918d-fb46-b6c11c675aec"

# ===================== 工具函数 =====================
def hex2bytes(hex_str: str) -> bytes:
    """十六进制字符串转bytes"""
    hex_str = hex_str.replace(" ", "").strip()
    return bytes.fromhex(hex_str)

def bytes2hex(data: bytes) -> str:
    """bytes转十六进制字符串"""
    return data.hex().upper()

def int_to_hex(int_in: int) -> str:
    """整数转小端序十六进制字符串"""
    hex_str = f"{int_in:04x}"
    return hex_str[2:] + hex_str[:2]

def adjust_contrast(image: Image.Image, contrast: float) -> Image.Image:
    """调整图像对比度（对应JS的adjustContrast）"""
    enhancer = ImageEnhance.Contrast(image)
    return enhancer.enhance(contrast)

# ===================== BLE通信核心类 =====================
class EPDBleClient:
    def __init__(self):
        self.client: Optional[BleakClient] = None
        self.ble_device = None
        self.gatt_connected = False
        self.app_version = 0x00
        self.mtu_size = 20  # 默认MTU
        self.msg_index = 0
        self.start_time = 0.0

    async def notify_callback(self, characteristic: BleakGATTCharacteristic, data: bytearray):
        """BLE通知回调（对应JS的handleNotify）"""
        data_bytes = bytes(data)
        if self.msg_index == 0:
            print(f"收到配置: {bytes2hex(data_bytes)}")
            # 解析引脚和驱动配置（简化版，可根据需要扩展）
            epd_pins = bytes2hex(data_bytes[:7])
            if len(data_bytes) > 10:
                epd_pins += bytes2hex(data_bytes[10:11])
            epd_driver = bytes2hex(data_bytes[7:8])
            print(f"解析到引脚配置: {epd_pins}, 驱动: {epd_driver}")
        else:
            try:
                msg = data_bytes.decode("utf-8").strip()
                print(f"收到设备消息: {msg}")
                if msg.startswith("mtu="):
                    self.mtu_size = int(msg.split("=")[1])
                    print(f"MTU更新为: {self.mtu_size}")
                elif msg.startswith("t="):
                    t = int(msg.split("=")[1]) + (time.timezone // 60)
                    remote_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t))
                    local_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                    print(f"远端时间: {remote_time}, 本地时间: {local_time}")
            except UnicodeDecodeError:
                print(f"收到二进制消息: {bytes2hex(data_bytes)}")
        self.msg_index += 1

    async def connect(self, device_name: Optional[str] = None):
        """连接BLE设备"""
        # 扫描设备
        print("扫描BLE设备...")
        devices = await BleakScanner.discover(timeout=30)
        target_device = None
        for d in devices:
            if device_name is None or (d.name and device_name in d.name):
                target_device = d
                break
        if not target_device:
            raise RuntimeError("未找到目标BLE设备")
        
        self.ble_device = target_device
        self.client = BleakClient(target_device)
        
        # 建立连接
        try:
            await self.client.connect()
            self.gatt_connected = True
            print(f"连接成功: {target_device.name} ({target_device.address})")

            # 获取版本特征值
            version_char = self.client.services.get_characteristic(VERSION_CHAR_UUID)
            if version_char:
                version_data = await self.client.read_gatt_char(version_char)
                self.app_version = version_data[0]
                print(f"固件版本: 0x{self.app_version:02x}")
                if self.app_version < 0x16:
                    print("警告: 固件版本过低，可能功能受限！")

            # 启用通知
            await self.client.start_notify(EPD_CHAR_UUID, self.notify_callback)
            print("已启用特征值通知")

            # 发送初始化指令
            await self.write(EpdCmd.INIT)
        except Exception as e:
            await self.disconnect()
            raise RuntimeError(f"连接失败: {str(e)}")

    async def disconnect(self):
        """断开连接"""
        if self.client and self.client.is_connected:
            await self.client.disconnect()
        self.gatt_connected = False
        self.msg_index = 0
        print("已断开BLE连接")

    async def write(self, cmd: int, data: Optional[bytes] = None, with_response: bool = True):
        """
        写入指令和数据（对应JS的write）
        :param cmd: 指令码
        :param data: 附加数据
        :param with_response: 是否需要响应
        """
        if not self.client or not self.client.is_connected:
            raise RuntimeError("BLE未连接")
        
        # 构造payload
        payload = bytearray([cmd])
        if data:
            payload.extend(data)
        
        # 仅调试用，可注释
        # print(f"发送数据: ⇑ {bytes2hex(payload)}")
        try:
            # bleak中write_gatt_char默认带响应，不带响应需指定response=False
            await self.client.write_gatt_char(
                EPD_CHAR_UUID, 
                payload, 
                response=with_response
            )
            return True
        except Exception as e:
            print(f"写入失败: {str(e)}")
            return False

    async def write_image(self, data: bytes, step: str = "bw", interleaved_count: int = 5):
        """
        分片发送图像数据（严格对齐JS的writeImage逻辑）
        :param data: 图像字节数据
        :param step: 传输步骤（bw/color/red）
        :param interleaved_count: 交错无响应写入次数（对应JS的interleavedcount）
        """
        if not data:
            raise ValueError("图像数据为空")
        
        # 1. 对齐JS的chunkSize计算（MTU-2）
        chunk_size = self.mtu_size - 2
        if chunk_size <= 0:
            raise ValueError(f"无效的MTU尺寸: {self.mtu_size}")
        
        # 2. 对齐JS的总块数计算（Math.round）
        total_chunks = round(len(data) / chunk_size)
        # 兼容数据长度不能被chunk_size整除的情况
        if len(data) % chunk_size != 0:
            total_chunks += 1
        
        chunk_idx = 0
        no_reply_count = interleaved_count
        self.start_time = time.time()

        for i in range(0, len(data), chunk_size):
            # 3. 对齐JS的进度显示（总用时+块数）
            elapsed = (time.time() - self.start_time)
            step_cn = "黑白" if step == "bw" else "颜色" if step == "color" else "红色"
            progress = f"{step_cn}块: {chunk_idx + 1}/{total_chunks}, 总用时: {elapsed:.2f}s"
            print(progress)

            # 4. 严格对齐JS的flag构造逻辑
            # step是bw则0x0F，否则0x00；i==0则不加0xF0，否则加0xF0
            flag = 0x0F if step == "bw" else 0x00
            if i != 0:
                flag |= 0xF0
            
            # 5. 构造单包payload（flag + 分片数据）
            chunk_data = data[i:i+chunk_size]
            payload = bytearray([flag]) + chunk_data

            # 6. 交错写入（无响应/有响应），对齐JS逻辑
            if no_reply_count > 0:
                await self.write(EpdCmd.WRITE_IMG, payload, with_response=False)
                no_reply_count -= 1
            else:
                await self.write(EpdCmd.WRITE_IMG, payload, with_response=True)
                no_reply_count = interleaved_count
            
            chunk_idx += 1

    # ===================== 电子纸控制接口 =====================
    async def set_driver(self, epd_pins: str, epd_driver: str):
        """设置引脚和驱动（对应JS的setDriver）"""
        pins_data = hex2bytes(epd_pins)
        driver_data = hex2bytes(epd_driver)
        await self.write(EpdCmd.SET_PINS, pins_data)
        await self.write(EpdCmd.INIT, driver_data)
        print("驱动配置已发送")

    async def sync_time(self, mode: int = 1):
        """同步时间（对应JS的syncTime）"""
        if mode == 2:
            confirm = input("提醒：时钟模式为全刷，可能产生残影，是否继续？(y/n)")
            if confirm.lower() != "y":
                return
        
        # 构造时间数据（时间戳+时区+模式）
        timestamp = int(time.time())
        timezone = -(time.timezone // 3600)  # 时区偏移（小时）
        data = struct.pack(">Ibb", timestamp, timezone, mode)
        if await self.write(EpdCmd.SET_TIME, data):
            print("时间同步成功！屏幕刷新完成前请勿操作")

    async def clear_screen(self):
        """清屏（对应JS的clearScreen）"""
        confirm = input("确认清屏？(y/n)")
        if confirm.lower() != "y":
            return
        if await self.write(EpdCmd.CLEAR):
            print("清屏指令已发送！屏幕刷新完成前请勿操作")

    async def send_custom_cmd(self, cmd_hex: str):
        """发送自定义指令（对应JS的sendcmd）"""
        cmd_bytes = hex2bytes(cmd_hex)
        if len(cmd_bytes) == 0:
            raise ValueError("指令不能为空")
        cmd = cmd_bytes[0]
        data = cmd_bytes[1:] if len(cmd_bytes) > 1 else None
        await self.write(cmd, data)
        print("自定义指令发送完成")

    def convert_uc8159(self, black_white_data: bytes, red_white_data: bytes) -> bytes:
        """适配UC8159驱动的像素格式转换（严格对齐JS的convertUC8159）"""
        half_length = len(black_white_data)
        payload_data = bytearray(half_length * 4)
        payload_idx = 0

        for i in range(half_length):
            black_data = black_white_data[i]
            color_data = red_white_data[i]
            for j in range(0, 8, 2):
                # 第一个像素
                if (color_data & 0x80) == 0x00:
                    data = 0x04  # 红色
                elif (black_data & 0x80) == 0x00:
                    data = 0x00  # 黑色
                else:
                    data = 0x03  # 白色
                data = (data << 4) & 0xFF
                black_data = (black_data << 1) & 0xFF
                color_data = (color_data << 1) & 0xFF

                # 第二个像素
                if (color_data & 0x80) == 0x00:
                    data |= 0x04
                elif (black_data & 0x80) == 0x00:
                    data |= 0x00
                else:
                    data |= 0x03
                black_data = (black_data << 1) & 0xFF
                color_data = (color_data << 1) & 0xFF

                payload_data[payload_idx] = data
                payload_idx += 1
        return bytes(payload_data)

    def process_image(self, image_path: str, canvas_width: int, canvas_height: int, 
                     dither_mode: str = "blackWhiteColor", contrast: float = 1.0, 
                     dither_strength: float = 1.0) -> bytes:
        """
        图像处理（裁剪、抖动、格式转换，对应JS的convertDithering+processImageData）
        :param image_path: 图片路径
        :param canvas_width: 画布宽度
        :param canvas_height: 画布高度
        :param dither_mode: 颜色模式（fourColor/threeColor/blackWhiteColor）
        :param contrast: 对比度
        :param dither_strength: 抖动强度
        :return: 处理后的图像字节数据
        """
        # 1. 加载并调整图片尺寸
        img = Image.open(image_path).convert("RGB")
        img = img.resize((canvas_width, canvas_height), Image.Resampling.LANCZOS)
        
        # 2. 调整对比度
        img = adjust_contrast(img, contrast)
        
        # 3. 抖动处理（Floyd-Steinberg抖动算法，对齐JS逻辑）
        if dither_mode in ["threeColor", "fourColor"]:
            # 三色/四色抖动（对齐JS的posterize+FloydSteinberg）
            img = ImageOps.posterize(img, 2)
            img = img.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
        else:
            # 黑白抖动
            img = img.convert("L")
            img = img.point(lambda x: 0 if x < 128 else 255, "1")
        
        # 4. 转换为电子纸格式字节数据（Uint8Array对齐）
        img_data = bytes(np.array(img).flatten())
        return img_data

    async def  send_image(self, image_path: str, canvas_size_name: str,
                         epd_driver: str = None,
                         dither_mode: str = "blackWhiteColor",
                         dither_alg: str = "floydSteinberg",
                         contrast: float = 1.0,
                         dither_strength: float = 1.0,
                         interleaved_count: int = 5):
        """
        发送图片到电子纸（严格对齐 JS sendimg, main.js 193-257）。

        完整流程:
          1. process_image (contrast → dither → processImageData)
          2. INIT
          3. writeImage (按颜色模式分发)
          4. REFRESH
        """
        if not self.gatt_connected:
            raise RuntimeError("BLE未连接")

        # 驱动（优先命令行参数，否则用设备自报值）
        if epd_driver is None:
            epd_driver = self.device_driver or "02"
        epd_driver = epd_driver.lower()

        canvas_size = next((s for s in canvas_sizes if s["name"] == canvas_size_name), None)
        if not canvas_size:
            raise ValueError(f"不支持的画布: {canvas_size_name}")
        w, h = canvas_size["width"], canvas_size["height"]

        print(f"图像: {image_path}")
        print(f"  画布: {w}x{h}, 模式: {dither_mode}, 驱动: {epd_driver}")

        # 1. 图像处理
        t0 = time.time()
        processed_data = process_image(
            image_path, w, h, dither_mode, dither_alg, contrast, dither_strength
        )
        print(f"  处理完成: {len(processed_data)} bytes ({time.time()-t0:.1f}s)")

        # 2. INIT（对齐 JS 第 220 行）
        await self.write(EpdCmd.INIT)

        # 3. 按模式发送（对齐 JS 第 222-245 行）
        send_start = time.time()

        if dither_mode == "fourColor":
            await self.write_image(processed_data, "color", interleaved_count)

        elif dither_mode == "threeColor":
            half_length = len(processed_data) // 2
            bw_data  = processed_data[:half_length]
            red_data = processed_data[half_length:]
            if epd_driver in ("08", "09"):
                uc_data = convert_uc8159(bw_data, red_data)
                await self.write_image(uc_data, "bw", interleaved_count)
            else:
                await self.write_image(bw_data, "bw", interleaved_count)
                await self.write_image(red_data, "red", interleaved_count)

        elif dither_mode == "blackWhiteColor":
            if epd_driver in ("08", "09"):
                empty = b'\xFF' * len(processed_data)
                uc_data = convert_uc8159(processed_data, empty)
                await self.write_image(uc_data, "bw", interleaved_count)
            else:
                await self.write_image(processed_data, "bw", interleaved_count)

        elif dither_mode == "sixColor":
            await self.write_image(processed_data, "color", interleaved_count)

        else:
            print(f"不支持的颜色模式: {dither_mode}")
            return

        # 4. REFRESH（对齐 JS 第 247 行）
        await self.write(EpdCmd.REFRESH)

        total = time.time() - send_start
        print(f"发送完成！传输耗时: {total:.1f}s")
        print("屏幕刷新完成前请不要操作。")

def convert_uc8159(black_white_data: bytes, red_white_data: bytes) -> bytes:
    """UC8159 驱动格式转换: 每字节(8像素) → 4字节(每像素4bit, 2像素/字节)"""
    half_length = len(black_white_data)
    payload = bytearray(half_length * 4)
    pi = 0
    for i in range(half_length):
        black_data = black_white_data[i]
        color_data = red_white_data[i]
        for _ in range(4):  # 8像素 / 2 = 4次循环
            # 第一个像素（高4位）
            if (color_data & 0x80) == 0x00:
                d = 0x04  # 红
            elif (black_data & 0x80) == 0x00:
                d = 0x00  # 黑
            else:
                d = 0x03  # 白
            d = (d << 4) & 0xFF
            black_data = (black_data << 1) & 0xFF
            color_data = (color_data << 1) & 0xFF
            # 第二个像素（低4位）
            if (color_data & 0x80) == 0x00:
                d |= 0x04
            elif (black_data & 0x80) == 0x00:
                d |= 0x00
            else:
                d |= 0x03
            black_data = (black_data << 1) & 0xFF
            color_data = (color_data << 1) & 0xFF
            payload[pi] = d
            pi += 1
    return bytes(payload[:pi])

def process_image(image_path: str, canvas_width: int, canvas_height: int,
                  dither_mode: str = "blackWhiteColor",
                  dither_alg: str = "floydSteinberg",
                  contrast: float = 1.0,
                  dither_strength: float = 1.0) -> bytes:
    """
    完整图像处理流水线（对齐 JS convertDithering → ditherImage → processImageData）。

    流程:
      1. 加载图片 → 缩放到画布尺寸
      2. adjustContrast
      3. ditherImage（Floyd-Steinberg 等）
      4. processImageData → EPD 字节流

    返回可直接传给 send_image 的 bytes。
    """
    # 1. 加载并缩放
    img = Image.open(image_path).convert("RGBA")
    img = img.resize((canvas_width, canvas_height), Image.Resampling.LANCZOS)

    # 构造 RGBA 平铺数组（对齐 JS 的 ImageData.data: Uint8ClampedArray）
    rgba = np.array(img, dtype=np.float64).reshape(-1)  # shape=(W*H*4,)

    # 2. 对比度（对齐 JS adjustContrast）
    if contrast != 1.0:
        for i in range(0, len(rgba), 4):
            rgba[i]   = min(255, max(0, (rgba[i]   - 128) * contrast + 128))
            rgba[i+1] = min(255, max(0, (rgba[i+1] - 128) * contrast + 128))
            rgba[i+2] = min(255, max(0, (rgba[i+2] - 128) * contrast + 128))

    # 3. 抖动
    print(f"  抖动算法: {dither_alg}, 强度: {dither_strength}")
    if dither_alg == "floydSteinberg":
        rgba = _floyd_steinberg_dither(rgba, canvas_width, canvas_height,
                                       dither_strength, dither_mode)
    elif dither_alg == "none":
        # 无抖动: 直接量化
        for y in range(canvas_height):
            for x in range(canvas_width):
                idx = (y * canvas_width + x) * 4
                c = _find_closest_color(int(rgba[idx]), int(rgba[idx+1]), int(rgba[idx+2]), dither_mode)
                rgba[idx] = c["r"]; rgba[idx+1] = c["g"]; rgba[idx+2] = c["b"]
    else:
        # 默认 Floyd-Steinberg
        rgba = _floyd_steinberg_dither(rgba, canvas_width, canvas_height,
                                       dither_strength, dither_mode)

    # 4. processImageData
    return _process_image_data(rgba, canvas_width, canvas_height, dither_mode)

# ---------- Floyd-Steinberg 抖动（对齐 dithering.js 第 120-181 行） ----------
def _floyd_steinberg_dither(data: np.ndarray, width: int, height: int,
                            strength: float, mode: str):
    """
    严格对齐 JS floydSteinbergDither：
    1. 在 tempData 上做误差扩散
    2. 最终用 findClosestColor 二次量化回 data
    
    data: shape=(H*W*4,) 的 int16 平铺数组（RGBA）。会被原地修改。
    返回修改后的 data（仍为 int16，调用方负责 clamp/cast）。
    """
    temp = data.copy()

    for y in range(height):
        for x in range(width):
            idx = (y * width + x) * 4
            r, g, b = int(temp[idx]), int(temp[idx+1]), int(temp[idx+2])

            closest = _find_closest_color(r, g, b, mode)

            err_r = (r - closest["r"]) * strength
            err_g = (g - closest["g"]) * strength
            err_b = (b - closest["b"]) * strength

            if x + 1 < width:
                ri = idx + 4
                temp[ri]   = min(255, max(0, temp[ri]   + err_r * 7 / 16))
                temp[ri+1] = min(255, max(0, temp[ri+1] + err_g * 7 / 16))
                temp[ri+2] = min(255, max(0, temp[ri+2] + err_b * 7 / 16))
            if y + 1 < height:
                if x > 0:
                    di = idx + width * 4 - 4
                    temp[di]   = min(255, max(0, temp[di]   + err_r * 3 / 16))
                    temp[di+1] = min(255, max(0, temp[di+1] + err_g * 3 / 16))
                    temp[di+2] = min(255, max(0, temp[di+2] + err_b * 3 / 16))
                di = idx + width * 4
                temp[di]   = min(255, max(0, temp[di]   + err_r * 5 / 16))
                temp[di+1] = min(255, max(0, temp[di+1] + err_g * 5 / 16))
                temp[di+2] = min(255, max(0, temp[di+2] + err_b * 5 / 16))
                if x + 1 < width:
                    di = idx + width * 4 + 4
                    temp[di]   = min(255, max(0, temp[di]   + err_r * 1 / 16))
                    temp[di+1] = min(255, max(0, temp[di+1] + err_g * 1 / 16))
                    temp[di+2] = min(255, max(0, temp[di+2] + err_b * 1 / 16))

    # 二次量化（对齐 JS 第 166-178 行）
    for y in range(height):
        for x in range(width):
            idx = (y * width + x) * 4
            r, g, b = int(temp[idx]), int(temp[idx+1]), int(temp[idx+2])
            closest = _find_closest_color(r, g, b, mode)
            data[idx]   = closest["r"]
            data[idx+1] = closest["g"]
            data[idx+2] = closest["b"]

    return data

def _find_closest_color(r: float, g: float, b: float, mode: str) -> dict:
    """
    对齐 dithering.js findClosestColor（第 77-118 行）。
    返回调色板中最近的颜色 dict。
    """
    if mode == "fourColor":
        palette = _four_color_palette
    elif mode == "threeColor":
        palette = _three_color_palette
    else:
        palette = _rgb_palette

    # 蓝色快捷路径（仅六色模式，对齐 JS 第 89-91 行）
    if mode != "fourColor" and mode != "threeColor":
        if r < 50 and g < 150 and b > 100:
            return _rgb_palette[2]  # 蓝色

    # 三色模式优先红色检测（对齐 JS 第 94-101 行）
    if mode == "threeColor":
        if r > 120 and r > g * 1.5 and r > b * 1.5:
            return _three_color_palette[2]  # 红色
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        return _three_color_palette[0] if luminance < 128 else _three_color_palette[1]

    # CIELAB 最近邻（对齐 JS 第 104-117 行）
    input_lab = _rgb_to_lab(r, g, b)
    min_dist = float('inf')
    closest = palette[0]
    for color in palette:
        c_lab = _rgb_to_lab(color["r"], color["g"], color["b"])
        d = _lab_distance(input_lab, c_lab)
        if d < min_dist:
            min_dist = d
            closest = color
    return closest


# ---------- 对比度调整（对齐 dithering.js adjustContrast 第 28-36 行） ----------
def _adjust_contrast_raw(data: np.ndarray, factor: float):
    """
    原地修改 RGBA 数组的 RGB 通道对比度。
    data: shape=(H*W*4,) 的 uint8 平铺数组。
    严格对齐 JS: pixel = clamp((pixel - 128) * factor + 128, 0, 255)
    """
    for i in range(0, len(data), 4):
        data[i]   = min(255, max(0, int((data[i]   - 128) * factor + 128)))
        data[i+1] = min(255, max(0, int((data[i+1] - 128) * factor + 128)))
        data[i+2] = min(255, max(0, int((data[i+2] - 128) * factor + 128)))

# ---------- 调色板（对齐 dithering.js 第 1-26 行） ----------
# 六色
_rgb_palette = [
    {"name": "黄色", "r": 255, "g": 255, "b": 0,   "value": 0xE2},
    {"name": "绿色", "r": 41,  "g": 204, "b": 20,  "value": 0x96},
    {"name": "蓝色", "r": 0,   "g": 0,   "b": 255, "value": 0x1D},
    {"name": "红色", "r": 255, "g": 0,   "b": 0,   "value": 0x4C},
    {"name": "黑色", "r": 0,   "g": 0,   "b": 0,   "value": 0x00},
    {"name": "白色", "r": 255, "g": 255, "b": 255, "value": 0xFF},
]
# 四色
_four_color_palette = [
    {"name": "黑色", "r": 0,   "g": 0,   "b": 0,   "value": 0x00},
    {"name": "白色", "r": 255, "g": 255, "b": 255, "value": 0x01},
    {"name": "红色", "r": 255, "g": 0,   "b": 0,   "value": 0x03},
    {"name": "黄色", "r": 255, "g": 255, "b": 0,   "value": 0x02},
]
# 三色
_three_color_palette = [
    {"name": "黑色", "r": 0,   "g": 0,   "b": 0,   "value": 0x00},
    {"name": "白色", "r": 255, "g": 255, "b": 255, "value": 0x01},
    {"name": "红色", "r": 255, "g": 0,   "b": 0,   "value": 0x02},
]

# ---------- 色彩空间转换（对齐 dithering.js 第 38-75 行） ----------
def _rgb_to_lab(r: float, g: float, b: float):
    """sRGB → CIELAB（对齐 JS rgbToLab）"""
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    r = ((r + 0.055) / 1.055) ** 2.4 if r > 0.04045 else r / 12.92
    g = ((g + 0.055) / 1.055) ** 2.4 if g > 0.04045 else g / 12.92
    b = ((b + 0.055) / 1.055) ** 2.4 if b > 0.04045 else b / 12.92
    r *= 100; g *= 100; b *= 100
    x = r * 0.4124 + g * 0.3576 + b * 0.1805
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = r * 0.0193 + g * 0.1192 + b * 0.9505
    x /= 95.047; y /= 100.0; z /= 108.883
    x = x ** (1/3) if x > 0.008856 else 7.787 * x + 16/116
    y = y ** (1/3) if y > 0.008856 else 7.787 * y + 16/116
    z = z ** (1/3) if z > 0.008856 else 7.787 * z + 16/116
    L = 116 * y - 16
    a = 500 * (x - y)
    bL = 200 * (y - z)
    return L, a, bL

def _lab_distance(lab1, lab2):
    """加权 CIELAB 距离（对齐 JS labDistance）"""
    dl = lab1[0] - lab2[0]
    da = lab1[1] - lab2[1]
    db = lab1[2] - lab2[2]
    return math.sqrt(0.2 * dl*dl + 3 * da*da + 3 * db*db)

# ---------- processImageData（对齐 dithering.js 第 620-716 行） ----------
def _process_image_data(data: np.ndarray, width: int, height: int, mode: str) -> bytes:
    """
    将抖动后的 RGBA 平铺数组转换为 EPD 字节流。
    严格对齐 JS processImageData 的每个分支。
    """
    if mode == "sixColor":
        # 六色: 列优先，每像素1字节 value
        out = bytearray(width * height)
        for y in range(height):
            for x in range(width):
                idx = (y * width + x) * 4
                r, g, b = int(data[idx]), int(data[idx+1]), int(data[idx+2])
                closest = _find_closest_color(r, g, b, mode)
                new_index = x * height + (height - 1 - y)
                out[new_index] = closest["value"]
        return bytes(out)

    elif mode == "fourColor":
        # 四色: 每像素2bit，4像素打包1字节，MSB在左
        out = bytearray(math.ceil(width * height / 4))
        for y in range(height):
            for x in range(width):
                idx = (y * width + x) * 4
                r, g, b = int(data[idx]), int(data[idx+1]), int(data[idx+2])
                closest = _find_closest_color(r, g, b, mode)
                color_val = closest["value"]  # 0x00/0x01/0x02/0x03
                new_index = (y * width + x) // 4
                shift = 6 - ((x % 4) * 2)
                out[new_index] |= (color_val << shift)
        return bytes(out)

    elif mode == "blackWhiteColor":
        # 黑白: 每像素1bit，8像素打包1字节，MSB在左（bit7=第一个像素）
        byte_width = math.ceil(width / 8)
        out = bytearray(byte_width * height)
        threshold = 140  # 对齐 JS 第 659 行
        for y in range(height):
            for x in range(width):
                idx = (y * width + x) * 4
                r, g, b = int(data[idx]), int(data[idx+1]), int(data[idx+2])
                grayscale = round(0.299 * r + 0.587 * g + 0.114 * b)
                bit = 1 if grayscale >= threshold else 0
                byte_index = y * byte_width + x // 8
                bit_index = 7 - (x % 8)
                out[byte_index] |= (bit << bit_index)
        return bytes(out)

    elif mode == "threeColor":
        # 三色: 两个平面（黑白 + 红色），各自每像素1bit打包
        byte_width = math.ceil(width / 8)
        bw_threshold = 140   # 对齐 JS 第 676 行
        red_threshold = 160  # 对齐 JS 第 677 行
        bw_data  = bytearray(byte_width * height)
        red_data = bytearray(byte_width * height)

        for y in range(height):
            for x in range(width):
                idx = (y * width + x) * 4
                r, g, b = int(data[idx]), int(data[idx+1]), int(data[idx+2])
                grayscale = round(0.299 * r + 0.587 * g + 0.114 * b)

                # 黑白层（对齐 JS 第 690-697 行）
                bw_bit = 1 if grayscale >= bw_threshold else 0
                byte_idx = y * byte_width + x // 8
                bit_idx  = 7 - (x % 8)
                if bw_bit:
                    bw_data[byte_idx] |= (1 << bit_idx)
                else:
                    bw_data[byte_idx] &= ~(1 << bit_idx)

                # 红色层（对齐 JS 第 699-706 行）
                # 红色像素: r > redThreshold 且 r > g 且 r > b → bit=0
                # 非红像素: bit=1
                red_bit = 0 if (r > red_threshold and r > g and r > b) else 1
                if red_bit:
                    red_data[byte_idx] |= (1 << bit_idx)
                else:
                    red_data[byte_idx] &= ~(1 << bit_idx)

        # 拼接（对齐 JS 第 710-712 行）
        return bytes(bw_data) + bytes(red_data)

    else:
        raise ValueError(f"不支持的颜色模式: {mode}")

# ===================== 示例使用 =====================
async def main():
    epd_client = EPDBleClient()
    try:
        # 1. 连接设备（替换为你的设备名称）
        await epd_client.connect(device_name="NRF_EPD_3D56")

        # 2. 清屏（可选）
        # await epd_client.clear_screen()

        # 3. 发送图片（严格对齐JS参数）
        await epd_client.send_image(
            image_path="E:\\Users\\Sakina\\Desktop\\epdtest.jpg",  # 替换为你的图片路径
            canvas_size_name="7.5_800_480",  # 替换为你的屏幕尺寸
            epd_driver="07",  # 替换为你的驱动值（08/09对应UC8159）
            dither_mode="threeColor",  # 颜色模式：fourColor/threeColor/blackWhiteColor
            interleaved_count=5  # 对应JS的interleavedcount
        )

    except Exception as e:
        print(f"执行失败: {str(e)}")
    finally:
        # 4. 断开连接
        await epd_client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())