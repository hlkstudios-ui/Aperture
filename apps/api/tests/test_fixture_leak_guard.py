from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError

from scripts import fixture_leak_guard as guard


class FakeDatabaseResult:
    def __init__(self, database: str, username: str) -> None:
        self.database = database
        self.username = username

    def one(self) -> tuple[str, str]:
        return self.database, self.username


class FakeDatabaseSession:
    def __init__(self, database: str, username: str) -> None:
        self.result = FakeDatabaseResult(database, username)

    def execute(self, _statement) -> FakeDatabaseResult:
        return self.result


class EmptyJobDatabase:
    def get(self, _model, _job_id):
        return None


class FakeS3:
    def __init__(self, keys: set[str], *, errors: bool = False) -> None:
        self.keys = keys
        self.errors = errors
        self.delete_calls: list[list[dict[str, str]]] = []

    def head_bucket(self, **_kwargs) -> None:
        return None

    def delete_objects(self, *, Delete, **_kwargs):
        objects = Delete["Objects"]
        self.delete_calls.append(objects)
        if self.errors:
            return {"Errors": [{"Key": objects[0]["Key"], "Code": "AccessDenied"}]}
        self.keys.difference_update(item["Key"] for item in objects)
        return {}

    def head_object(self, *, Key, **_kwargs):
        if Key not in self.keys:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "HeadObject")
        return {"ContentLength": 1}


class FakeRedis:
    def __init__(self) -> None:
        self.keys = {"community:review:fixture-profile", "legitimate:key"}
        self.queues = {
            guard.SCENE_QUEUE: ["fixture-job", "legitimate-job", "fixture-job"]
        }
        self.closed = False

    def ping(self) -> bool:
        return True

    def scan_iter(self):
        return iter(key.encode() for key in self.keys)

    def lrange(self, queue, _start, _end):
        return [value.encode() for value in self.queues.get(queue, [])]

    def delete(self, *keys) -> int:
        removed = 0
        for key in keys:
            if key in self.keys:
                self.keys.remove(key)
                removed += 1
        return removed

    def exists(self, key) -> bool:
        return key in self.keys

    def lrem(self, queue, _count, payload) -> int:
        values = self.queues.get(queue, [])
        removed = values.count(payload)
        self.queues[queue] = [value for value in values if value != payload]
        return removed

    def lpos(self, queue, payload):
        try:
            return self.queues.get(queue, []).index(payload)
        except ValueError:
            return None

    def close(self) -> None:
        self.closed = True


def _patch_s3(monkeypatch, client: FakeS3) -> None:
    monkeypatch.setattr(guard, "_assert_local_object_storage", lambda: None)
    monkeypatch.setattr(
        guard,
        "get_settings",
        lambda: SimpleNamespace(s3_bucket=guard.DEVELOPMENT_S3_BUCKET),
    )
    monkeypatch.setattr(guard, "s3_client", lambda: client)


def test_janitor_requires_exact_development_database_identity(monkeypatch) -> None:
    local_url = (
        "postgresql+psycopg://anime_streaming_dev:secret@127.0.0.1:5433/"
        "anime_streaming_dev"
    )
    monkeypatch.setattr(
        guard,
        "get_settings",
        lambda: SimpleNamespace(app_env="development", database_url=local_url),
    )
    guard._assert_local_development(
        FakeDatabaseSession("anime_streaming_dev", "anime_streaming_dev")
    )

    wrong_url = local_url.replace("/anime_streaming_dev", "/some_other_database")
    monkeypatch.setattr(
        guard,
        "get_settings",
        lambda: SimpleNamespace(app_env="development", database_url=wrong_url),
    )
    with pytest.raises(SystemExit, match="exact"):
        guard._assert_local_development(
            FakeDatabaseSession("some_other_database", "anime_streaming_dev")
        )


def test_janitor_requires_loopback_canonical_object_storage(monkeypatch) -> None:
    monkeypatch.setattr(
        guard,
        "get_settings",
        lambda: SimpleNamespace(
            s3_endpoint="http://127.0.0.1:9100",
            s3_bucket=guard.DEVELOPMENT_S3_BUCKET,
        ),
    )
    guard._assert_local_object_storage()

    monkeypatch.setattr(
        guard,
        "get_settings",
        lambda: SimpleNamespace(
            s3_endpoint="https://objects.example.com",
            s3_bucket=guard.DEVELOPMENT_S3_BUCKET,
        ),
    )
    with pytest.raises(SystemExit, match="non-local"):
        guard._assert_local_object_storage()


def test_s3_delete_uses_exact_manifest_chunks_and_verifies_absence(monkeypatch) -> None:
    keys = {f"processed/playback-test/run/{index}" for index in range(1001)}
    client = FakeS3(set(keys))
    _patch_s3(monkeypatch, client)
    manifest = [{"key": key} for key in sorted(keys)]

    removed = guard.delete_s3_fixture_manifest(manifest, [])

    assert removed == 1001
    assert [len(call) for call in client.delete_calls] == [1000, 1]
    assert client.keys == set()


