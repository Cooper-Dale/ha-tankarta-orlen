"""Pure data models and Tankarta list-price parsing."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any


class TankartaError(Exception):
    """Base Tankarta error with optional safe diagnostic metadata."""

    def __init__(
        self,
        message: str,
        *,
        diagnostics: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.diagnostics = dict(diagnostics or {})


class BrowserlessAuthenticationError(TankartaError):
    """Browserless credentials were rejected."""


class BrowserlessConnectionError(TankartaError):
    """Browserless could not be reached or returned an invalid envelope."""


class TankartaPortalConnectionError(TankartaError):
    """The Tankarta portal itself could not be reached."""


class TankartaAuthenticationError(TankartaError):
    """The Tankarta session could not be authenticated."""


class TankartaTwoFactorError(TankartaAuthenticationError):
    """The Tankarta account requires an OTP step."""


class TankartaChallengeError(TankartaAuthenticationError):
    """The Tankarta login page requires an interactive challenge."""


class TankartaEndpointError(TankartaError):
    """The authenticated list-price endpoint was unavailable."""


class TankartaDataError(TankartaError):
    """Tankarta returned unexpected or incomplete data."""


class TankartaLoginFormError(TankartaDataError):
    """The Tankarta login form no longer matches supported selectors."""


@dataclass(frozen=True, slots=True)
class PriceReading:
    """One list-price sensor discovered in the Tankarta response."""

    key: str
    product: str
    display_name: str
    price: Decimal
    division_id: Any


@dataclass(frozen=True, slots=True)
class TankartaData:
    """A coordinated Tankarta update."""

    updated_at: datetime
    readings: Mapping[str, PriceReading]
    source_item_count: int
    skipped_item_count: int


def account_fingerprint(username: str) -> str:
    """Create a stable non-reversible account identifier for HA registry keys."""
    normalized = username.strip().casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _price(value: Any) -> Decimal | None:
    """Return a finite decimal price, excluding booleans and invalid values."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _division_material(value: Any) -> str:
    """Serialize a division identifier only long enough to derive an opaque key."""
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        return repr(value)


def _reading_key(*, privacy_salt: str, division_id: Any, product: str) -> str:
    """Hash the division and product without placing divisionID in registry keys."""
    material = "\0".join(
        (privacy_salt, _division_material(division_id), product.strip().casefold())
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def parse_prices(
    payload: Sequence[Any],
    *,
    now: datetime,
    privacy_salt: str,
) -> TankartaData:
    """Parse list prices and produce stable dynamic entity keys."""
    if isinstance(payload, (str, bytes, bytearray)) or not isinstance(payload, Sequence):
        raise TankartaDataError("Tankarta list-price response is not an array")
    if now.tzinfo is None:
        raise TankartaDataError("A timezone-aware update timestamp is required")
    if not privacy_salt:
        raise TankartaDataError("A privacy salt is required")

    parsed: dict[str, tuple[str, Decimal, Any]] = {}
    skipped = 0

    for item in payload:
        if not isinstance(item, Mapping):
            skipped += 1
            continue

        product = str(item.get("product") or "").strip()
        price = _price(item.get("productPrice"))
        if not product or price is None:
            skipped += 1
            continue

        division_id = item.get("divisionID")
        key = _reading_key(
            privacy_salt=privacy_salt,
            division_id=division_id,
            product=product,
        )
        previous = parsed.get(key)
        if previous is not None and previous[1] != price:
            raise TankartaDataError(
                f"Tankarta returned conflicting prices for product {product!r}"
            )
        parsed[key] = (product, price, division_id)

    if not parsed:
        raise TankartaDataError("Tankarta returned no valid product prices")

    by_product: dict[str, list[str]] = defaultdict(list)
    for key, (product, _price_value, _division_id) in parsed.items():
        by_product[product.casefold()].append(key)

    readings: dict[str, PriceReading] = {}
    for product_group in sorted(by_product):
        keys = sorted(by_product[product_group])
        for index, key in enumerate(keys, start=1):
            product, price, division_id = parsed[key]
            display_name = product if len(keys) == 1 else f"{product} (varianta {index})"
            readings[key] = PriceReading(
                key=key,
                product=product,
                display_name=display_name,
                price=price,
                division_id=division_id,
            )

    return TankartaData(
        updated_at=now,
        readings=readings,
        source_item_count=len(payload),
        skipped_item_count=skipped,
    )
