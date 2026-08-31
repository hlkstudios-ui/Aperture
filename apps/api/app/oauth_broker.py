import hashlib
import json
from dataclasses import asdict, dataclass

import redis.asyncio as redis

from app.config import get_settings

ATTEMPT_TTL_SECONDS = 10 * 60
HANDOFF_TTL_SECONDS = 90
ORIGIN_BOUND_CONSUME = """
local raw = redis.call('GET', KEYS[1])
if not raw then return {0} end
local ok, payload = pcall(cjson.decode, raw)
if not ok or type(payload) ~= 'table' or type(payload['return_origin']) ~= 'string' then
  return {-2}
end
if payload['return_origin'] ~= ARGV[1] then return {-1} end
redis.call('DEL', KEYS[1])
return {1, raw}
"""


class OAuthBrokerUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class OAuthAttempt:
    provider: str
    verifier: str
    return_origin: str


@dataclass(frozen=True)
class OAuthHandoff:
    session_id: str
    session_token: str
    return_origin: str
    email: str
    provider: str
    label: str


def _key(kind: str, opaque_value: str) -> str:
    digest = hashlib.sha256(opaque_value.encode()).hexdigest()
    return f"aperture:oauth:{kind}:{digest}"


def _client():
    return redis.from_url(
        get_settings().redis_url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
    )


async def _store(kind: str, opaque_value: str, payload: dict[str, str], ttl: int) -> None:
    client = _client()
    try:
        stored = await client.set(
            _key(kind, opaque_value),
            json.dumps(payload, separators=(",", ":")),
            ex=ttl,
            nx=True,
        )
        if not stored:
            raise OAuthBrokerUnavailable("OAuth broker could not reserve one-time state")
    except redis.RedisError as error:
        raise OAuthBrokerUnavailable("OAuth broker storage is unavailable") from error
    finally:
        await client.aclose()


async def _consume(kind: str, opaque_value: str) -> dict[str, str] | None:
    client = _client()
    try:
        raw = await client.getdel(_key(kind, opaque_value))
    except redis.RedisError as error:
        raise OAuthBrokerUnavailable("OAuth broker storage is unavailable") from error
    finally:
        await client.aclose()
    if raw is None:
        return None
    return _decode_payload(raw)


def _decode_payload(raw: str) -> dict[str, str]:
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as error:
        raise OAuthBrokerUnavailable("OAuth broker state is invalid") from error
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in payload.items()
    ):
        raise OAuthBrokerUnavailable("OAuth broker state is invalid")
    return payload


async def store_attempt(state: str, attempt: OAuthAttempt) -> None:
    await _store("attempt", state, asdict(attempt), ATTEMPT_TTL_SECONDS)


async def consume_attempt(state: str) -> OAuthAttempt | None:
    payload = await _consume("attempt", state)
    if payload is None:
        return None
    try:
        return OAuthAttempt(**payload)
    except TypeError as error:
        raise OAuthBrokerUnavailable("OAuth broker attempt is invalid") from error


async def store_handoff(code: str, handoff: OAuthHandoff) -> None:
    await _store("handoff", code, asdict(handoff), HANDOFF_TTL_SECONDS)


async def consume_handoff(code: str) -> OAuthHandoff | None:
    payload = await _consume("handoff", code)
    if payload is None:
        return None
    try:
        return OAuthHandoff(**payload)
    except TypeError as error:
        raise OAuthBrokerUnavailable("OAuth broker handoff is invalid") from error


async def consume_handoff_for_origin(
    code: str, expected_return_origin: str
) -> OAuthHandoff | None:
    client = _client()
    try:
        result = await client.eval(
            ORIGIN_BOUND_CONSUME,
            1,
            _key("handoff", code),
            expected_return_origin,
        )
    except redis.RedisError as error:
        raise OAuthBrokerUnavailable("OAuth broker storage is unavailable") from error
    finally:
        await client.aclose()
    if not isinstance(result, list) or not result:
        raise OAuthBrokerUnavailable("OAuth broker state is invalid")
    outcome = result[0]
    if outcome in {0, -1}:
        return None
    if outcome != 1 or len(result) != 2 or not isinstance(result[1], str):
        raise OAuthBrokerUnavailable("OAuth broker state is invalid")
    payload = _decode_payload(result[1])
    try:
        return OAuthHandoff(**payload)
    except TypeError as error:
        raise OAuthBrokerUnavailable("OAuth broker handoff is invalid") from error
