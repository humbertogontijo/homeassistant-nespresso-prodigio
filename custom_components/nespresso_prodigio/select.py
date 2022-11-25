import logging

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

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


class NespressoSelect(SelectEntity):
    def __init__(self):
        self.entity_description = SelectEntityDescription()
        self.entity_description.options = ["Ristretto", "Espresso", "Lungo"]

    @property
    def unique_id(self) -> str:
        return "coffee_picker"

