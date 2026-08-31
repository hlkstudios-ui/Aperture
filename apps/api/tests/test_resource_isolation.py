from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import conftest as pytest_conftest
import pytest

from test_support.resource_isolation import (
    TEST_REDIS_DATABASE,
    UnsafeTestResourceError,
    assert_disposable_bucket_name,
    assert_disposable_database_name,
    assert_isolated_redis_url,
    build_test_resource_plan,
    is_proven_dead_local_owner,
    is_reapable_owner,
    new_resource_owner,
    parse_resource_owner,
    safe_url,
)

LOCAL_DATABASE = "postgresql+psycopg://aperture:secret@127.0.0.1:5432/aperture_dev"
LOCAL_REDIS = "redis://127.0.0.1:6379/0"
LOCAL_S3 = "http://127.0.0.1:9000"


class FakeOwnerRedis:
    def __init__(self, entries: dict[bytes, bytes] | None = None) -> None:
        self.entries = entries or {}
        self.deleted: list[bytes] = []
        self.set_kwargs: list[dict] = []
        self.closed = False

    def ping(self) -> bool:
        return True

    def scan_iter(self):
        return iter(self.entries)

    def get(self, key):
        encoded = key.encode() if isinstance(key, str) else key
        return self.entries.get(encoded)

    def set(self, key, value, **kwargs) -> bool:
        self.set_kwargs.append(kwargs)
        encoded = key.encode() if isinstance(key, str) else key
        if kwargs.get("nx") and encoded in self.entries:
            return False
        self.entries[encoded] = value
        return True

    def delete(self, *keys) -> int:
        removed = 0
        for key in keys:
            encoded = key.encode() if isinstance(key, str) else key
            if encoded in self.entries:
                self.deleted.append(encoded)
                del self.entries[encoded]
                removed += 1
        return removed

    def exists(self, key) -> bool:
        encoded = key.encode() if isinstance(key, str) else key
        return encoded in self.entries

    def eval(self, script, key_count, *values) -> int:
        owner_key = values[0]
        encoded_owner = owner_key.encode() if isinstance(owner_key, str) else owner_key
        if "redis.call('set'" in script:
            expected, replacement = values[1:]
            if self.entries.get(encoded_owner) != expected:
                return 0
            self.entries[encoded_owner] = replacement
            return 1
        if key_count > 1:
            expected = values[-1]
            if self.entries.get(encoded_owner) != expected:
                return -1
            return self.delete(*values[1:-1])
        expected = values[1]
        if self.entries.get(encoded_owner) != expected:
            return 0
        del self.entries[encoded_owner]
        return 1

    def close(self) -> None:
        self.closed = True


class FakeScalarResult:
    def __init__(self, value: int) -> None:
        self.value = value

    def scalar_one(self) -> int:
        return self.value


class FakeAdminConnection:
    def __init__(self, database_rows: list[tuple[str, str | None]]) -> None:
        self.database_rows = database_rows
        self.dropped: list[str] = []

    def exec_driver_sql(self, statement: str, _parameters=None):
        if statement.startswith("SELECT datname"):
            return iter(self.database_rows)
        if statement.startswith("SELECT count"):
            return FakeScalarResult(0)
        if statement.startswith("DROP DATABASE"):
            self.dropped.append(statement)
            return None
        raise AssertionError(statement)


class FakeBody:
    def __init__(self, value: bytes) -> None:
        self.value = value

    def read(self) -> bytes:
        return self.value


class FakeStaleS3:
    def __init__(self, owners: dict[str, bytes]) -> None:
        self.owners = owners

    def list_buckets(self):
        names = [*self.owners, "production-media"]
        return {"Buckets": [{"Name": name} for name in names]}

    def get_object(self, *, Bucket, **_kwargs):
        if Bucket not in self.owners:
            raise KeyError(Bucket)
        return {"Body": FakeBody(self.owners[Bucket])}


def build_plan(**overrides: str):
    values = {
        "app_env": "development",
        "database_url": LOCAL_DATABASE,
        "redis_url": LOCAL_REDIS,
        "s3_endpoint": LOCAL_S3,
        "run_token": "deadbeef1234",
    }
    values.update(overrides)
    return build_test_resource_plan(**values)


def test_plan_replaces_every_mutable_resource() -> None:
    plan = build_plan()

    assert plan.database_name == "aperture_pytest_deadbeef1234"
    assert plan.database_url.endswith("/aperture_pytest_deadbeef1234")
    assert plan.admin_database_url.endswith("/postgres")
    assert plan.redis_url == f"redis://127.0.0.1:6379/{TEST_REDIS_DATABASE}"
    assert plan.s3_bucket == "aperture-pytest-deadbeef1234"
    assert "aperture_dev" not in plan.database_url


