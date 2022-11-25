"""
Support for Nespresso Connected mmachine.
https://www.nespresso.com

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/sensor.Nespresso/
"""
import logging
from abc import ABC
from typing import Any

from bleak import BLEDevice
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .nespresso import NespressoClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_devices: AddEntitiesCallback,
):
    """Set up the Nespresso sensor."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_devices(
        [
            NespressoSwitch(
                "nespresso_" + device.name, device, coordinator.api, coordinator
            )
            for device in coordinator.api.devices
        ]
    )


class NespressoSwitch(SwitchEntity, ABC):
    """General Representation of an Nespresso sensor."""

    def __init__(
        self, name: str, device: BLEDevice, client: NespressoClient, coordinator
    ):
        """Initialize a sensor."""
        self._attr_is_on = False
        self._name = name
        self._device = device
        self._client = client
        self._coordinator = coordinator
        _LOGGER.debug("Added sensor entity {}".format(self._name))

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def icon(self) -> str:
        return "mdi:coffee-maker"

    @property
    def unique_id(self):
        return self._name

    @property
    def is_on(self) -> bool:
        """Return True if entity is on."""
        return self._attr_is_on

    @property
    def state_attributes(self):
        """Return the state attributes.

        Implemented by component base class, should not be extended by integrations.
        Convention for attribute names is lowercase snake_case.
        """
        return self._device.attributes

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._attr_is_on = True
        await self._client.make_coffee(
            self._device, self._coordinator.get_select().current_option.lower()
        )
        self._attr_is_on = False

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        if self._attr_is_on:
            await self._client.cancel_coffee(self._device)
        self._attr_is_on = False
