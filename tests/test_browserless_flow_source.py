"""Static guardrails for the Browserless login/error-detection sequence."""

from pathlib import Path


SOURCE = (
    Path(__file__).parents[1]
    / "custom_components"
    / "tankarta"
    / "browserless_function.js"
).read_text(encoding="utf-8")


def test_login_is_attempted_before_price_fetch_for_missing_session() -> None:
    restore = SOURCE.index("const sessionAuthenticated = await restoreSession()")
    login = SOURCE.index("await loginFresh()", restore)
    fetch = SOURCE.index("prices = await fetchPrices()", login)
    assert restore < login < fetch


def test_endpoint_404_has_specific_error_code() -> None:
    assert '"endpoint_not_found"' in SOURCE
    assert '"list_price_request_not_observed"' in SOURCE
    assert '"portal_unreachable"' in SOURCE
    assert '"authentication_failed"' in SOURCE


def test_prices_are_captured_from_native_dashboard_post() -> None:
    assert 'request.method().toUpperCase() !== "POST"' in SOURCE
    assert 'page.on("response"' in SOURCE
    assert '"/Dashboard-ListPrice"' in SOURCE
    assert 'method: "GET"' not in SOURCE


def test_request_body_is_not_replayed_or_logged() -> None:
    assert 'request.postData()' in SOURCE
    assert 'listPriceRequestBodyLength' in SOURCE
    assert 'postData,' not in SOURCE


def test_diagnostics_do_not_capture_input_values() -> None:
    diagnostics_section = SOURCE[SOURCE.index("async function pageSnapshot") : SOURCE.index("async function fail")]
    assert "input.value" not in diagnostics_section
    assert "cookie.value" not in diagnostics_section
