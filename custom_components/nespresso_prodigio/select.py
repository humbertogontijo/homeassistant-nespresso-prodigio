import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .nespresso import NespressoVolumeSelect

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_devices: AddEntitiesCallback,
):
    """Set up the Nespresso sensor."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    nespresso_select = NespressoSelect()

    def get_select():
        return nespresso_select

    coordinator.get_select = get_select
    async_add_devices([nespresso_select])

    selects = []

    for bundle in coordinator.api.bundles:
        bundle.volume_select = NespressoVolumeSelect()
        selects.append(bundle.volume_select)

    async_add_devices(selects)


class NespressoSelect(SelectEntity, NespressoVolumeSelect):

    def select_option(self, option: str) -> None:
        pass

    @property
    def unique_id(self) -> str:
        return "coffee_picker"
