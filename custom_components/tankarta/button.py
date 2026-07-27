"""Button platform for Tankarta."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TankartaConfigEntry
from .entity import TankartaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TankartaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Tankarta refresh button."""
    async_add_entities([TankartaRefreshButton(entry)])


class TankartaRefreshButton(TankartaEntity, ButtonEntity):
    """Request an immediate coordinator refresh."""

    _attr_translation_key = "refresh"
    _attr_icon = "mdi:refresh"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: TankartaConfigEntry) -> None:
        super().__init__(entry, entry.runtime_data.coordinator, "refresh")

    async def async_press(self) -> None:
        """Refresh list prices now."""
        await self.coordinator.async_request_refresh()
