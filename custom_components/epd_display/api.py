"""API client for EPD server communication."""

import asyncio
import logging
from typing import Any, Optional

import aiohttp

_LOGGER = logging.getLogger(__name__)


class EpdApiClient:
    """Client to interact with the EPD BLE control server."""

    def __init__(self, host: str, port: int, session: aiohttp.ClientSession) -> None:
        self._host = host
        self._port = port
        self._session = session
        self._base_url = f"http://{host}:{port}"

    @property
    def base_url(self) -> str:
        return self._base_url

    async def _request(self, method: str, path: str, data=None, timeout: int = 30) -> dict:
        url = f"{self._base_url}{path}"
        try:
            async with self._session.request(
                method, url, data=data,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status == 409:
                    # 设备忙（正在传输），抛出可识别的异常
                    body = await resp.json()
                    detail = body.get("detail", "设备正在传输中，请等待完成")
                    raise EpdBusyError(detail)
                resp.raise_for_status()
                return await resp.json()
        except EpdBusyError:
            raise
        except aiohttp.ClientError as err:
            _LOGGER.error("EPD API error: %s %s -> %s", method, path, err)
            raise
        except asyncio.TimeoutError:
            _LOGGER.error("EPD API timeout: %s %s", method, path)
            raise

    async def async_get_status(self) -> dict:
        return await self._request("GET", "/status", timeout=10)

    async def async_connect(self, device_name: Optional[str] = None) -> dict:
        data = {}
        if device_name:
            data["device_name"] = device_name
        return await self._request("POST", "/connect", data=data, timeout=60)

    async def async_disconnect(self) -> dict:
        return await self._request("POST", "/disconnect", timeout=10)

    async def async_clear(self) -> dict:
        return await self._request("POST", "/clear", timeout=30)

    async def async_refresh(self) -> dict:
        return await self._request("POST", "/refresh", timeout=30)

    async def async_sleep(self) -> dict:
        return await self._request("POST", "/sleep", timeout=10)

    async def async_sync_time(self, mode: int = 1) -> dict:
        return await self._request("POST", "/sync_time", data={"mode": str(mode)}, timeout=30)

    async def async_sys_reset(self) -> dict:
        return await self._request("POST", "/sys_reset", timeout=15)

    async def async_display_image(
        self, image_path: str,
        canvas: Optional[str] = None, driver: Optional[str] = None,
        dither_mode: Optional[str] = None,
        contrast: float = 1.0, dither_strength: float = 1.0,
    ) -> dict:
        url = f"{self._base_url}/display"
        form = aiohttp.FormData()
        form.add_field("image", open(image_path, "rb"), filename=image_path.split("/")[-1])
        if canvas:     form.add_field("canvas", canvas)
        if driver:     form.add_field("driver", driver)
        if dither_mode: form.add_field("dither_mode", dither_mode)
        form.add_field("contrast", str(contrast))
        form.add_field("dither_strength", str(dither_strength))
        try:
            async with self._session.post(
                url, data=form, timeout=aiohttp.ClientTimeout(total=300),
            ) as resp:
                if resp.status == 409:
                    body = await resp.json()
                    raise EpdBusyError(body.get("detail", "设备正在传输中"))
                resp.raise_for_status()
                return await resp.json()
        except EpdBusyError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.error("EPD display_image failed: %s", err)
            raise

    async def async_display_image_bytes(
        self, image_bytes: bytes, filename: str,
        canvas: Optional[str] = None, driver: Optional[str] = None,
        dither_mode: Optional[str] = None,
        contrast: float = 1.0, dither_strength: float = 1.0,
    ) -> dict:
        url = f"{self._base_url}/display"
        form = aiohttp.FormData()
        form.add_field("image", image_bytes, filename=filename, content_type="application/octet-stream")
        if canvas:     form.add_field("canvas", canvas)
        if driver:     form.add_field("driver", driver)
        if dither_mode: form.add_field("dither_mode", dither_mode)
        form.add_field("contrast", str(contrast))
        form.add_field("dither_strength", str(dither_strength))
        try:
            async with self._session.post(
                url, data=form, timeout=aiohttp.ClientTimeout(total=300),
            ) as resp:
                if resp.status == 409:
                    body = await resp.json()
                    raise EpdBusyError(body.get("detail", "设备正在传输中"))
                resp.raise_for_status()
                return await resp.json()
        except EpdBusyError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.error("EPD display_image_bytes failed: %s", err)
            raise

    async def async_display_url(
        self, image_url: str,
        canvas: Optional[str] = None, driver: Optional[str] = None,
        dither_mode: Optional[str] = None,
        contrast: float = 1.0, dither_strength: float = 1.0,
    ) -> dict:
        data = {"image_url": image_url}
        if canvas:     data["canvas"] = canvas
        if driver:     data["driver"] = driver
        if dither_mode: data["dither_mode"] = dither_mode
        data["contrast"] = str(contrast)
        data["dither_strength"] = str(dither_strength)
        return await self._request("POST", "/display_url", data=data, timeout=300)

    async def async_test_connection(self) -> bool:
        try:
            await self._request("GET", "/status", timeout=5)
            return True
        except Exception:
            return False


class EpdBusyError(Exception):
    """设备正在传输，不接受新指令"""
