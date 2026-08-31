"""Audit and remove confirmed synthetic test data from a local development stack.

The default mode is read-only. Deletion requires both ``--apply`` and the exact
confirmation phrase. Tests are prevented from reaching this database by the
separate test-resource isolation bootstrap; this script is the one-time janitor
and a reusable integrity check.
"""

# ruff: noqa: E402 -- direct script execution bootstraps the API import root below.

from __future__ import annotations

import argparse
import ipaddress
import json
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import redis
from botocore.exceptions import ClientError
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.catalog_models import (
    Character,
    Credit,
    Genre,
    Movie,
    Person,
    movie_genres,
    series_genres,
)
from app.config import get_settings
from app.curation_models import (
    Collection,
    CollectionItem,
    Journey,
    JourneyChapter,
    JourneyItem,
)
from app.db import SessionLocal
from app.models import (
    Admin,
    AggregatedMetric,
    AuditLog,
    BillingWebhookEvent,
    MediaAsset,
    PlaybackSource,
    ProcessingJob,
    Profile,
    User,
)
from app.object_storage import s3_client
from app.processing_queue import PROCESSING_QUEUE
from app.scene_models import SceneCharacter, SceneIntelligenceJob, SceneIntelligenceVersion
from app.scene_queue import SCENE_QUEUE

CONFIRMATION = "delete-confirmed-development-test-fixtures"
DEVELOPMENT_DATABASE_NAME = "anime_streaming_dev"
DEVELOPMENT_S3_BUCKET = "anime-streaming-development"
DEVELOPMENT_REDIS_DATABASE = 0
DELETE_BATCH_SIZE = 1000
UUID_RE = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
USER_EMAIL_RE = (
    r"^((analytics|homepage-viewer|recommendations)-[0-9a-f]{10}|"
    r"viewer-([0-9a-f]{10}|[0-9a-f]{32})|"
    r"club-(host|member)-[0-9a-f]{10}|"
    r"review-(rate|author|reader)-[0-9a-f]{10}|"
    rf"playback-viewer-{UUID_RE})@example[.]com$"
)
ADMIN_EMAIL_RE = (
    r"^((analytics-admin|club-admin|review-admin|curation|recommendation-admin)-"
    rf"[0-9a-f]{{10}}|playback-admin-{UUID_RE})@example[.]com$"
)
PERSON_NAME_RE = rf"^Playback (Actor|Director) {UUID_RE}$"
CHARACTER_NAME_RE = rf"^Playback Character {UUID_RE}$"
BILLING_EVENT_RE = r"^evt_(in_(paid|failed)|subscription)_[0-9a-f]{32}$"
ORPHAN_TEST_AUDIT_LOG_IDS = tuple(
    UUID(value)
    for value in (
        "fe9e12d3-e9b7-45c8-a134-bb7a389c9856",
        "ec3e3844-958a-4c65-bb3f-5c89ab4e1acf",
        "3409b94b-35bf-47f4-8fa7-2cd13c0d9c54",
        "46023397-17d5-41a2-bd7c-e17d83c450d8",
        "29c34df2-b5c9-4320-aad2-d1623ed1827a",
        "270a236a-d371-462c-a7f2-cda13d91bef8",
        "6982e25a-de6d-4764-b469-4da475f0aba7",
    )
)
TEST_AGGREGATE_IDS = tuple(
    UUID(value)
    for value in (
        "70906f12-d906-4d88-9db1-00581ed1292d",
        "44cddca1-fa95-47f7-9dcf-e12cfff0153d",
        "d985af82-30fe-4709-b7b0-6988893256b8",
    )
)
RATE_LIMIT_PREFIXES = (
    "admin-login:",
    "analytics:",
    "ask-movie:",
    "clubs:",
    "community:",
    "customer-login:",
    "party:",
    "password-reset:",
)
TESTCLIENT_RATE_LIMIT_KEYS = frozenset(
    {
        "oauth-start:testclient",
        "password-reset-confirm:testclient",
        "register:testclient",
    }
)


def _ids(records: Iterable[object]) -> list:
    return [record.id for record in records]


def _describe(records: Iterable[object], *fields: str) -> list[dict[str, str | None]]:
    return [
        {
            "id": str(record.id),
            **{
                field: str(getattr(record, field)) if getattr(record, field) is not None else None
                for field in fields
            },
        }
        for record in records
    ]


