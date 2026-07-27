"""Tankarta integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .api import TankartaApi, TankartaApiConfig
from .coordinator import TankartaDataUpdateCoordinator

PLATFORMS = (Platform.SENSOR, Platform.BUTTON)


@dataclass(slots=True)
class TankartaRuntimeData:
    """Runtime objects stored on the config entry."""

    api: TankartaApi
    coordinator: TankartaDataUpdateCoordinator


TankartaConfigEntry: TypeAlias = ConfigEntry[TankartaRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: TankartaConfigEntry) -> bool:
    """Set up Tankarta from a config entry."""
    api = TankartaApi(hass, TankartaApiConfig.from_mapping(entry.data))
    coordinator = TankartaDataUpdateCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = TankartaRuntimeData(api=api, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TankartaConfigEntry) -> bool:
    """Unload a Tankarta config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
