import os

import pytest

from app import e2e_redis_fence
from app.e2e_redis_fence import (
    ACQUIRE_OWNER,
    OWNER_KEY,
    RECLAIM_OWNER,
    RELEASE_OWNER,
    E2ERedisFenceError,
    acquire_owner,
    release_owner,
    verify_owner,
)

REDIS_URL = "redis://127.0.0.1:6380/14"
RUN_ONE = "owner-safety01"
RUN_TWO = "owner-safety02"
TOKEN_ONE = "1" * 64
TOKEN_TWO = "2" * 64


class FakeRedis:
    def __init__(self, values: dict[str, bytes] | None = None) -> None:
        self.values = values or {}

    def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    def eval(self, script: str, _keys: int, key: str, *arguments: str) -> object:
        if script == ACQUIRE_OWNER:
            current = self.values.get(key)
            if current is not None:
                return [b"existing", current]
            if self.values:
                return [b"dirty", str(len(self.values)).encode()]
            self.values[key] = arguments[0].encode()
            return [b"acquired", self.values[key]]
        if script == RECLAIM_OWNER:
            if self.values.get(key) != arguments[0].encode():
                return 0
            self.values.clear()
            self.values[key] = arguments[1].encode()
            return 1
        if script == RELEASE_OWNER:
            if self.values.get(key) != arguments[0].encode():
                return 0
            self.values.clear()
            return 1
        raise AssertionError("unexpected Redis script")


@pytest.mark.parametrize("reclaim_dead_local", [False, True])
def test_acquire_refuses_unknown_preexisting_keys_without_modifying_them(
    reclaim_dead_local: bool,
) -> None:
    client = FakeRedis({"unowned-application-key": b"keep-me"})

    with pytest.raises(E2ERedisFenceError, match="unknown preexisting keys"):
        acquire_owner(
            REDIS_URL,
            RUN_ONE,
            TOKEN_ONE,
            os.getpid(),
            reclaim_dead_local=reclaim_dead_local,
            client=client,
        )

    assert client.values == {"unowned-application-key": b"keep-me"}


def test_acquire_rejects_a_query_parameter_database_override() -> None:
    with pytest.raises(E2ERedisFenceError, match="query or fragment"):
        acquire_owner(
            f"{REDIS_URL}?db=0",
            RUN_ONE,
            TOKEN_ONE,
            os.getpid(),
            client=FakeRedis(),
        )


def test_acquire_refuses_a_concurrent_run_owner() -> None:
    client = FakeRedis()
    acquire_owner(REDIS_URL, RUN_ONE, TOKEN_ONE, os.getpid(), client=client)

    with pytest.raises(E2ERedisFenceError, match="refusing concurrent access"):
        acquire_owner(REDIS_URL, RUN_TWO, TOKEN_TWO, os.getpid(), client=client)

    assert verify_owner(REDIS_URL, RUN_ONE, TOKEN_ONE, client=client).run_id == RUN_ONE


def test_reclaim_flag_still_refuses_an_active_owner() -> None:
    client = FakeRedis()
    acquire_owner(REDIS_URL, RUN_ONE, TOKEN_ONE, os.getpid(), client=client)

    with pytest.raises(E2ERedisFenceError, match="still active"):
        acquire_owner(
            REDIS_URL,
            RUN_TWO,
            TOKEN_TWO,
            os.getpid(),
            reclaim_dead_local=True,
            client=client,
        )


def test_explicit_reclaim_replaces_only_a_proven_dead_local_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeRedis()
    acquire_owner(REDIS_URL, RUN_ONE, TOKEN_ONE, 999_999, client=client)
    client.values["previous-run-key"] = b"fixture"
    monkeypatch.setattr(e2e_redis_fence, "process_is_alive", lambda _pid: False)

    owner = acquire_owner(
        REDIS_URL,
        RUN_TWO,
        TOKEN_TWO,
        os.getpid(),
        reclaim_dead_local=True,
        client=client,
    )

    assert owner.run_id == RUN_TWO
    assert set(client.values) == {OWNER_KEY}


def test_release_flushes_only_the_matching_owner() -> None:
    client = FakeRedis()
    acquire_owner(REDIS_URL, RUN_ONE, TOKEN_ONE, os.getpid(), client=client)
    client.values["run-owned-key"] = b"fixture"

    with pytest.raises(E2ERedisFenceError, match="different E2E run"):
        release_owner(REDIS_URL, RUN_TWO, TOKEN_TWO, client=client)
    assert "run-owned-key" in client.values

    release_owner(REDIS_URL, RUN_ONE, TOKEN_ONE, client=client)
    assert client.values == {}
