import asyncio
import json

import pytest

from app import oauth_broker
from app.oauth_broker import OAuthAttempt, OAuthBrokerUnavailable, OAuthHandoff


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.closed = False

    async def set(self, key: str, value: str, *, ex: int, nx: bool) -> bool:
        assert ex > 0
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def getdel(self, key: str) -> str | None:
        return self.values.pop(key, None)

    async def eval(self, _script: str, _key_count: int, key: str, origin: str):
        raw = self.values.get(key)
        if raw is None:
            return [0]
        payload = json.loads(raw)
        if payload.get("return_origin") != origin:
            return [-1]
        self.values.pop(key)
        return [1, raw]

    async def aclose(self) -> None:
        self.closed = True


def test_attempt_and_handoff_are_one_time_and_keys_do_not_contain_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeRedis()
    monkeypatch.setattr(oauth_broker, "_client", lambda: client)

    state = "signed-state-containing-a-nonce"
    attempt = OAuthAttempt(
        provider="google",
        verifier="private-pkce-verifier",
        return_origin="https://watch.customer.example",
    )
    asyncio.run(oauth_broker.store_attempt(state, attempt))
    assert all(state not in key and attempt.verifier not in key for key in client.values)
    assert asyncio.run(oauth_broker.consume_attempt(state)) == attempt
    assert asyncio.run(oauth_broker.consume_attempt(state)) is None

    code = "short-lived-browser-handoff-code"
    handoff = OAuthHandoff(
        session_id="session-id",
        session_token="private-session-token",
        return_origin=attempt.return_origin,
        email="viewer@example.test",
        provider="google",
        label="Viewer",
    )
    asyncio.run(oauth_broker.store_handoff(code, handoff))
    assert all(code not in key and handoff.session_token not in key for key in client.values)
    assert (
        asyncio.run(
            oauth_broker.consume_handoff_for_origin(code, "https://wrong.customer.example")
        )
        is None
    )
    assert (
        asyncio.run(oauth_broker.consume_handoff_for_origin(code, attempt.return_origin))
        == handoff
    )
    assert (
        asyncio.run(oauth_broker.consume_handoff_for_origin(code, attempt.return_origin))
        is None
    )
    assert client.closed is True


def test_one_time_state_collision_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeRedis()
    monkeypatch.setattr(oauth_broker, "_client", lambda: client)
    attempt = OAuthAttempt("github", "verifier", "https://apertures.online")
    asyncio.run(oauth_broker.store_attempt("same-state", attempt))
    with pytest.raises(OAuthBrokerUnavailable, match="one-time state"):
        asyncio.run(oauth_broker.store_attempt("same-state", attempt))
