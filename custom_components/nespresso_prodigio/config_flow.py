"""Config flow for yeelight_bt"""
from __future__ import annotations

import logging

import voluptuous as vol
from bleak import BleakError
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.components.bluetooth import (
    async_get_scanner,
)

from .const import CONF_ENTRY_AUTH_KEY, DOMAIN, PLATFORMS
from .nespresso import NespressoClient

_LOGGER = logging.getLogger(__name__)


class NespressoFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Blueprint."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize."""
        self._errors = {}

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        self._errors = {}

        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            valid = await self._test_connection(
                user_input[CONF_ENTRY_AUTH_KEY]
            )
            if valid:
                return self.async_create_entry(
                    title=user_input[CONF_ENTRY_AUTH_KEY], data=user_input
                )
            else:
                self._errors["base"] = "auth"

            return await self._show_config_form(user_input)

        user_input = {}
        # Provide defaults for form
        user_input[CONF_ENTRY_AUTH_KEY] = ""

        return await self._show_config_form(user_input)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return NespressoOptionsFlowHandler(config_entry)

    async def _show_config_form(self, user_input):  # pylint: disable=unused-argument
        """Show the configuration form to edit location data."""
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ENTRY_AUTH_KEY, default=user_input[CONF_ENTRY_AUTH_KEY]): str,
                }
            ),
            errors=self._errors,
        )

    async def _test_connection(self, auth_code):
        """Return true if credentials is valid."""
        try:
            scanner = async_get_scanner(self.hass)
            _LOGGER.debug("Preparing for a scan")
            if len(scanner.discovered_devices) == 0:
                message = "No bluetooth scanner detected. \
                            Enable the bluetooth integration or ensure an esphome device \
                            is running as a bluetooth proxy"
                _LOGGER.error(message)
                self._errors["base"] = message
                return False
            try:
                _LOGGER.debug("Starting a scan for Nespresso BT devices")
                client = NespressoClient(scanner, auth_code)
                await client.get_device_data()
            except BleakError as err:
                _LOGGER.error(f"Bluetooth connection error while trying to scan: {err}")
                self._errors["base"] = "BleakError"
                return False
            return True
        except Exception as e:  # pylint: disable=broad-except
            self._errors["base"] = str(e)
            return False


class NespressoOptionsFlowHandler(config_entries.OptionsFlow):
    """Blueprint config flow options handler."""

    def __init__(self, config_entry):
        """Initialize HACS options flow."""
        self.config_entry = config_entry
        self.options = dict(config_entry.options)

    async def async_step_init(self, user_input=None):  # pylint: disable=unused-argument
        """Manage the options."""
        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        if user_input is not None:
            self.options.update(user_input)
            return await self._update_options()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(x, default=self.options.get(x, True)): bool
                    for x in sorted(PLATFORMS)
                }
            ),
        )

    async def _update_options(self):
        """Update config entry options."""
        return self.async_create_entry(
            title=self.config_entry.data.get(CONF_ENTRY_AUTH_KEY), data=self.options
        )
