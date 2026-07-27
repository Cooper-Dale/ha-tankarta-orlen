"""Config flow for Tankarta."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import logging
import re
from typing import Any, Mapping

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, OptionsFlowWithReload
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util import dt as dt_util

from .api import TankartaApi, TankartaApiConfig
from .const import (
    CONF_BLOCK_ADS,
    CONF_BROWSERLESS_TOKEN,
    CONF_BROWSERLESS_URL,
    CONF_CURRENCY,
    CONF_DISCOUNT_AMOUNT,
    CONF_DISCOUNT_PERCENTAGE,
    CONF_HEADLESS,
    CONF_REQUEST_TIMEOUT,
    CONF_SCAN_INTERVAL,
    CONF_STEALTH,
    DEFAULT_BLOCK_ADS,
    DEFAULT_BROWSERLESS_URL,
    DEFAULT_CURRENCY,
    DEFAULT_HEADLESS,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STEALTH,
    DOMAIN,
    MAX_DISCOUNT_AMOUNT,
    MAX_DISCOUNT_PERCENTAGE,
    MAX_REQUEST_TIMEOUT,
    MAX_SCAN_INTERVAL,
    MIN_REQUEST_TIMEOUT,
    MIN_SCAN_INTERVAL,
)
from .models import (
    BrowserlessAuthenticationError,
    BrowserlessConnectionError,
    TankartaAuthenticationError,
    TankartaChallengeError,
    TankartaDataError,
    TankartaEndpointError,
    TankartaLoginFormError,
    TankartaPortalConnectionError,
    TankartaTwoFactorError,
    account_fingerprint,
    parse_prices,
)

_LOGGER = logging.getLogger(__name__)
_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


class InvalidCurrencyError(ValueError):
    """The configured currency is not an ISO 4217-like code."""


def normalize_currency(data: dict[str, Any]) -> None:
    """Normalize and validate the currency code used by monetary sensors."""
    currency = str(data.get(CONF_CURRENCY) or DEFAULT_CURRENCY).strip().upper()
    if not _CURRENCY_PATTERN.fullmatch(currency):
        raise InvalidCurrencyError(currency)
    data[CONF_CURRENCY] = currency


def connection_schema(
    defaults: Mapping[str, Any] | None = None,
    *,
    password_optional: bool = False,
):
    """Build the connection schema with current values as defaults."""
    data = dict(defaults or {})
    password_key = (
        vol.Optional(CONF_PASSWORD, default="")
        if password_optional
        else vol.Required(CONF_PASSWORD)
    )
    return vol.Schema(
        {
            vol.Required(
                CONF_USERNAME,
                default=data.get(CONF_USERNAME, ""),
            ): TextSelector(),
            password_key: TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Required(
                CONF_BROWSERLESS_URL,
                default=data.get(CONF_BROWSERLESS_URL, DEFAULT_BROWSERLESS_URL),
            ): TextSelector(),
            vol.Optional(
                CONF_BROWSERLESS_TOKEN,
                default=data.get(CONF_BROWSERLESS_TOKEN, ""),
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
            vol.Required(
                CONF_CURRENCY,
                default=data.get(CONF_CURRENCY, DEFAULT_CURRENCY),
            ): TextSelector(),
            vol.Required(
                CONF_HEADLESS,
                default=data.get(CONF_HEADLESS, DEFAULT_HEADLESS),
            ): BooleanSelector(),
            vol.Required(
                CONF_STEALTH,
                default=data.get(CONF_STEALTH, DEFAULT_STEALTH),
            ): BooleanSelector(),
            vol.Required(
                CONF_BLOCK_ADS,
                default=data.get(CONF_BLOCK_ADS, DEFAULT_BLOCK_ADS),
            ): BooleanSelector(),
            vol.Required(
                CONF_REQUEST_TIMEOUT,
                default=data.get(CONF_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_REQUEST_TIMEOUT,
                    max=MAX_REQUEST_TIMEOUT,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="s",
                )
            ),
        }
    )


def options_schema(*, currency: str = DEFAULT_CURRENCY):
    """Build polling and optional discount settings."""
    return vol.Schema(
        {
            vol.Required(CONF_SCAN_INTERVAL): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_SCAN_INTERVAL,
                    max=MAX_SCAN_INTERVAL,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="min",
                )
            ),
            vol.Optional(CONF_DISCOUNT_AMOUNT): NumberSelector(
                NumberSelectorConfig(
                    min=0,
                    max=MAX_DISCOUNT_AMOUNT,
                    step=0.01,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement=currency,
                )
            ),
            vol.Optional(CONF_DISCOUNT_PERCENTAGE): NumberSelector(
                NumberSelectorConfig(
                    min=0,
                    max=MAX_DISCOUNT_PERCENTAGE,
                    step=0.01,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="%",
                )
            ),
        }
    )


def normalize_discount_options(data: dict[str, Any]) -> None:
    """Validate mutually exclusive discount options and normalize storage."""
    normalized: dict[str, Decimal | None] = {}
    for key in (CONF_DISCOUNT_AMOUNT, CONF_DISCOUNT_PERCENTAGE):
        value = data.get(key)
        if value in (None, "", 0, 0.0, "0"):
            data.pop(key, None)
            normalized[key] = None
            continue
        try:
            decimal_value = Decimal(str(value))
        except (InvalidOperation, ValueError) as err:
            raise ValueError(key) from err
        if not decimal_value.is_finite() or decimal_value < 0:
            raise ValueError(key)
        if decimal_value == 0:
            data.pop(key, None)
            normalized[key] = None
            continue
        data[key] = float(decimal_value)
        normalized[key] = decimal_value

    if normalized.get(CONF_DISCOUNT_AMOUNT) is not None and normalized.get(
        CONF_DISCOUNT_PERCENTAGE
    ) is not None:
        raise ValueError("discount_both_set")
    percentage = normalized.get(CONF_DISCOUNT_PERCENTAGE)
    if percentage is not None and percentage > MAX_DISCOUNT_PERCENTAGE:
        raise ValueError(CONF_DISCOUNT_PERCENTAGE)
    amount = normalized.get(CONF_DISCOUNT_AMOUNT)
    if amount is not None and amount > MAX_DISCOUNT_AMOUNT:
        raise ValueError(CONF_DISCOUNT_AMOUNT)


async def validate_input(hass: HomeAssistant, data: Mapping[str, Any]) -> None:
    """Validate Browserless connectivity, credentials and list-price data."""
    mutable_data = dict(data)
    normalize_currency(mutable_data)
    fingerprint = account_fingerprint(str(mutable_data[CONF_USERNAME]))
    api = TankartaApi(hass, TankartaApiConfig.from_mapping(mutable_data))
    payload = await api.async_fetch()
    parse_prices(payload, now=dt_util.utcnow(), privacy_salt=fingerprint)


class TankartaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the Tankarta config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Create a Tankarta config entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                normalize_currency(user_input)
            except InvalidCurrencyError:
                errors["base"] = "invalid_currency"
            else:
                error = await self._async_validate(user_input)
                if error is None:
                    fingerprint = account_fingerprint(str(user_input[CONF_USERNAME]))
                    await self.async_set_unique_id(fingerprint)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(title="Tankarta", data=user_input)
                errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=connection_schema(user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Change required connection settings."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            merged = dict(entry.data)
            merged.update(user_input)
            if not user_input.get(CONF_PASSWORD):
                merged[CONF_PASSWORD] = entry.data[CONF_PASSWORD]
            try:
                normalize_currency(merged)
            except InvalidCurrencyError:
                errors["base"] = "invalid_currency"
            else:
                error = await self._async_validate(merged)
                if error is None:
                    fingerprint = account_fingerprint(str(merged[CONF_USERNAME]))
                    await self.async_set_unique_id(fingerprint)
                    self._abort_if_unique_id_mismatch()
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates=merged,
                    )
                errors["base"] = error

        defaults = dict(entry.data)
        defaults.update(user_input or {})
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=connection_schema(defaults, password_optional=True),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]):
        """Start reauthentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Update rejected credentials."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            merged = dict(entry.data)
            merged.update(user_input)
            error = await self._async_validate(merged)
            if error is None:
                fingerprint = account_fingerprint(str(merged[CONF_USERNAME]))
                await self.async_set_unique_id(fingerprint)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates=merged,
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=entry.data.get(CONF_USERNAME, ""),
                    ): TextSelector(),
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    async def _async_validate(self, data: Mapping[str, Any]) -> str | None:
        try:
            await validate_input(self.hass, data)
        except InvalidCurrencyError:
            return "invalid_currency"
        except TankartaTwoFactorError:
            return "two_factor_required"
        except TankartaChallengeError:
            return "challenge_required"
        except TankartaAuthenticationError:
            return "invalid_auth"
        except BrowserlessAuthenticationError:
            return "invalid_browserless_auth"
        except BrowserlessConnectionError:
            return "cannot_connect_browserless"
        except TankartaPortalConnectionError:
            return "cannot_connect_portal"
        except TankartaEndpointError:
            return "endpoint_not_found"
        except TankartaLoginFormError:
            return "login_form_changed"
        except TankartaDataError:
            return "invalid_data"
        except Exception:
            _LOGGER.exception("Unexpected exception validating Tankarta configuration")
            return "unknown"
        return None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the Tankarta options flow."""
        return TankartaOptionsFlow()


class TankartaOptionsFlow(OptionsFlowWithReload):
    """Manage polling and price discount settings."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Configure optional polling and discount behavior."""
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_SCAN_INTERVAL] = int(user_input[CONF_SCAN_INTERVAL])
            try:
                normalize_discount_options(user_input)
            except ValueError as err:
                reason = str(err)
                if reason == "discount_both_set":
                    errors["base"] = "discount_both_set"
                elif reason == CONF_DISCOUNT_PERCENTAGE:
                    errors["base"] = "invalid_discount_percentage"
                else:
                    errors["base"] = "invalid_discount_amount"
            else:
                return self.async_create_entry(data=user_input)

        defaults = dict(self.config_entry.options)
        defaults.update(user_input or {})
        defaults.setdefault(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        currency = str(
            self.config_entry.data.get(CONF_CURRENCY, DEFAULT_CURRENCY)
        ).upper()
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                options_schema(currency=currency), defaults
            ),
            errors=errors,
        )
