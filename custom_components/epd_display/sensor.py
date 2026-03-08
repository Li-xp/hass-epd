"""Sensor platform for EPD Display."""
import logging
from datetime import timedelta
from homeassistant.components.sensor import SensorEntity
from .const import DOMAIN, CONF_HOST, CONF_PORT

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=10)   # 默认10秒轮询，传输时约2秒刷新一次


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    client = data["client"]
    config = data["config"]
    async_add_entities([
        EpdConnectionSensor(client, config, entry.entry_id),
        EpdFirmwareSensor(client, config, entry.entry_id),
        EpdMtuSensor(client, config, entry.entry_id),
        EpdTransferSensor(client, config, entry.entry_id),
    ], True)


class EpdBaseSensor(SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, client, config, entry_id, suffix):
        self._client = client
        self._config = config
        host = config[CONF_HOST]
        port = config[CONF_PORT]
        self._attr_unique_id = f"epd_{host}_{port}_{suffix}"
        self._status = {}

    @property
    def device_info(self):
        host = self._config[CONF_HOST]
        port = self._config[CONF_PORT]
        return {
            "identifiers": {(DOMAIN, f"{host}:{port}")},
            "name": f"EPD Display ({host})",
            "manufacturer": "EPD BLE",
            "model": "E-Paper Display",
        }

    async def async_update(self):
        try:
            self._status = await self._client.async_get_status()
        except Exception:
            self._status = {}


class EpdConnectionSensor(EpdBaseSensor):
    _attr_name = "Connection"
    _attr_icon = "mdi:bluetooth-connect"

    def __init__(self, client, config, entry_id):
        super().__init__(client, config, entry_id, "connection")

    @property
    def native_value(self):
        return "Connected" if self._status.get("connected") else "Disconnected"

    @property
    def extra_state_attributes(self):
        return {"device": self._status.get("device"), "server": self._client.base_url}


class EpdFirmwareSensor(EpdBaseSensor):
    _attr_name = "Firmware"
    _attr_icon = "mdi:chip"

    def __init__(self, client, config, entry_id):
        super().__init__(client, config, entry_id, "firmware")

    @property
    def native_value(self):
        return self._status.get("firmware", "Unknown")


class EpdMtuSensor(EpdBaseSensor):
    _attr_name = "MTU"
    _attr_icon = "mdi:resize"
    _attr_native_unit_of_measurement = "bytes"

    def __init__(self, client, config, entry_id):
        super().__init__(client, config, entry_id, "mtu")

    @property
    def native_value(self):
        return self._status.get("mtu")


class EpdTransferSensor(EpdBaseSensor):
    """传输状态传感器：空闲 / 传输中 XX%"""
    _attr_name = "Transfer"
    _attr_icon = "mdi:transfer"

    def __init__(self, client, config, entry_id):
        super().__init__(client, config, entry_id, "transfer")
        self._transfer = {}

    async def async_update(self):
        try:
            self._status = await self._client.async_get_status()
            self._transfer = self._status.get("transfer", {})
        except Exception:
            self._status = {}
            self._transfer = {}

    @property
    def scan_interval(self):
        # 传输中时每2秒轮询，空闲时每10秒
        return timedelta(seconds=2) if self._transfer.get("busy") else timedelta(seconds=10)

    @property
    def native_value(self) -> str:
        if not self._transfer:
            return "Unknown"
        if self._transfer.get("busy"):
            pct = self._transfer.get("percent", 0)
            step = self._transfer.get("step", "")
            return f"传输中 {pct}%"
        err = self._transfer.get("last_error", "")
        return "错误" if err else "空闲"

    @property
    def extra_state_attributes(self) -> dict:
        t = self._transfer
        if not t:
            return {}
        return {
            "busy": t.get("busy", False),
            "step": t.get("step", ""),
            "chunk": t.get("chunk", 0),
            "total": t.get("total", 0),
            "percent": t.get("percent", 0),
            "elapsed_s": t.get("elapsed", 0),
            "message": t.get("message", ""),
            "last_error": t.get("last_error", ""),
        }
