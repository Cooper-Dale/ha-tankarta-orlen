"""Data update coordinator for Tankarta."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import TankartaApi
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .models import (
    BrowserlessAuthenticationError,
    BrowserlessConnectionError,
    TankartaAuthenticationError,
    TankartaData,
    TankartaDataError,
    TankartaEndpointError,
    TankartaPortalConnectionError,
    parse_prices,
)

_LOGGER = logging.getLogger(__name__)


class TankartaDataUpdateCoordinator(DataUpdateCoordinator[TankartaData]):
    """Coordinate one Browserless request for all Tankarta entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: TankartaApi,
    ) -> None:
        self.entry = entry
        self.api = api
        scan_interval = int(
            entry.options.get(
                CONF_SCAN_INTERVAL,
                entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            )
        )
        self.privacy_salt = entry.unique_id or entry.entry_id

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=scan_interval),
            always_update=False,
        )

    async def _async_update_data(self) -> TankartaData:
        try:
            payload = await self.api.async_fetch()
            data = parse_prices(
                payload,
                now=dt_util.utcnow(),
                privacy_salt=self.privacy_salt,
            )
            _LOGGER.debug(
                "Loaded %d Tankarta price sensors; skipped %d malformed items",
                len(data.readings),
                data.skipped_item_count,
            )
            return data
        except TankartaAuthenticationError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except BrowserlessAuthenticationError as err:
            raise UpdateFailed(
                "Browserless authentication failed; reconfigure the integration"
            ) from err
        except (
            BrowserlessConnectionError,
            TankartaPortalConnectionError,
            TankartaEndpointError,
            TankartaDataError,
        ) as err:
            raise UpdateFailed(str(err)) from err
