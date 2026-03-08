"""Button platform for EPD Display."""
import logging
from homeassistant.components.button import ButtonEntity
from .const import DOMAIN, CONF_HOST, CONF_PORT, CONF_DEVICE_NAME

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    client = data["client"]
    config = data["config"]
    async_add_entities([
        EpdConnectButton(client, config, entry.entry_id),
        EpdDisconnectButton(client, config, entry.entry_id),
        EpdClearButton(client, config, entry.entry_id),
        EpdRefreshButton(client, config, entry.entry_id),
        EpdSleepButton(client, config, entry.entry_id),
        EpdSyncTimeClockButton(client, config, entry.entry_id),
        EpdSyncTimeCalendarButton(client, config, entry.entry_id),
        EpdSysResetButton(client, config, entry.entry_id),
    ])

class EpdBaseButton(ButtonEntity):
    _attr_has_entity_name = True
    def __init__(self, client, config, entry_id, suffix):
        self._client = client
        self._config = config
        host = config[CONF_HOST]
        port = config[CONF_PORT]
        self._attr_unique_id = f"epd_{host}_{port}_btn_{suffix}"
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

class EpdConnectButton(EpdBaseButton):
    _attr_name = "Connect"
    _attr_icon = "mdi:bluetooth-connect"
    def __init__(self, client, config, entry_id):
        super().__init__(client, config, entry_id, "connect")
    async def async_press(self):
        device_name = self._config.get(CONF_DEVICE_NAME)
        try:
            await self._client.async_connect(device_name)
        except Exception as err:
            _LOGGER.error("EPD connect failed: %s", err)

class EpdDisconnectButton(EpdBaseButton):
    _attr_name = "Disconnect"
    _attr_icon = "mdi:bluetooth-off"
    def __init__(self, client, config, entry_id):
        super().__init__(client, config, entry_id, "disconnect")
    async def async_press(self):
        try:
            await self._client.async_disconnect()
        except Exception as err:
            _LOGGER.error("EPD disconnect failed: %s", err)

class EpdClearButton(EpdBaseButton):
    _attr_name = "Clear Screen"
    _attr_icon = "mdi:eraser"
    def __init__(self, client, config, entry_id):
        super().__init__(client, config, entry_id, "clear")
    async def async_press(self):
        try:
            await self._client.async_clear()
        except Exception as err:
            _LOGGER.error("EPD clear failed: %s", err)

class EpdRefreshButton(EpdBaseButton):
    _attr_name = "Refresh"
    _attr_icon = "mdi:refresh"
    def __init__(self, client, config, entry_id):
        super().__init__(client, config, entry_id, "refresh")
    async def async_press(self):
        try:
            await self._client.async_refresh()
        except Exception as err:
            _LOGGER.error("EPD refresh failed: %s", err)

class EpdSleepButton(EpdBaseButton):
    _attr_name = "Sleep"
    _attr_icon = "mdi:sleep"
    def __init__(self, client, config, entry_id):
        super().__init__(client, config, entry_id, "sleep")
    async def async_press(self):
        try:
            await self._client.async_sleep()
        except Exception as err:
            _LOGGER.error("EPD sleep failed: %s", err)

class EpdSyncTimeClockButton(EpdBaseButton):
    """同步时间并启动局刷时钟模式（mode=2）"""
    _attr_name = "Sync Clock"
    _attr_icon = "mdi:clock-outline"
    def __init__(self, client, config, entry_id):
        super().__init__(client, config, entry_id, "sync_clock")
    async def async_press(self):
        try:
            await self._client.async_sync_time(mode=2)
        except Exception as err:
            _LOGGER.error("EPD sync clock failed: %s", err)

class EpdSyncTimeCalendarButton(EpdBaseButton):
    """同步时间并启动全刷日历模式（mode=1）"""
    _attr_name = "Sync Calendar"
    _attr_icon = "mdi:calendar-clock"
    def __init__(self, client, config, entry_id):
        super().__init__(client, config, entry_id, "sync_calendar")
    async def async_press(self):
        try:
            await self._client.async_sync_time(mode=1)
        except Exception as err:
            _LOGGER.error("EPD sync calendar failed: %s", err)

class EpdSysResetButton(EpdBaseButton):
    """系统重置"""
    _attr_name = "System Reset"
    _attr_icon = "mdi:restart"
    def __init__(self, client, config, entry_id):
        super().__init__(client, config, entry_id, "sys_reset")
    async def async_press(self):
        try:
            await self._client.async_sys_reset()
        except Exception as err:
            _LOGGER.error("EPD sys_reset failed: %s", err)

class EpdBaseButton(ButtonEntity):
    _attr_has_entity_name = True
    def __init__(self, client, config, entry_id, suffix):
        self._client = client
        self._config = config
        host = config[CONF_HOST]
        port = config[CONF_PORT]
        self._attr_unique_id = f"epd_{host}_{port}_btn_{suffix}"
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

class EpdConnectButton(EpdBaseButton):
    _attr_name = "Connect"
    _attr_icon = "mdi:bluetooth-connect"
    def __init__(self, client, config, entry_id):
        super().__init__(client, config, entry_id, "connect")
    async def async_press(self):
        device_name = self._config.get(CONF_DEVICE_NAME)
        try:
            await self._client.async_connect(device_name)
        except Exception as err:
            _LOGGER.error("EPD connect failed: %s", err)

class EpdDisconnectButton(EpdBaseButton):
    _attr_name = "Disconnect"
    _attr_icon = "mdi:bluetooth-off"
    def __init__(self, client, config, entry_id):
        super().__init__(client, config, entry_id, "disconnect")
    async def async_press(self):
        try:
            await self._client.async_disconnect()
        except Exception as err:
            _LOGGER.error("EPD disconnect failed: %s", err)

class EpdClearButton(EpdBaseButton):
    _attr_name = "Clear Screen"
    _attr_icon = "mdi:eraser"
    def __init__(self, client, config, entry_id):
        super().__init__(client, config, entry_id, "clear")
    async def async_press(self):
        try:
            await self._client.async_clear()
        except Exception as err:
            _LOGGER.error("EPD clear failed: %s", err)

class EpdRefreshButton(EpdBaseButton):
    _attr_name = "Refresh"
    _attr_icon = "mdi:refresh"
    def __init__(self, client, config, entry_id):
        super().__init__(client, config, entry_id, "refresh")
    async def async_press(self):
        try:
            await self._client.async_refresh()
        except Exception as err:
            _LOGGER.error("EPD refresh failed: %s", err)

class EpdSleepButton(EpdBaseButton):
    _attr_name = "Sleep"
    _attr_icon = "mdi:sleep"
    def __init__(self, client, config, entry_id):
        super().__init__(client, config, entry_id, "sleep")
    async def async_press(self):
        try:
            await self._client.async_sleep()
        except Exception as err:
            _LOGGER.error("EPD sleep failed: %s", err)
