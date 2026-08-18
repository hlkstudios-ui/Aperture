import redis.asyncio as redis
from fastapi import HTTPException, status

from app.config import get_settings


async def enforce_rate_limit(key: str, *, limit: int, window_seconds: int, weight: int = 1) -> None:
    if get_settings().app_env in {"development", "test"}:
        limit *= 20
    client = redis.from_url(get_settings().redis_url)
    try:
        count = await client.incrby(key, weight)
        if count == weight:
            await client.expire(key, window_seconds)
        if count > limit:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts; try again later"
            )
    finally:
        await client.aclose()