@pytest.mark.parametrize("app_env", ["staging", "production", "preview", ""])
def test_plan_rejects_non_test_source_environments(app_env: str) -> None:
    with pytest.raises(UnsafeTestResourceError, match="APP_ENV"):
        build_plan(app_env=app_env)


@pytest.mark.parametrize(
    ("field", "url"),
    [
        (
            "database_url",
            "postgresql+psycopg://aperture:secret@db.example.com:5432/aperture",
        ),
        ("redis_url", "redis://cache.example.com:6379/0"),
        ("s3_endpoint", "https://s3.example.com"),
    ],
)
def test_plan_rejects_remote_services(field: str, url: str) -> None:
    with pytest.raises(UnsafeTestResourceError, match="loopback"):
        build_plan(**{field: url})


def test_plan_rejects_unsupported_database_engines_and_bad_tokens() -> None:
    with pytest.raises(UnsafeTestResourceError, match="PostgreSQL"):
        build_plan(database_url="sqlite:///aperture.db")
    with pytest.raises(UnsafeTestResourceError, match="run token"):
        build_plan(run_token="unsafe_token!")


@pytest.mark.parametrize(
    "database_name",
    ["aperture", "aperture_pytest_", "aperture_pytest_bad-name", "production"],
)
def test_database_destructive_guard_rejects_non_generated_names(database_name: str) -> None:
    with pytest.raises(UnsafeTestResourceError, match="Refusing destructive database"):
        assert_disposable_database_name(database_name)


@pytest.mark.parametrize(
    "bucket_name",
    ["aperture", "aperture-pytest-", "aperture-pytest-BADUPPER", "production-media"],
)
def test_bucket_destructive_guard_rejects_non_generated_names(bucket_name: str) -> None:
    with pytest.raises(UnsafeTestResourceError, match="Refusing destructive bucket"):
        assert_disposable_bucket_name(bucket_name)


def test_redis_destructive_guard_requires_database_fifteen() -> None:
    assert_isolated_redis_url("redis://localhost:6379/15")
    with pytest.raises(UnsafeTestResourceError, match="outside database 15"):
        assert_isolated_redis_url("redis://localhost:6379/0")


def test_safe_url_redacts_password() -> None:
    rendered = safe_url(LOCAL_DATABASE)

    assert "secret" not in rendered
    assert "***" in rendered


def test_resource_owner_round_trip_is_bound_to_exact_resource() -> None:
    owner = new_resource_owner(
        resource_kind="s3-bucket",
        resource_name="aperture-pytest-deadbeef1234",
        run_token="deadbeef1234",
    )

    restored = parse_resource_owner(
        owner.to_json(),
        resource_kind="s3-bucket",
        resource_name="aperture-pytest-deadbeef1234",
    )

    assert restored == owner
    with pytest.raises(UnsafeTestResourceError, match="invalid ownership"):
        parse_resource_owner(
            owner.to_json(),
            resource_kind="s3-bucket",
            resource_name="aperture-pytest-feedface1234",
        )


def test_only_a_dead_owner_on_this_host_is_reclaimable() -> None:
    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    owner = new_resource_owner(
        resource_kind="postgresql-database",
        resource_name="aperture_pytest_deadbeef1234",
        run_token="deadbeef1234",
        now=created_at,
    )

    assert is_proven_dead_local_owner(
        owner,
        hostname=owner.hostname,
        process_is_alive=lambda _pid: False,
    )
    assert not is_proven_dead_local_owner(
        owner,
        hostname=owner.hostname,
        process_is_alive=lambda _pid: True,
    )
    assert not is_proven_dead_local_owner(
        owner,
        hostname="some-other-host",
        process_is_alive=lambda _pid: False,
    )
    assert not is_reapable_owner(
        owner,
        minimum_age_seconds=300,
        now=created_at + timedelta(seconds=299),
        hostname=owner.hostname,
        process_is_alive=lambda _pid: False,
    )
    assert is_reapable_owner(
        owner,
        minimum_age_seconds=300,
        now=created_at + timedelta(seconds=300),
        hostname=owner.hostname,
        process_is_alive=lambda _pid: False,
    )


@pytest.mark.parametrize(
    "payload",
    [
        "{}",
        '{"schema":"aperture.pytest.resource-owner.v1"}',
        "not-json",
    ],
)
def test_resource_owner_rejects_incomplete_or_malformed_metadata(payload: str) -> None:
    with pytest.raises(UnsafeTestResourceError, match="invalid ownership"):
        parse_resource_owner(
            payload,
            resource_kind="redis-database",
            resource_name="redis-db-15",
        )


