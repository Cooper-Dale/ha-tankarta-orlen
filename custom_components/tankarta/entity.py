"""Shared entity helpers for Tankarta."""

from __future__ import annotations

from homeassistant.const import CONF_USERNAME
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TankartaConfigEntry
from .const import BASE_URL, DOMAIN
from .coordinator import TankartaDataUpdateCoordinator
from .models import account_fingerprint


class TankartaEntity(CoordinatorEntity[TankartaDataUpdateCoordinator]):
    """Base class for Tankarta entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: TankartaConfigEntry,
        coordinator: TankartaDataUpdateCoordinator,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        account_id = entry.unique_id or account_fingerprint(
            str(entry.data[CONF_USERNAME])
        )
        self._attr_unique_id = f"{account_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, account_id)},
            name="Tankarta",
            manufacturer="ORLEN",
            model="Business portal",
            configuration_url=BASE_URL,
        )
