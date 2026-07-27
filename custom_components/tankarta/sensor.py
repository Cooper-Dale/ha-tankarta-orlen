"""Sensor platform for Tankarta."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TankartaConfigEntry
from .const import (
    CONF_CURRENCY,
    CONF_DISCOUNT_AMOUNT,
    CONF_DISCOUNT_PERCENTAGE,
    DEFAULT_CURRENCY,
)
from .entity import TankartaEntity
from .models import PriceCalculation, calculate_price


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TankartaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Tankarta sensors, including dynamically discovered products."""
    coordinator = entry.runtime_data.coordinator
    known_products: set[str] = set()

    def new_price_entities() -> list[TankartaPriceSensor]:
        new_keys = sorted(set(coordinator.data.readings) - known_products)
        known_products.update(new_keys)
        return [TankartaPriceSensor(entry, key) for key in new_keys]

    entities: list[SensorEntity] = [TankartaLastUpdateSensor(entry)]
    entities.extend(new_price_entities())
    async_add_entities(entities)

    @callback
    def discover_new_products() -> None:
        new_entities = new_price_entities()
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(discover_new_products))


class TankartaPriceSensor(TankartaEntity, SensorEntity):
    """Current Tankarta list price for one dynamically discovered product."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, entry: TankartaConfigEntry, reading_key: str) -> None:
        super().__init__(entry, entry.runtime_data.coordinator, f"price_{reading_key}")
        self._reading_key = reading_key
        self._entry = entry
        reading = self.coordinator.data.readings[reading_key]
        self._attr_name = reading.display_name
        self._attr_icon = self._icon_for_product(reading.product)
        self._attr_native_unit_of_measurement = str(
            entry.data.get(CONF_CURRENCY, DEFAULT_CURRENCY)
        )

    @staticmethod
    def _icon_for_product(product: str) -> str:
        normalized = product.casefold()
        if normalized == "h2" or "vodík" in normalized or "hydrogen" in normalized:
            return "mdi:molecule"
        if "adblue" in normalized:
            return "mdi:water-outline"
        return "mdi:gas-station"

    @property
    def available(self) -> bool:
        return super().available and self._reading_key in self.coordinator.data.readings

    @property
    def name(self) -> str:
        reading = self.coordinator.data.readings.get(self._reading_key)
        return reading.display_name if reading is not None else str(self._attr_name)

    def _price_calculation(self) -> PriceCalculation | None:
        reading = self.coordinator.data.readings.get(self._reading_key)
        if reading is None:
            return None
        return calculate_price(
            reading.price,
            discount_amount=self._entry.options.get(CONF_DISCOUNT_AMOUNT),
            discount_percentage=self._entry.options.get(
                CONF_DISCOUNT_PERCENTAGE
            ),
        )

    @property
    def native_value(self) -> Decimal | None:
        calculation = self._price_calculation()
        return calculation.effective_price if calculation is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose source price, discount and Tankarta metadata."""
        reading = self.coordinator.data.readings.get(self._reading_key)
        calculation = self._price_calculation()
        if reading is None or calculation is None:
            return {}

        attributes: dict[str, Any] = {
            "product": reading.product,
            "division_id": reading.division_id,
            "announced_price": float(calculation.announced_price),
            "price_type": calculation.price_type,
            "discount_type": calculation.discount_type,
            "discount_amount": float(calculation.discount_amount),
        }
        if calculation.discount_type == "percentage":
            attributes["discount_percentage"] = float(
                calculation.discount_value or Decimal("0")
            )
        return attributes


class TankartaLastUpdateSensor(TankartaEntity, SensorEntity):
    """Timestamp of the last successful Tankarta refresh."""

    _attr_translation_key = "last_update"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, entry: TankartaConfigEntry) -> None:
        super().__init__(entry, entry.runtime_data.coordinator, "last_update")

    @property
    def native_value(self):
        return self.coordinator.data.updated_at
