import time
import uuid
from datetime import UTC, datetime

import redis
from fastapi import HTTPException, status
from sqlalchemy import or_, select

from app.config import get_settings
from app.models import DeviceSession, Entitlement

ACQUIRE_LEASE = """
local key, country_key, member = KEYS[1], KEYS[2], ARGV[1]
local now, cutoff = tonumber(ARGV[2]), tonumber(ARGV[3])
local limit, ttl = tonumber(ARGV[4]), tonumber(ARGV[5])
local country = ARGV[6]
redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)
if redis.call('ZSCORE', key, member) then
  redis.call('ZADD', key, now, member)
  redis.call('EXPIRE', key, ttl)
  redis.call('HSET', country_key, member, country)
  redis.call('EXPIRE', country_key, ttl)
  return 1
end
if redis.call('ZCARD', key) >= limit then return 0 end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, ttl)
redis.call('HSET', country_key, member, country)
redis.call('EXPIRE', country_key, ttl)
return 1
"""

REFRESH_LEASE = """
local key, country_key, member = KEYS[1], KEYS[2], ARGV[1]
local now, cutoff, ttl = tonumber(ARGV[2]), tonumber(ARGV[3]), tonumber(ARGV[4])
redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)
if not redis.call('ZSCORE', key, member) then
  redis.call('HDEL', country_key, member)
  return false
end
local country = redis.call('HGET', country_key, member)
if country == false then return false end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, ttl)
redis.call('EXPIRE', country_key, ttl)
return country
"""


def stream_limit(db, user_id: uuid.UUID) -> int:
    now = datetime.now(UTC)
    entitlement = db.scalar(
        select(Entitlement)
        .where(
            Entitlement.user_id == user_id,
            Entitlement.key == "simultaneous_streams",
            or_(Entitlement.starts_at.is_(None), Entitlement.starts_at <= now),
            or_(Entitlement.ends_at.is_(None), Entitlement.ends_at > now),
        )
        .order_by(Entitlement.created_at.desc())
        .limit(1)
    )
    raw = entitlement.value.get("limit") if entitlement else 1
    try:
        return max(1, min(int(raw), 100))
    except (TypeError, ValueError):
        return 1


def acquire_stream_lease(db, session: DeviceSession, country: str | None = None) -> None:
    settings = get_settings()
    now = int(time.time())
    client = redis.from_url(settings.redis_url, socket_timeout=3)
    try:
        allowed = client.eval(
            ACQUIRE_LEASE,
            2,
            f"playback-leases:{session.user_id}",
            f"playback-lease-countries:{session.user_id}",
            str(session.id),
            now,
            now - settings.playback_lease_seconds,
            stream_limit(db, session.user_id),
            settings.playback_lease_seconds + 30,
            country or "",
        )
    except redis.RedisError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Playback coordination unavailable"
        ) from exc
    finally:
        client.close()
    if not allowed:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This account is already streaming on the maximum number of devices",
        )


def refresh_stream_lease(session: DeviceSession) -> str | None:
    settings = get_settings()
    now = int(time.time())
    client = redis.from_url(settings.redis_url, socket_timeout=3)
    key = f"playback-leases:{session.user_id}"
    country_key = f"playback-lease-countries:{session.user_id}"
    try:
        country = client.eval(
            REFRESH_LEASE,
            2,
            key,
            country_key,
            str(session.id),
            now,
            now - settings.playback_lease_seconds,
            settings.playback_lease_seconds + 30,
        )
        if country is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Playback lease is inactive")
    except redis.RedisError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Playback coordination unavailable"
        ) from exc
    finally:
        client.close()
    decoded = country.decode() if isinstance(country, bytes) else str(country)
    return decoded or None