def test_redis_claim_refuses_unknown_preexisting_keys(monkeypatch) -> None:
    client = FakeOwnerRedis({b"unknown:key": b"do-not-delete"})
    monkeypatch.setattr(
        pytest_conftest.redis.Redis,
        "from_url",
        lambda *_args, **_kwargs: client,
    )
    sandbox = pytest_conftest.TestResourceSandbox(SimpleNamespace(), build_plan())

    with pytest.raises(UnsafeTestResourceError, match="without valid pytest ownership"):
        sandbox._claim_redis_database()

    assert client.entries == {b"unknown:key": b"do-not-delete"}
    assert client.deleted == []
    assert client.closed


def test_redis_claim_has_durable_owner_without_expiration(monkeypatch) -> None:
    client = FakeOwnerRedis()
    monkeypatch.setattr(
        pytest_conftest.redis.Redis,
        "from_url",
        lambda *_args, **_kwargs: client,
    )
    sandbox = pytest_conftest.TestResourceSandbox(SimpleNamespace(), build_plan())

    sandbox._claim_redis_database()

    assert client.set_kwargs == [{"nx": True}]
    payload = client.entries[pytest_conftest.REDIS_OWNER_KEY.encode()]
    owner = parse_resource_owner(
        payload,
        resource_kind="redis-database",
        resource_name=pytest_conftest.REDIS_RESOURCE_NAME,
    )
    assert owner.pid > 0
    assert owner.hostname
    assert owner.run_token == sandbox.plan.run_token


def test_redis_claim_reclaims_only_exact_keys_of_proven_dead_local_owner(
    monkeypatch,
) -> None:
    previous = new_resource_owner(
        resource_kind="redis-database",
        resource_name=pytest_conftest.REDIS_RESOURCE_NAME,
        run_token="feedface1234",
    ).to_json().encode()
    client = FakeOwnerRedis(
        {
            pytest_conftest.REDIS_OWNER_KEY.encode(): previous,
            b"stale:test:key": b"fixture",
        }
    )
    monkeypatch.setattr(
        pytest_conftest.redis.Redis,
        "from_url",
        lambda *_args, **_kwargs: client,
    )
    monkeypatch.setattr(
        pytest_conftest,
        "is_proven_dead_local_owner",
        lambda _owner: True,
    )
    sandbox = pytest_conftest.TestResourceSandbox(SimpleNamespace(), build_plan())

    sandbox._claim_redis_database()

    assert client.deleted == [b"stale:test:key"]
    assert set(client.entries) == {pytest_conftest.REDIS_OWNER_KEY.encode()}
    assert client.entries[pytest_conftest.REDIS_OWNER_KEY.encode()] != previous


def test_stale_database_reaper_selects_only_exact_owned_resource(monkeypatch) -> None:
    owned_name = "aperture_pytest_feedface1234"
    owned = new_resource_owner(
        resource_kind="postgresql-database",
        resource_name=owned_name,
        run_token="feedface1234",
    ).to_json()
    connection = FakeAdminConnection(
        [
            (owned_name, owned),
            ("aperture_pytest_deadbeef1234", None),
        ]
    )
    monkeypatch.setattr(
        pytest_conftest,
        "is_reapable_owner",
        lambda _owner, **_kwargs: True,
    )
    sandbox = pytest_conftest.TestResourceSandbox(SimpleNamespace(), build_plan())

    sandbox._reap_stale_databases(connection)

    assert connection.dropped == [f'DROP DATABASE "{owned_name}"']


def test_stale_bucket_reaper_selects_only_exact_owned_resource(monkeypatch) -> None:
    owned_name = "aperture-pytest-feedface1234"
    unknown_name = "aperture-pytest-deadbeef1234"
    owned = new_resource_owner(
        resource_kind="s3-bucket",
        resource_name=owned_name,
        run_token="feedface1234",
    ).to_json().encode()
    client = FakeStaleS3(
        {
            owned_name: owned,
            unknown_name: b"malformed metadata",
        }
    )
    monkeypatch.setattr(
        pytest_conftest,
        "is_reapable_owner",
        lambda _owner, **_kwargs: True,
    )
    sandbox = pytest_conftest.TestResourceSandbox(SimpleNamespace(), build_plan())
    sandbox.s3 = client
    deleted: list[str] = []
    monkeypatch.setattr(sandbox, "_empty_and_delete_bucket", deleted.append)

    sandbox._reap_stale_buckets()

    assert deleted == [owned_name]
