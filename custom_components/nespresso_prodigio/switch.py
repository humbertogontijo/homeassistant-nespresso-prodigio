"""
Support for Nespresso Connected mmachine.
https://www.nespresso.com

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/sensor.Nespresso/
"""
import logging
from abc import ABC
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .nespresso import NespressoClient, NespressoDeviceBundle

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
                bundle, coordinator.api
            )
            for bundle in coordinator.api.bundles
        ]
    )


class NespressoSwitch(SwitchEntity, ABC):
    """General Representation of a Nespresso sensor."""

    def __init__(
            self, bundle: NespressoDeviceBundle, client: NespressoClient
    ):
        """Initialize a sensor."""
        self._attr_is_on = False
        self._name = "nespresso_" + bundle.device.name
        self._bundle = bundle
        self._client = client
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
        return format_mac(self._bundle.device.address)

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
        return self._bundle.attributes

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._attr_is_on = True
        await self._client.make_coffee(
            self._bundle.device, self._bundle.selected_volume.current_option.lower()
        )
        self._attr_is_on = False

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        if self._attr_is_on:
            await self._client.cancel_coffee(self._bundle.device)
        self._attr_is_on = False