def test_s3_delete_refuses_unapproved_keys_and_surfaces_api_errors(monkeypatch) -> None:
    client = FakeS3({"legitimate/movie.mp4"})
    _patch_s3(monkeypatch, client)
    with pytest.raises(SystemExit, match="outside approved"):
        guard.delete_s3_fixture_manifest([{"key": "legitimate/movie.mp4"}], [])

    failing = FakeS3({"gallery/playback-test/failure.jpg"}, errors=True)
    _patch_s3(monkeypatch, failing)
    with pytest.raises(RuntimeError, match="refused"):
        guard.delete_s3_fixture_manifest(
            [{"key": "gallery/playback-test/failure.jpg"}],
            [],
        )


def test_redis_delete_removes_only_manifested_keys_and_payloads(monkeypatch) -> None:
    client = FakeRedis()
    monkeypatch.setattr(guard, "_assert_local_redis", lambda: None)
    monkeypatch.setattr(
        guard,
        "get_settings",
        lambda: SimpleNamespace(redis_url="redis://127.0.0.1:6379/0"),
    )
    monkeypatch.setattr(guard.redis.Redis, "from_url", lambda *_args, **_kwargs: client)
    report = {
        "redis_rate_limit_keys": [{"key": "community:review:fixture-profile"}],
        "redis_queue_payloads": [
            {"key": guard.SCENE_QUEUE, "payload": "fixture-job", "occurrences": "2"}
        ],
        "redis_orphan_queue_payloads": [],
    }
    records = {
        "redis_rate_identifiers": ["fixture-profile"],
        "redis_processing_payloads": [],
        "redis_scene_payloads": ["fixture-job"],
    }

    removed = guard.delete_redis_fixture_manifest(EmptyJobDatabase(), report, records)

    assert removed == 3
    assert client.keys == {"legitimate:key"}
    assert client.queues[guard.SCENE_QUEUE] == ["legitimate-job"]
    assert client.closed


def test_redis_audit_reports_without_mutating(monkeypatch) -> None:
    client = FakeRedis()
    monkeypatch.setattr(guard, "_assert_local_redis", lambda: None)
    monkeypatch.setattr(
        guard,
        "get_settings",
        lambda: SimpleNamespace(redis_url="redis://127.0.0.1:6379/0"),
    )
    monkeypatch.setattr(guard.redis.Redis, "from_url", lambda *_args, **_kwargs: client)
    records = {
        "redis_rate_identifiers": ["fixture-profile"],
        "redis_processing_payloads": [],
        "redis_scene_payloads": ["fixture-job"],
    }

    report = guard.collect_redis_fixture_leaks(EmptyJobDatabase(), records)

    assert report["redis_rate_limit_keys"] == [
        {"key": "community:review:fixture-profile"}
    ]
    assert report["redis_queue_payloads"] == [
        {
            "key": guard.SCENE_QUEUE,
            "payload": "fixture-job",
            "occurrences": "2",
        }
    ]
    assert report["redis_orphan_queue_payloads"] == []
    assert client.keys == {"community:review:fixture-profile", "legitimate:key"}
    assert client.queues[guard.SCENE_QUEUE] == [
        "fixture-job",
        "legitimate-job",
        "fixture-job",
    ]


def test_redis_delete_refuses_unapproved_manifest_entries(monkeypatch) -> None:
    client = FakeRedis()
    monkeypatch.setattr(guard, "_assert_local_redis", lambda: None)
    monkeypatch.setattr(
        guard,
        "get_settings",
        lambda: SimpleNamespace(redis_url="redis://127.0.0.1:6379/0"),
    )
    monkeypatch.setattr(guard.redis.Redis, "from_url", lambda *_args, **_kwargs: client)
    report = {
        "redis_rate_limit_keys": [{"key": "community:review:someone-else"}],
        "redis_queue_payloads": [],
        "redis_orphan_queue_payloads": [],
    }
    records = {
        "redis_rate_identifiers": ["fixture-profile"],
        "redis_processing_payloads": [],
        "redis_scene_payloads": [],
    }

    with pytest.raises(SystemExit, match="unapproved"):
        guard.delete_redis_fixture_manifest(EmptyJobDatabase(), report, records)

    assert client.keys == {"community:review:fixture-profile", "legitimate:key"}
    assert client.closed


def test_redis_audit_and_apply_remove_exact_orphan_job_uuid(monkeypatch) -> None:
    orphan_id = "0d8f576c-83ea-4f03-bc27-57590339a0f8"
    client = FakeRedis()
    client.queues[guard.SCENE_QUEUE] = [orphan_id, "legitimate-job", orphan_id]
    monkeypatch.setattr(guard, "_assert_local_redis", lambda: None)
    monkeypatch.setattr(
        guard,
        "get_settings",
        lambda: SimpleNamespace(redis_url="redis://127.0.0.1:6379/0"),
    )
    monkeypatch.setattr(guard.redis.Redis, "from_url", lambda *_args, **_kwargs: client)
    records = {
        "redis_rate_identifiers": [],
        "redis_processing_payloads": [],
        "redis_scene_payloads": [],
    }
    database = EmptyJobDatabase()

    report = guard.collect_redis_fixture_leaks(database, records)

    assert report["redis_orphan_queue_payloads"] == [
        {
            "key": guard.SCENE_QUEUE,
            "payload": orphan_id,
            "occurrences": "2",
        }
    ]
    removed = guard.delete_redis_fixture_manifest(database, report, records)
    assert removed == 2
    assert client.queues[guard.SCENE_QUEUE] == ["legitimate-job"]
