import uuid
from types import SimpleNamespace

import pytest
import redis
from fastapi import HTTPException

from app.config import get_settings
from app.stream_limits import acquire_stream_lease, refresh_stream_lease


class EntitlementDb:
    def __init__(self, limit: object = 1):
        self.entitlement = SimpleNamespace(value={"limit": limit})

    def scalar(self, _statement):
        return self.entitlement


def session(user_id: uuid.UUID):
    return SimpleNamespace(id=uuid.uuid4(), user_id=user_id)


def test_stream_lease_enforces_device_limit_and_refreshes_existing_session() -> None:
    user_id = uuid.uuid4()
    first, second = session(user_id), session(user_id)
    client = redis.from_url(get_settings().redis_url)
    key = f"playback-leases:{user_id}"
    country_key = f"playback-lease-countries:{user_id}"
    client.delete(key, country_key)
    try:
        acquire_stream_lease(EntitlementDb(1), first, "CA")
        acquire_stream_lease(EntitlementDb(1), first, "CA")
        assert refresh_stream_lease(first) == "CA"
        assert client.hget(country_key, str(first.id)) == b"CA"
        with pytest.raises(HTTPException) as blocked:
            acquire_stream_lease(EntitlementDb(1), second)
        assert blocked.value.status_code == 409

        client.zadd(key, {str(first.id): 0})
        acquire_stream_lease(EntitlementDb(1), second, "US")
        assert refresh_stream_lease(second) == "US"
        with pytest.raises(HTTPException) as expired:
            refresh_stream_lease(first)
        assert expired.value.status_code == 403
    finally:
        client.delete(key, country_key)
        client.close()


def test_invalid_entitlement_fails_closed_to_one_stream() -> None:
    user_id = uuid.uuid4()
    first, second = session(user_id), session(user_id)
    client = redis.from_url(get_settings().redis_url)
    key = f"playback-leases:{user_id}"
    client.delete(key)
    try:
        acquire_stream_lease(EntitlementDb("invalid"), first)
        with pytest.raises(HTTPException) as blocked:
            acquire_stream_lease(EntitlementDb("invalid"), second)
        assert blocked.value.status_code == 409
    finally:
        client.delete(key)
        client.close()
