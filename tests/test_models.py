"""Tests for privacy-preserving Tankarta list-price parsing."""

from datetime import UTC, datetime
from decimal import Decimal
import importlib.util
from pathlib import Path
import sys

_MODELS_PATH = (
    Path(__file__).parents[1] / "custom_components" / "tankarta" / "models.py"
)
_SPEC = importlib.util.spec_from_file_location("tankarta_models_for_tests", _MODELS_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODELS = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODELS
_SPEC.loader.exec_module(_MODELS)
parse_prices = _MODELS.parse_prices


SAMPLE = [
    {"divisionID": 101010, "product": "Verva 100", "productPrice": 48.67},
    {"divisionID": 101010, "product": "Verva Diesel", "productPrice": 50.46},
    {"divisionID": 101010, "product": "ADBlue", "productPrice": 23.90},
    {"divisionID": 101010, "product": "Efecta 95", "productPrice": 43.67},
    {"divisionID": 101010, "product": "Efecta Diesel", "productPrice": 46.46},
    {"divisionID": 101010, "product": "H2", "productPrice": 499.00},
    {"divisionID": 101010, "product": "HVO100 DIESEL", "productPrice": 49.90},
]


def test_sample_payload_creates_seven_readings_with_division_attribute() -> None:
    data = parse_prices(
        SAMPLE,
        now=datetime(2026, 7, 27, tzinfo=UTC),
        privacy_salt="account-salt",
    )

    assert len(data.readings) == 7
    assert {reading.product for reading in data.readings.values()} == {
        "Verva 100",
        "Verva Diesel",
        "ADBlue",
        "Efecta 95",
        "Efecta Diesel",
        "H2",
        "HVO100 DIESEL",
    }
    assert next(
        reading.price
        for reading in data.readings.values()
        if reading.product == "Verva 100"
    ) == Decimal("48.67")
    reading = next(
        reading for reading in data.readings.values() if reading.product == "Verva 100"
    )
    assert reading.division_id == 101010
    assert "101010" not in reading.key


def test_duplicate_product_names_are_disambiguated_with_opaque_keys() -> None:
    data = parse_prices(
        [
            {"divisionID": 100, "product": "Efecta 95", "productPrice": 40},
            {"divisionID": 200, "product": "Efecta 95", "productPrice": 41},
        ],
        now=datetime(2026, 7, 27, tzinfo=UTC),
        privacy_salt="account-salt",
    )

    assert {reading.display_name for reading in data.readings.values()} == {
        "Efecta 95 (varianta 1)",
        "Efecta 95 (varianta 2)",
    }
    assert {reading.division_id for reading in data.readings.values()} == {100, 200}
    assert all("100" not in reading.key for reading in data.readings.values())
    assert all("200" not in reading.key for reading in data.readings.values())
