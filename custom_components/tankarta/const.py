"""Constants for the Tankarta integration."""

from __future__ import annotations

DOMAIN = "tankarta"

CONF_BROWSERLESS_URL = "browserless_url"
CONF_BROWSERLESS_TOKEN = "browserless_token"
CONF_STEALTH = "stealth"
CONF_HEADLESS = "headless"
CONF_BLOCK_ADS = "block_ads"
CONF_REQUEST_TIMEOUT = "request_timeout"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_CURRENCY = "currency"

DEFAULT_BROWSERLESS_URL = "http://db21ed7f-browserless-chrome:3000"
DEFAULT_STEALTH = True
DEFAULT_HEADLESS = False
DEFAULT_BLOCK_ADS = True
DEFAULT_REQUEST_TIMEOUT = 90
DEFAULT_SCAN_INTERVAL = 360
DEFAULT_CURRENCY = "CZK"

MIN_REQUEST_TIMEOUT = 30
MAX_REQUEST_TIMEOUT = 300
MIN_SCAN_INTERVAL = 15
MAX_SCAN_INTERVAL = 1440

BASE_URL = "https://business.tankarta.cz"
LOGIN_URL = f"{BASE_URL}/Login?ReturnUrl=%2F"
LIST_PRICE_PATH = "/Dashboard-ListPrice"
LIST_PRICE_URL = f"{BASE_URL}{LIST_PRICE_PATH}"