def collect_fixture_leaks(
    db: Session,
) -> tuple[dict[str, list[dict[str, str | None]]], dict[str, list]]:
    users = list(db.scalars(select(User).where(User.email.op("~")(USER_EMAIL_RE))))
    admins = list(db.scalars(select(Admin).where(Admin.email.op("~")(ADMIN_EMAIL_RE))))
    user_ids = _ids(users)
    admin_ids = _ids(admins)
    profile_ids = list(db.scalars(select(Profile.id).where(Profile.user_id.in_(user_ids))))
    assets = list(
        db.scalars(
            select(MediaAsset).where(
                MediaAsset.created_by_admin_id.in_(admin_ids),
                or_(
                    MediaAsset.original_filename.ilike("%fixture%"),
                    MediaAsset.original_filename == "club.mp4",
                    MediaAsset.storage_key.op("~")(
                        rf"^(source|processed)/([0-9a-f]{{10}}|{UUID_RE})(/|[.])"
                    ),
                ),
            )
        )
    )
    movies = list(
        db.scalars(
            select(Movie).where(
                Movie.slug.op("~")(r"^club-film-[0-9a-f]{10}$"),
                Movie.title == func.concat("Club Film ", func.substring(Movie.slug, 11)),
                Movie.short_description == "Club fixture.",
                Movie.metadata_provider.is_(None),
                Movie.external_id.is_(None),
            )
        )
    )
    movie_ids = _ids(movies)
    processing_job_ids = list(
        db.scalars(select(ProcessingJob.id).where(ProcessingJob.asset_id.in_(_ids(assets))))
    )
    scene_job_ids = list(
        db.scalars(
            select(SceneIntelligenceJob.id)
            .join(
                SceneIntelligenceVersion,
                SceneIntelligenceJob.version_id == SceneIntelligenceVersion.id,
            )
            .join(
                PlaybackSource,
                SceneIntelligenceVersion.playback_source_id == PlaybackSource.id,
            )
            .where(PlaybackSource.movie_id.in_(movie_ids))
        )
    )
    people = list(
        db.scalars(
            select(Person).where(
                Person.name.op("~")(PERSON_NAME_RE),
                Person.slug == func.lower(func.replace(Person.name, " ", "-")),
                ~select(Credit.id).where(Credit.person_id == Person.id).exists(),
            )
        )
    )
    characters = list(
        db.scalars(
            select(Character).where(
                Character.name.op("~")(CHARACTER_NAME_RE),
                Character.slug == func.lower(func.replace(Character.name, " ", "-")),
                ~select(Credit.id).where(Credit.character_id == Character.id).exists(),
                ~select(SceneCharacter.id)
                .where(SceneCharacter.character_id == Character.id)
                .exists(),
            )
        )
    )
    genres = list(
        db.scalars(
            select(Genre).where(
                Genre.slug.op("~")(r"^(drama|comedy)-[0-9a-f]{10}$"),
                Genre.name
                == func.concat(
                    func.initcap(func.split_part(Genre.slug, "-", 1)),
                    " ",
                    func.split_part(Genre.slug, "-", 2),
                ),
                ~select(movie_genres.c.genre_id)
                .where(movie_genres.c.genre_id == Genre.id)
                .exists(),
                ~select(series_genres.c.genre_id)
                .where(series_genres.c.genre_id == Genre.id)
                .exists(),
            )
        )
    )
    collections = list(
        db.scalars(
            select(Collection).where(
                Collection.slug.op("~")(r"^movement-[0-9a-f]{10}$"),
                Collection.title == "A film movement",
                Collection.description == "An ordered collection",
                ~select(CollectionItem.id)
                .where(CollectionItem.collection_id == Collection.id)
                .exists(),
            )
        )
    )
    journeys = list(
        db.scalars(
            select(Journey).where(
                Journey.slug.op("~")(r"^journey-[0-9a-f]{10}$"),
                Journey.title == "A film journey",
                Journey.description == "Learn in sequence",
                ~select(JourneyItem.id)
                .join(JourneyChapter, JourneyItem.chapter_id == JourneyChapter.id)
                .where(JourneyChapter.journey_id == Journey.id)
                .exists(),
            )
        )
    )
    linked_logs = list(db.scalars(select(AuditLog).where(AuditLog.actor_id.in_(admin_ids))))
    orphan_logs = list(
        db.scalars(select(AuditLog).where(AuditLog.id.in_(ORPHAN_TEST_AUDIT_LOG_IDS)))
    )
    audit_logs = list({record.id: record for record in [*linked_logs, *orphan_logs]}.values())
    billing_events = list(
        db.scalars(
            select(BillingWebhookEvent).where(
                BillingWebhookEvent.external_event_id.op("~")(BILLING_EVENT_RE)
            )
        )
    )
    aggregates = list(
        db.scalars(select(AggregatedMetric).where(AggregatedMetric.id.in_(TEST_AGGREGATE_IDS)))
    )
    report = {
        "users": _describe(users, "email"),
        "admins": _describe(admins, "email"),
        "media_assets": _describe(assets, "original_filename", "storage_key"),
        "movies": _describe(movies, "title", "slug"),
        "people": _describe(people, "name", "slug"),
        "characters": _describe(characters, "name", "slug"),
        "genres": _describe(genres, "name", "slug"),
        "collections": _describe(collections, "title", "slug"),
        "journeys": _describe(journeys, "title", "slug"),
        "audit_logs": _describe(audit_logs, "action", "outcome"),
        "billing_webhook_events": _describe(billing_events, "external_event_id"),
        "aggregated_metrics": _describe(aggregates, "event_type"),
    }
    records = {
        "users": _ids(users),
        "admins": admin_ids,
        "media_assets": _ids(assets),
        "movies": _ids(movies),
        "people": _ids(people),
        "characters": _ids(characters),
        "genres": _ids(genres),
        "collections": _ids(collections),
        "journeys": _ids(journeys),
        "audit_logs": _ids(audit_logs),
        "billing_webhook_events": _ids(billing_events),
        "aggregated_metrics": _ids(aggregates),
        "redis_rate_identifiers": [
            *(str(record.id) for record in users),
            *(record.email for record in users),
            *(str(record.id) for record in admins),
            *(record.email for record in admins),
            *(str(profile_id) for profile_id in profile_ids),
        ],
        "redis_processing_payloads": [str(job_id) for job_id in processing_job_ids],
        "redis_scene_payloads": [str(job_id) for job_id in scene_job_ids],
    }
    return report, records


