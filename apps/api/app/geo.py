import hashlib
import hmac
import re
import time
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.config import get_settings

COUNTRY_PATTERN = re.compile(r"^[A-Z]{2}$")
FUTURE_CLOCK_SKEW_SECONDS = 30


def normalize_country(country: str) -> str:
    normalized = country.strip().upper()
    if not COUNTRY_PATTERN.fullmatch(normalized):
        raise ValueError("Country must be an ISO 3166-1 alpha-2 code")
    return normalized


def sign_geo_assertion(country: str, timestamp: int, secret: str) -> str:
    normalized = normalize_country(country)
    return hmac.new(
        secret.encode(), f"{normalized}:{timestamp}".encode(), hashlib.sha256
    ).hexdigest()


def verify_geo_assertion(
    country: str | None,
    timestamp: str | None,
    signature: str | None,
    *,
    now: int | None = None,
) -> str:
    if not country or not timestamp or not signature:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Trusted viewer region is required")
    try:
        normalized = normalize_country(country)
        issued_at = int(timestamp)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Viewer region assertion is invalid"
        ) from exc

    current = int(time.time()) if now is None else now
    settings = get_settings()
    if issued_at > current + FUTURE_CLOCK_SKEW_SECONDS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Viewer region assertion is not yet valid")
    if current - issued_at > settings.geo_assertion_max_age_seconds:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Viewer region assertion has expired")

    expected = sign_geo_assertion(normalized, issued_at, settings.geo_assertion_secret)
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Viewer region assertion is invalid")
    return normalized


def trusted_viewer_country(
    country: Annotated[str | None, Header(alias="X-Aperture-Country")] = None,
    timestamp: Annotated[str | None, Header(alias="X-Aperture-Geo-Timestamp")] = None,
    signature: Annotated[str | None, Header(alias="X-Aperture-Geo-Signature")] = None,
) -> str:
    return verify_geo_assertion(country, timestamp, signature)


ViewerCountry = Annotated[str, Depends(trusted_viewer_country)]


def optional_viewer_country(
    country: Annotated[str | None, Header(alias="X-Aperture-Country")] = None,
    timestamp: Annotated[str | None, Header(alias="X-Aperture-Geo-Timestamp")] = None,
    signature: Annotated[str | None, Header(alias="X-Aperture-Geo-Signature")] = None,
) -> str | None:
    if country is None and timestamp is None and signature is None:
        return None
    return verify_geo_assertion(country, timestamp, signature)


OptionalViewerCountry = Annotated[str | None, Depends(optional_viewer_country)]
