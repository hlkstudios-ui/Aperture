from __future__ import annotations

import atexit
import os
import sys
from pathlib import Path
from typing import Any

import boto3
import pytest
import redis
from alembic import command
from alembic.config import Config as AlembicConfig
from botocore.config import Config as BotoConfig
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from app.config import Settings
from test_support.resource_isolation import (
    TestResourcePlan,
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

API_ROOT = Path(__file__).resolve().parents[1]
REDIS_OWNER_KEY = "aperture:pytest:resource-owner"
REDIS_RESOURCE_NAME = "redis-db-15"
S3_OWNER_KEY = ".aperture-pytest-owner.json"
STALE_RESOURCE_MIN_AGE_SECONDS = 5 * 60
DELETE_BATCH_SIZE = 1000


class TestResourceSandbox:
    """Own all mutable infrastructure used by one pytest process."""

    def __init__(self, source: Settings, plan: TestResourcePlan) -> None:
        self.source = source
        self.plan = plan
        self.database_created = False
        self.bucket_created = False
        self.redis_owned = False
        self.closed = False
        self.redis_client: redis.Redis | None = None
        self.s3: Any = None
        self.database_owner = new_resource_owner(
            resource_kind="postgresql-database",
            resource_name=plan.database_name,
            run_token=plan.run_token,
        )
        self.redis_owner = new_resource_owner(
            resource_kind="redis-database",
            resource_name=REDIS_RESOURCE_NAME,
            run_token=plan.run_token,
        )
        self.bucket_owner = new_resource_owner(
            resource_kind="s3-bucket",
            resource_name=plan.s3_bucket,
            run_token=plan.run_token,
        )

    def start(self) -> None:
        try:
            self._create_database()
            self._claim_redis_database()
            self._create_bucket()
            self._install_test_environment()
            self._run_migrations()
            self._verify_application_bindings()
        except BaseException:
            try:
                self.close()
            except RuntimeError:
                pass
            raise

    def close(self) -> None:
        if self.closed:
            return
        errors: list[str] = []
        for resource, cleanup in (
            ("application database connections", self._dispose_application_engine),
            ("S3 bucket", self._delete_bucket),
            ("Redis database", self._release_redis_database),
            ("PostgreSQL database", self._drop_database),
        ):
            try:
                cleanup()
            except Exception as exc:
                errors.append(f"{resource} ({type(exc).__name__})")
        self.closed = not (self.database_created or self.bucket_created or self.redis_owned)
        if errors:
            failed = ", ".join(errors)
            raise RuntimeError(f"Could not completely tear down isolated resources: {failed}")

    def _create_database(self) -> None:
        assert_disposable_database_name(self.plan.database_name)
        admin_engine = create_engine(
            self.plan.admin_database_url,
            isolation_level="AUTOCOMMIT",
            poolclass=NullPool,
        )
        try:
            with admin_engine.connect() as connection:
                self._reap_stale_databases(connection)
                connection.exec_driver_sql(f'CREATE DATABASE "{self.plan.database_name}"')
                self.database_created = True
                owner = self.database_owner.to_json().replace("'", "''")
                connection.exec_driver_sql(
                    f'COMMENT ON DATABASE "{self.plan.database_name}" IS \'{owner}\''
                )
        finally:
            admin_engine.dispose()

    def _reap_stale_databases(self, connection: Any) -> None:
        rows = connection.exec_driver_sql(
            "SELECT datname, shobj_description(oid, 'pg_database') "
            "FROM pg_database WHERE left(datname, %s) = %s",
            (len("aperture_pytest_"), "aperture_pytest_"),
        )
        for database_name, metadata in rows:
            try:
                assert_disposable_database_name(database_name)
                owner = parse_resource_owner(
                    metadata or "",
                    resource_kind="postgresql-database",
                    resource_name=database_name,
                )
            except UnsafeTestResourceError:
                continue
            if owner.run_token != database_name.removeprefix("aperture_pytest_"):
                continue
            if not is_reapable_owner(
                owner,
                minimum_age_seconds=STALE_RESOURCE_MIN_AGE_SECONDS,
            ):
                continue
            active_connections = connection.exec_driver_sql(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            ).scalar_one()
            if active_connections:
                continue
            connection.exec_driver_sql(f'DROP DATABASE "{database_name}"')

    def _claim_redis_database(self) -> None:
        assert_isolated_redis_url(self.plan.redis_url)
        client = redis.Redis.from_url(
            self.plan.redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()
        owner_payload = self.redis_owner.to_json().encode()
        keys = self._redis_keys(client)
        existing_payload = client.get(REDIS_OWNER_KEY) if REDIS_OWNER_KEY.encode() in keys else None
        if existing_payload is None and keys:
            client.close()
            raise UnsafeTestResourceError(
                "Redis database 15 contains keys without valid pytest ownership; refusing cleanup"
            )
        if existing_payload is not None:
            try:
                existing_owner = parse_resource_owner(
                    existing_payload,
                    resource_kind="redis-database",
                    resource_name=REDIS_RESOURCE_NAME,
                )
            except UnsafeTestResourceError:
                client.close()
                raise
            if not is_proven_dead_local_owner(existing_owner):
                client.close()
                raise UnsafeTestResourceError(
                    "Redis database 15 is owned by an active or non-local pytest process"
                )
            claimed = client.eval(
                "if redis.call('get', KEYS[1]) == ARGV[1] then "
                "redis.call('set', KEYS[1], ARGV[2]); return 1 else return 0 end",
                1,
                REDIS_OWNER_KEY,
                existing_payload,
                owner_payload,
            )
            if claimed != 1:
                client.close()
                raise UnsafeTestResourceError(
                    "Redis stale-owner reclamation lost its ownership race"
                )
            self.redis_client = client
            self.redis_owned = True
            self._delete_exact_redis_keys(
                client,
                keys - {REDIS_OWNER_KEY.encode()},
                owner_payload=owner_payload,
            )
            if self._redis_keys(client) != {REDIS_OWNER_KEY.encode()}:
                raise UnsafeTestResourceError(
                    "Redis stale-owner reclamation could not verify an owned empty database"
                )
            return
        claimed = client.set(REDIS_OWNER_KEY, owner_payload, nx=True)
        if not claimed:
            client.close()
            raise UnsafeTestResourceError(
                "Redis database 15 is already owned by another pytest process; "
                "refusing to let concurrent test runs share mutable state"
            )
        if client.get(REDIS_OWNER_KEY) != owner_payload:
            client.close()
            raise UnsafeTestResourceError("Redis ownership verification failed")
        self.redis_client = client
        self.redis_owned = True

    def _create_bucket(self) -> None:
        assert_disposable_bucket_name(self.plan.s3_bucket)
        self.s3 = boto3.client(
            "s3",
            endpoint_url=str(self.source.s3_endpoint),
            region_name=self.source.s3_region,
            aws_access_key_id=self.source.s3_access_key,
            aws_secret_access_key=self.source.s3_secret_key,
            config=BotoConfig(
                s3={"addressing_style": "path"},
                connect_timeout=2,
                read_timeout=3,
                retries={"max_attempts": 1, "mode": "standard"},
            ),
        )
        self._reap_stale_buckets()
        parameters: dict[str, Any] = {"Bucket": self.plan.s3_bucket}
        if self.source.s3_region != "us-east-1":
            parameters["CreateBucketConfiguration"] = {
                "LocationConstraint": self.source.s3_region
            }
        self.s3.create_bucket(**parameters)
        self.bucket_created = True
        self.s3.put_object(
            Bucket=self.plan.s3_bucket,
            Key=S3_OWNER_KEY,
            Body=self.bucket_owner.to_json().encode(),
            ContentType="application/json",
        )

    def _reap_stale_buckets(self) -> None:
        for item in self.s3.list_buckets().get("Buckets", []):
            bucket_name = item.get("Name", "")
            if not bucket_name.startswith("aperture-pytest-"):
                continue
            try:
                assert_disposable_bucket_name(bucket_name)
                response = self.s3.get_object(Bucket=bucket_name, Key=S3_OWNER_KEY)
                payload = response["Body"].read()
                owner = parse_resource_owner(
                    payload,
                    resource_kind="s3-bucket",
                    resource_name=bucket_name,
                )
            except Exception:
                # Missing/malformed metadata and inaccessible buckets are never inferred safe.
                continue
            if owner.run_token != bucket_name.removeprefix("aperture-pytest-"):
                continue
            if not is_reapable_owner(
                owner,
                minimum_age_seconds=STALE_RESOURCE_MIN_AGE_SECONDS,
            ):
                continue
            current_payload = self.s3.get_object(Bucket=bucket_name, Key=S3_OWNER_KEY)[
                "Body"
            ].read()
            if current_payload != payload:
                continue
            self._empty_and_delete_bucket(bucket_name)

    def _install_test_environment(self) -> None:
        if "app.db" in sys.modules:
            raise UnsafeTestResourceError(
                "app.db was imported before pytest installed isolated resource URLs"
            )
        os.environ.update(
            {
                "APP_ENV": "test",
                "DATABASE_URL": self.plan.database_url,
                "REDIS_URL": self.plan.redis_url,
                "S3_ENDPOINT": str(self.source.s3_endpoint),
                "S3_PUBLIC_ENDPOINT": str(self.source.s3_endpoint),
                "S3_BUCKET": self.plan.s3_bucket,
                "BILLING_PROVIDER": "disabled",
                "STUDIO_DEV_AUTO_LOGIN": "false",
                "PLATFORM_CONTROL_PLANE_ENABLED": "true",
                "APERTURE_PYTEST_RESOURCE_TOKEN": self.plan.run_token,
            }
        )
        from app.config import get_settings

        get_settings.cache_clear()

    def _run_migrations(self) -> None:
        configuration = AlembicConfig(str(API_ROOT / "alembic.ini"))
        configuration.set_main_option("script_location", str(API_ROOT / "migrations"))
        command.upgrade(configuration, "head")

    def _verify_application_bindings(self) -> None:
        from app.config import get_settings
        from app.db import engine

        settings = get_settings()
        expected = {
            "APP_ENV": (settings.app_env, "test"),
            "DATABASE_URL": (settings.database_url, self.plan.database_url),
            "REDIS_URL": (settings.redis_url, self.plan.redis_url),
            "S3_BUCKET": (settings.s3_bucket, self.plan.s3_bucket),
            "BILLING_PROVIDER": (settings.billing_provider, "disabled"),
            "STUDIO_DEV_AUTO_LOGIN": (settings.studio_dev_auto_login, False),
            "PLATFORM_CONTROL_PLANE_ENABLED": (
                settings.platform_control_plane_enabled,
                True,
            ),
        }
        mismatched = [name for name, values in expected.items() if values[0] != values[1]]
        if mismatched or engine.url.database != self.plan.database_name:
            names = ", ".join(mismatched or ["SQLAlchemy engine"])
            raise UnsafeTestResourceError(
                f"Application resource isolation verification failed for: {names}"
            )

    def _dispose_application_engine(self) -> None:
        database_module = sys.modules.get("app.db")
        engine = getattr(database_module, "engine", None)
        if engine is not None:
            engine.dispose()

    def _delete_bucket(self) -> None:
        if not self.bucket_created or self.s3 is None:
            return
        assert_disposable_bucket_name(self.plan.s3_bucket)
        response = self.s3.get_object(Bucket=self.plan.s3_bucket, Key=S3_OWNER_KEY)
        if response["Body"].read() != self.bucket_owner.to_json().encode():
            raise RuntimeError("S3 test bucket ownership changed before teardown")
        self._empty_and_delete_bucket(self.plan.s3_bucket)
        self.bucket_created = False

    def _empty_and_delete_bucket(self, bucket_name: str) -> None:
        assert_disposable_bucket_name(bucket_name)
        self._abort_multipart_uploads(bucket_name)
        self._delete_object_versions(bucket_name)
        self._delete_current_objects(bucket_name)
        if self.s3.list_objects_v2(Bucket=bucket_name, MaxKeys=1).get("Contents"):
            raise RuntimeError(f"S3 bucket {bucket_name} was not emptied")
        if self.s3.list_object_versions(Bucket=bucket_name, MaxKeys=1).get(
            "Versions"
        ) or self.s3.list_object_versions(Bucket=bucket_name, MaxKeys=1).get("DeleteMarkers"):
            raise RuntimeError(f"S3 bucket {bucket_name} still has object versions")
        if self.s3.list_multipart_uploads(Bucket=bucket_name, MaxUploads=1).get("Uploads"):
            raise RuntimeError(f"S3 bucket {bucket_name} still has multipart uploads")
        self.s3.delete_bucket(Bucket=bucket_name)

    def _abort_multipart_uploads(self, bucket_name: str) -> None:
        while True:
            response = self.s3.list_multipart_uploads(Bucket=bucket_name)
            uploads = response.get("Uploads", [])
            for upload in uploads:
                self.s3.abort_multipart_upload(
                    Bucket=bucket_name,
                    Key=upload["Key"],
                    UploadId=upload["UploadId"],
                )
            if not uploads:
                return

    def _delete_object_versions(self, bucket_name: str) -> None:
        while True:
            response = self.s3.list_object_versions(Bucket=bucket_name)
            objects = [
                {"Key": item["Key"], "VersionId": item["VersionId"]}
                for item in [*response.get("Versions", []), *response.get("DeleteMarkers", [])]
            ]
            if not objects:
                return
            self._delete_s3_manifest(bucket_name, objects)

    def _delete_current_objects(self, bucket_name: str) -> None:
        while True:
            response = self.s3.list_objects_v2(Bucket=bucket_name)
            objects = [{"Key": item["Key"]} for item in response.get("Contents", [])]
            if not objects:
                return
            self._delete_s3_manifest(bucket_name, objects)

    def _delete_s3_manifest(self, bucket_name: str, objects: list[dict[str, str]]) -> None:
        for start in range(0, len(objects), DELETE_BATCH_SIZE):
            chunk = objects[start : start + DELETE_BATCH_SIZE]
            response = self.s3.delete_objects(
                Bucket=bucket_name,
                Delete={"Objects": chunk, "Quiet": True},
            )
            if response.get("Errors"):
                raise RuntimeError(f"S3 object deletion failed for {bucket_name}")

    @staticmethod
    def _redis_keys(client: redis.Redis) -> set[bytes]:
        return set(client.scan_iter())

    @staticmethod
    def _delete_exact_redis_keys(
        client: redis.Redis,
        keys: set[bytes],
        *,
        owner_payload: bytes,
    ) -> None:
        ordered = sorted(keys)
        for start in range(0, len(ordered), 500):
            chunk = ordered[start : start + 500]
            if chunk:
                deleted = client.eval(
                    "if redis.call('get', KEYS[1]) ~= ARGV[1] then return -1 end "
                    "local removed = 0; for i = 2, #KEYS do "
                    "removed = removed + redis.call('del', KEYS[i]); end; return removed",
                    len(chunk) + 1,
                    REDIS_OWNER_KEY,
                    *chunk,
                    owner_payload,
                )
                if deleted == -1:
                    raise UnsafeTestResourceError(
                        "Redis ownership changed during exact-key cleanup"
                    )
        if any(client.exists(key) for key in ordered):
            raise UnsafeTestResourceError("Redis exact-key cleanup could not verify deletion")

    def _release_redis_database(self) -> None:
        if not self.redis_owned or self.redis_client is None:
            return
        assert_isolated_redis_url(self.plan.redis_url)
        try:
            owner_payload = self.redis_owner.to_json().encode()
            owner = self.redis_client.get(REDIS_OWNER_KEY)
            if owner != owner_payload:
                raise RuntimeError(
                    "Redis test ownership changed before teardown; refusing cleanup"
                )
            keys = self._redis_keys(self.redis_client)
            if REDIS_OWNER_KEY.encode() not in keys:
                raise RuntimeError("Redis owner key disappeared before teardown")
            self._delete_exact_redis_keys(
                self.redis_client,
                keys - {REDIS_OWNER_KEY.encode()},
                owner_payload=owner_payload,
            )
            deleted = self.redis_client.eval(
                "if redis.call('get', KEYS[1]) == ARGV[1] then "
                "return redis.call('del', KEYS[1]) else return 0 end",
                1,
                REDIS_OWNER_KEY,
                owner_payload,
            )
            if deleted != 1 or self._redis_keys(self.redis_client):
                raise RuntimeError("Redis exact-key teardown could not verify an empty database")
            self.redis_owned = False
        finally:
            self.redis_client.close()

    def _drop_database(self) -> None:
        if not self.database_created:
            return
        assert_disposable_database_name(self.plan.database_name)
        admin_engine = create_engine(
            self.plan.admin_database_url,
            isolation_level="AUTOCOMMIT",
            poolclass=NullPool,
        )
        try:
            with admin_engine.connect() as connection:
                metadata = connection.exec_driver_sql(
                    "SELECT shobj_description(oid, 'pg_database') "
                    "FROM pg_database WHERE datname = %s",
                    (self.plan.database_name,),
                ).scalar_one_or_none()
                if metadata != self.database_owner.to_json():
                    raise RuntimeError(
                        "PostgreSQL test database ownership changed before teardown"
                    )
                connection.exec_driver_sql(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (self.plan.database_name,),
                )
                connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{self.plan.database_name}"')
            self.database_created = False
        finally:
            admin_engine.dispose()


def _start_test_sandbox() -> TestResourceSandbox:
    os.environ["STUDIO_DEV_AUTO_LOGIN"] = "false"
    try:
        source = Settings()
        plan = build_test_resource_plan(
            app_env=source.app_env,
            database_url=source.database_url,
            redis_url=source.redis_url,
            s3_endpoint=str(source.s3_endpoint),
        )
    except BaseException as exc:
        raise pytest.UsageError(
            "Refusing to start API tests without verified local/CI resource isolation. "
            f"Reason: {type(exc).__name__}."
        ) from None
    sandbox = TestResourceSandbox(source, plan)
    try:
        sandbox.start()
    except BaseException as exc:
        message = (
            "Unable to create isolated API test resources. "
            f"PostgreSQL server: {safe_url(plan.admin_database_url)}; "
            "Redis database: 15; S3: generated local bucket. "
            f"Reason: {type(exc).__name__}: {exc}. "
            "Tests stopped before application imports."
        )
        raise pytest.UsageError(message) from None
    return sandbox


_SANDBOX = _start_test_sandbox()
atexit.register(_SANDBOX.close)


def pytest_report_header() -> str:
    return (
        f"isolated resources: PostgreSQL={_SANDBOX.plan.database_name}, "
        f"Redis=15, S3={_SANDBOX.plan.s3_bucket}"
    )


def pytest_sessionfinish() -> None:
    _SANDBOX.close()
