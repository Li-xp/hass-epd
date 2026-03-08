"""Config flow for EPD Display integration."""

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EpdApiClient
from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_PORT,
    CONF_DEVICE_NAME,
    CONF_CANVAS,
    CONF_DRIVER,
    CONF_DITHER_MODE,
    CONF_CONTRAST,
    CONF_DITHER_STRENGTH,
    DEFAULT_PORT,
    DEFAULT_DEVICE_NAME,
    DEFAULT_CANVAS,
    DEFAULT_DRIVER,
    DEFAULT_DITHER_MODE,
    DEFAULT_CONTRAST,
    DEFAULT_DITHER_STRENGTH,
    CANVAS_OPTIONS,
    DITHER_MODES,
)

_LOGGER = logging.getLogger(__name__)


class EpdDisplayConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EPD Display."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]

            # Test connection
            session = async_get_clientsession(self.hass)
            client = EpdApiClient(host, port, session)
            if await client.async_test_connection():
                # Check if already configured
                await self.async_set_unique_id(f"epd_{host}_{port}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"EPD ({host}:{port})",
                    data=user_input,
                )
            else:
                errors["base"] = "cannot_connect"

        data_schema = vol.Schema({
            vol.Required(CONF_HOST, default="192.168.1.100"): str,
            vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
            vol.Required(CONF_DEVICE_NAME, default=DEFAULT_DEVICE_NAME): str,
            vol.Required(CONF_CANVAS, default=DEFAULT_CANVAS): vol.In(CANVAS_OPTIONS),
            vol.Required(CONF_DRIVER, default=DEFAULT_DRIVER): str,
            vol.Required(CONF_DITHER_MODE, default=DEFAULT_DITHER_MODE): vol.In(DITHER_MODES),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow handler."""
        return EpdDisplayOptionsFlow(config_entry)


class EpdDisplayOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for EPD Display."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._config_entry.data

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_CANVAS, default=current.get(CONF_CANVAS, DEFAULT_CANVAS)): vol.In(CANVAS_OPTIONS),
                vol.Required(CONF_DRIVER, default=current.get(CONF_DRIVER, DEFAULT_DRIVER)): str,
                vol.Required(CONF_DITHER_MODE, default=current.get(CONF_DITHER_MODE, DEFAULT_DITHER_MODE)): vol.In(DITHER_MODES),
                vol.Optional(CONF_CONTRAST, default=current.get(CONF_CONTRAST, DEFAULT_CONTRAST)): vol.Coerce(float),
                vol.Optional(CONF_DITHER_STRENGTH, default=current.get(CONF_DITHER_STRENGTH, DEFAULT_DITHER_STRENGTH)): vol.Coerce(float),
            }),
        )
