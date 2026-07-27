"""Browserless client for the Tankarta business portal."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from aiohttp import ClientError, ClientSession, ClientTimeout

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_BLOCK_ADS,
    CONF_BROWSERLESS_TOKEN,
    CONF_BROWSERLESS_URL,
    CONF_HEADLESS,
    CONF_REQUEST_TIMEOUT,
    CONF_STEALTH,
    DEFAULT_BLOCK_ADS,
    DEFAULT_HEADLESS,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_STEALTH,
)
from .models import (
    BrowserlessAuthenticationError,
    TankartaAuthenticationError,
    TankartaConnectionError,
    TankartaDataError,
)


@dataclass(frozen=True, slots=True)
class TankartaApiConfig:
    """Connection settings required by the Browserless function."""

    username: str
    password: str
    browserless_url: str
    browserless_token: str
    stealth: bool
    headless: bool
    block_ads: bool
    request_timeout: int

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "TankartaApiConfig":
        """Build API configuration from a config-entry-like mapping."""
        return cls(
            username=str(data[CONF_USERNAME]),
            password=str(data[CONF_PASSWORD]),
            browserless_url=str(data[CONF_BROWSERLESS_URL]),
            browserless_token=str(data.get(CONF_BROWSERLESS_TOKEN) or ""),
            stealth=bool(data.get(CONF_STEALTH, DEFAULT_STEALTH)),
            headless=bool(data.get(CONF_HEADLESS, DEFAULT_HEADLESS)),
            block_ads=bool(data.get(CONF_BLOCK_ADS, DEFAULT_BLOCK_ADS)),
            request_timeout=int(data.get(CONF_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT)),
        )


def normalize_browserless_function_url(config: TankartaApiConfig) -> str:
    """Convert a Browserless base or WebSocket URL to the function endpoint."""
    raw = config.browserless_url.strip()
    if not raw:
        raise TankartaConnectionError("Browserless URL is empty")

    parsed = urlsplit(raw)
    scheme = {"ws": "http", "wss": "https"}.get(parsed.scheme, parsed.scheme)
    if scheme not in {"http", "https"} or not parsed.netloc:
        raise TankartaConnectionError(
            "Browserless URL must use http, https, ws or wss"
        )

    path = parsed.path.rstrip("/")
    if path.endswith("/chromium/function") or path.endswith("/function"):
        function_path = path
    elif path.endswith("/chromium"):
        function_path = f"{path}/function"
    elif not path:
        function_path = "/chromium/function"
    else:
        function_path = f"{path}/chromium/function"

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if config.browserless_token:
        query["token"] = config.browserless_token
    query.setdefault(
        "launch",
        json.dumps(
            {"headless": config.headless, "stealth": config.stealth},
            separators=(",", ":"),
        ),
    )
    query.setdefault("blockAds", "true" if config.block_ads else "false")
    query.setdefault("timeout", str((config.request_timeout + 15) * 1000))

    return urlunsplit((scheme, parsed.netloc, function_path, urlencode(query), ""))


class TankartaApi:
    """Run Tankarta browser automation through Browserless."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: TankartaApiConfig,
        session: ClientSession | None = None,
    ) -> None:
        self._hass = hass
        self._config = config
        self._session = session or async_get_clientsession(hass)
        self._script: str | None = None
        self._browser_session: dict[str, Any] | None = None

    async def _async_script(self) -> str:
        if self._script is None:
            script_path = Path(__file__).with_name("browserless_function.js")
            self._script = await self._hass.async_add_executor_job(
                lambda: script_path.read_text(encoding="utf-8")
            )
        return self._script

    async def async_fetch(self) -> list[Mapping[str, Any]]:
        """Fetch the current Tankarta list-price array."""
        url = normalize_browserless_function_url(self._config)
        body = {
            "code": await self._async_script(),
            "context": {
                "username": self._config.username,
                "password": self._config.password,
                "timeoutMs": self._config.request_timeout * 1000,
                "session": self._browser_session,
            },
        }
        timeout = ClientTimeout(total=self._config.request_timeout + 20)

        try:
            async with self._session.post(url, json=body, timeout=timeout) as response:
                text = await response.text()
                if response.status in {401, 403}:
                    raise BrowserlessAuthenticationError(
                        f"Browserless rejected the request with HTTP {response.status}"
                    )
                if response.status < 200 or response.status >= 300:
                    raise TankartaConnectionError(
                        f"Browserless returned HTTP {response.status}"
                    )
                try:
                    decoded = json.loads(text)
                except json.JSONDecodeError as err:
                    raise TankartaDataError(
                        "Browserless response was not valid JSON"
                    ) from err
        except (
            BrowserlessAuthenticationError,
            TankartaConnectionError,
            TankartaDataError,
        ):
            raise
        except (ClientError, TimeoutError) as err:
            raise TankartaConnectionError(
                f"Browserless request failed: {type(err).__name__}"
            ) from err

        result: Any = decoded
        if isinstance(decoded, dict) and "data" in decoded:
            result = decoded["data"]
        if not isinstance(result, dict):
            raise TankartaDataError("Browserless returned an unexpected JSON value")

        if not result.get("success"):
            code = str(result.get("code") or "unknown")
            message = str(result.get("error") or "Browserless function failed")
            if code in {"authentication_failed", "two_factor_required"}:
                raise TankartaAuthenticationError(message)
            if code in {"login_form_changed", "invalid_payload"}:
                raise TankartaDataError(message)
            raise TankartaConnectionError(f"{code}: {message}")

        prices = result.get("prices")
        if (
            isinstance(prices, (str, bytes, bytearray))
            or not isinstance(prices, Sequence)
        ):
            raise TankartaDataError("Browserless result is missing the prices array")

        browser_session = result.get("session")
        if isinstance(browser_session, dict):
            self._browser_session = browser_session

        return [item for item in prices if isinstance(item, Mapping)]
