import pytest
from fastapi import HTTPException

from app.config import get_settings
from app.geo import (
    normalize_country,
    optional_viewer_country,
    sign_geo_assertion,
    verify_geo_assertion,
)


def test_signed_geo_assertion_normalizes_and_verifies() -> None:
    issued_at = 1_700_000_000
    secret = get_settings().geo_assertion_secret
    signature = sign_geo_assertion(" ca ", issued_at, secret)

    assert verify_geo_assertion("ca", str(issued_at), signature, now=issued_at + 60) == "CA"


@pytest.mark.parametrize("country", ["", "CAN", "1A", "C-"])
def test_country_must_be_iso_alpha_two(country: str) -> None:
    with pytest.raises(ValueError, match="ISO 3166-1"):
        normalize_country(country)


def test_geo_assertion_rejects_missing_tampered_expired_and_future_values() -> None:
    issued_at = 1_700_000_000
    secret = get_settings().geo_assertion_secret
    signature = sign_geo_assertion("CA", issued_at, secret)

    with pytest.raises(HTTPException) as missing:
        verify_geo_assertion(None, None, None, now=issued_at)
    assert missing.value.status_code == 403

    with pytest.raises(HTTPException, match="invalid"):
        verify_geo_assertion("US", str(issued_at), signature, now=issued_at)

    with pytest.raises(HTTPException, match="expired"):
        verify_geo_assertion("CA", str(issued_at), signature, now=issued_at + 121)

    future = issued_at + 31
    with pytest.raises(HTTPException, match="not yet valid"):
        verify_geo_assertion(
            "CA", str(future), sign_geo_assertion("CA", future, secret), now=issued_at
        )


def test_optional_geo_allows_absence_but_rejects_partial_assertions() -> None:
    assert optional_viewer_country() is None
    with pytest.raises(HTTPException, match="Trusted viewer region"):
        optional_viewer_country(country="CA")