def _is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    normalized = host.rstrip(".").casefold()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _assert_local_development(db: Session) -> None:
    settings = get_settings()
    url = make_url(settings.database_url)
    if settings.app_env != "development":
        raise SystemExit("Fixture cleanup is restricted to APP_ENV=development")
    if not _is_loopback_host(url.host):
        raise SystemExit("Fixture cleanup refuses a non-local database")
    if url.database != DEVELOPMENT_DATABASE_NAME:
        raise SystemExit(
            f"Fixture cleanup requires the exact {DEVELOPMENT_DATABASE_NAME!r} database"
        )
    current_database, current_user = db.execute(
        text("SELECT current_database(), current_user")
    ).one()
    if current_database != DEVELOPMENT_DATABASE_NAME or current_user != url.username:
        raise SystemExit("Connected PostgreSQL identity does not match DATABASE_URL")


def _assert_local_object_storage() -> None:
    settings = get_settings()
    parsed = urlsplit(str(settings.s3_endpoint))
    if (
        parsed.scheme not in {"http", "https"}
        or not _is_loopback_host(parsed.hostname)
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise SystemExit("Fixture cleanup refuses a non-local S3 endpoint")
    if settings.s3_bucket != DEVELOPMENT_S3_BUCKET:
        raise SystemExit(
            f"Fixture cleanup requires the exact {DEVELOPMENT_S3_BUCKET!r} S3 bucket"
        )


def _assert_local_redis() -> None:
    settings = get_settings()
    parsed = urlsplit(settings.redis_url)
    try:
        database = int(parsed.path.removeprefix("/") or "0")
    except ValueError as exc:
        raise SystemExit("Fixture cleanup requires a numeric Redis database") from exc
    if (
        parsed.scheme not in {"redis", "rediss"}
        or not _is_loopback_host(parsed.hostname)
        or parsed.fragment
        or database != DEVELOPMENT_REDIS_DATABASE
    ):
        raise SystemExit("Fixture cleanup requires local Redis database 0")


def _s3_key_exists(client: object, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise
    return True


def collect_s3_fixture_leaks(
    asset_rows: list[dict[str, str | None]],
) -> list[dict[str, str]]:
    _assert_local_object_storage()
    settings = get_settings()
    client = s3_client()
    client.head_bucket(Bucket=settings.s3_bucket)
    keys: set[str] = set()
    for row in asset_rows:
        storage_key = row.get("storage_key")
        if storage_key and _s3_key_exists(client, settings.s3_bucket, storage_key):
            keys.add(storage_key)
    for prefix in ("gallery/playback-test/", "processed/playback-test/"):
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=settings.s3_bucket, Prefix=prefix):
            keys.update(item["Key"] for item in page.get("Contents", []))
    return [{"key": key} for key in sorted(keys)]


def delete_s3_fixture_manifest(
    manifest: list[dict[str, str]],
    asset_rows: list[dict[str, str | None]],
) -> int:
    _assert_local_object_storage()
    settings = get_settings()
    client = s3_client()
    client.head_bucket(Bucket=settings.s3_bucket)
    exact_asset_keys = {
        row["storage_key"] for row in asset_rows if isinstance(row.get("storage_key"), str)
    }
    keys = [item["key"] for item in manifest]
    if len(keys) != len(set(keys)) or any(
        key not in exact_asset_keys
        and not key.startswith(("gallery/playback-test/", "processed/playback-test/"))
        for key in keys
    ):
        raise SystemExit("S3 fixture manifest contains a key outside approved exact fixtures")
    for start in range(0, len(keys), DELETE_BATCH_SIZE):
        chunk = keys[start : start + DELETE_BATCH_SIZE]
        if not chunk:
            continue
        response = client.delete_objects(
            Bucket=settings.s3_bucket,
            Delete={"Objects": [{"Key": key} for key in chunk], "Quiet": True},
        )
        errors = response.get("Errors", [])
        if errors:
            failed = ", ".join(str(item.get("Key", "<unknown>")) for item in errors)
            raise RuntimeError(f"S3 refused fixture object deletion for: {failed}")
    remaining = [
        key for key in keys if _s3_key_exists(client, settings.s3_bucket, key)
    ]
    if remaining:
        raise RuntimeError(f"S3 fixture deletion verification failed for {len(remaining)} keys")
    return len(keys)


def _fixture_rate_key(key: str, identifiers: set[str]) -> bool:
    if key in TESTCLIENT_RATE_LIMIT_KEYS:
        return True
    if not key.startswith(RATE_LIMIT_PREFIXES):
        return False
    return any(part in identifiers for part in key.split(":"))


def collect_redis_fixture_leaks(
    db: Session,
    records: dict[str, list],
) -> dict[str, list[dict[str, str]]]:
    _assert_local_redis()
    settings = get_settings()
    client = redis.Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    try:
        client.ping()
        identifiers = set(records["redis_rate_identifiers"])
        rate_keys: list[dict[str, str]] = []
        for raw_key in client.scan_iter():
            try:
                key = raw_key.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if _fixture_rate_key(key, identifiers):
                rate_keys.append({"key": key})
        desired_payloads = {
            PROCESSING_QUEUE: set(records["redis_processing_payloads"]),
            SCENE_QUEUE: set(records["redis_scene_payloads"]),
        }
        queue_payloads: list[dict[str, str]] = []
        orphan_queue_payloads: list[dict[str, str]] = []
        for queue, payloads in desired_payloads.items():
            current = client.lrange(queue, 0, -1)
            model = ProcessingJob if queue == PROCESSING_QUEUE else SceneIntelligenceJob
            for raw_payload in sorted(set(current)):
                try:
                    payload = raw_payload.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                occurrences = current.count(raw_payload)
                item = {
                    "key": queue,
                    "payload": payload,
                    "occurrences": str(occurrences),
                }
                if payload in payloads:
                    queue_payloads.append(item)
                    continue
                try:
                    job_id = UUID(payload)
                except ValueError:
                    continue
                if str(job_id) != payload or db.get(model, job_id) is not None:
                    continue
                orphan_queue_payloads.append(item)
        return {
            "redis_rate_limit_keys": sorted(rate_keys, key=lambda item: item["key"]),
            "redis_queue_payloads": queue_payloads,
            "redis_orphan_queue_payloads": orphan_queue_payloads,
        }
    finally:
        client.close()


def delete_redis_fixture_manifest(
    db: Session,
    report: dict[str, list[dict[str, str]]],
    records: dict[str, list],
) -> int:
    _assert_local_redis()
    client = redis.Redis.from_url(
        get_settings().redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    try:
        rate_keys = [item["key"] for item in report["redis_rate_limit_keys"]]
        identifiers = set(records["redis_rate_identifiers"])
        if len(rate_keys) != len(set(rate_keys)) or any(
            not _fixture_rate_key(key, identifiers) for key in rate_keys
        ):
            raise SystemExit("Redis fixture manifest contains an unapproved or duplicate key")
        for start in range(0, len(rate_keys), 500):
            chunk = rate_keys[start : start + 500]
            if chunk:
                client.delete(*chunk)
        if any(client.exists(key) for key in rate_keys):
            raise RuntimeError("Redis exact-key deletion verification failed")
        removed_payloads = 0
        queue_items = [
            *report["redis_queue_payloads"],
            *report["redis_orphan_queue_payloads"],
        ]
        seen_payloads: set[tuple[str, str]] = set()
        for item in queue_items:
            queue = item["key"]
            payload = item["payload"]
            model = (
                ProcessingJob
                if queue == PROCESSING_QUEUE
                else SceneIntelligenceJob
                if queue == SCENE_QUEUE
                else None
            )
            fixture_payloads = (
                records["redis_processing_payloads"]
                if queue == PROCESSING_QUEUE
                else records["redis_scene_payloads"]
                if queue == SCENE_QUEUE
                else []
            )
            try:
                job_id = UUID(payload)
            except ValueError:
                job_id = None
            proven_orphan = (
                model is not None
                and job_id is not None
                and str(job_id) == payload
                and db.get(model, job_id) is None
            )
            identity = (queue, payload)
            if (
                identity in seen_payloads
                or (payload not in fixture_payloads and not proven_orphan)
            ):
                raise SystemExit("Redis fixture manifest contains an unapproved queue payload")
            seen_payloads.add(identity)
            removed_payloads += client.lrem(queue, 0, payload)
            if client.lpos(queue, payload) is not None:
                raise RuntimeError("Redis exact-payload deletion verification failed")
        return len(rate_keys) + removed_payloads
    finally:
        client.close()


def apply_cleanup(db: Session, records: dict[str, list]) -> None:
    for model, key in (
        (User, "users"),
        (MediaAsset, "media_assets"),
        (Movie, "movies"),
        (Collection, "collections"),
        (Journey, "journeys"),
        (Person, "people"),
        (Character, "characters"),
        (Genre, "genres"),
        (AuditLog, "audit_logs"),
        (Admin, "admins"),
        (BillingWebhookEvent, "billing_webhook_events"),
        (AggregatedMetric, "aggregated_metrics"),
    ):
        if records[key]:
            db.execute(delete(model).where(model.id.in_(records[key])))
    db.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm")
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--skip-object-storage",
        action="store_true",
        help="Database-clone verification only; never use for the real cleanup.",
    )
    args = parser.parse_args()
    with SessionLocal() as db:
        _assert_local_development(db)
        report, records = collect_fixture_leaks(db)
        report["object_storage_objects"] = (
            [] if args.skip_object_storage else collect_s3_fixture_leaks(report["media_assets"])
        )
        redis_report = collect_redis_fixture_leaks(db, records)
        report.update(redis_report)
        payload = {
            "generated_at": datetime.now(UTC).isoformat(),
            "mode": "apply" if args.apply else "audit",
            "counts": {key: len(value) for key, value in report.items()},
            "records": report,
        }
        rendered = json.dumps(payload, indent=2, sort_keys=True)
        print(rendered)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(rendered + "\n", encoding="utf-8")
        if not args.apply:
            raise SystemExit(1 if any(report.values()) else 0)
        if args.confirm != CONFIRMATION:
            raise SystemExit(f"--apply requires --confirm {CONFIRMATION}")
        deleted_objects = (
            0
            if args.skip_object_storage
            else delete_s3_fixture_manifest(
                report["object_storage_objects"],
                report["media_assets"],
            )
        )
        deleted_redis_items = delete_redis_fixture_manifest(db, redis_report, records)
        apply_cleanup(db, records)
        print(
            "Removed confirmed fixture rows, "
            f"{deleted_objects} test storage objects, and {deleted_redis_items} Redis items."
        )


if __name__ == "__main__":
    main()
