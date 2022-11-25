import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .nespresso import NespressoVolume, NespressoDeviceBundle

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
            NespressoSelect(
                bundle
            )
            for bundle in coordinator.api.bundles
        ]
    )


class NespressoSelect(SelectEntity):

    def __init__(self, bundle: NespressoDeviceBundle):
        self._bundle = bundle
        self._attr_options = [str(e.value) for e in NespressoVolume]
        self._attr_current_option = str(NespressoVolume.LUNGO)
        self.select_option(self._attr_current_option)

    def select_option(self, option: str) -> None:
        self._bundle.selected_volume = option

    @property
    def unique_id(self) -> str:
        return "coffee_picker"
