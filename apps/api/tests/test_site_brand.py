import struct
import uuid
import zlib
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Barrier
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import delete, func, select, update

from app.auth import hash_password
from app.db import SessionLocal
from app.email_delivery import _send_password_reset
from app.main import app
from app.models import Admin, AuditLog, SiteBrandAsset, SiteBrandConfiguration
from app.site_brand_schemas import SiteBrandPatchRequest
from app.site_brand_service import (
    admin_response,
    default_config,
    get_or_claim_configuration,
    patch_configuration,
    public_response,
    validate_logo,
)
from scripts.reassign_site_brand_owner import reassign_site_brand_owner


@pytest.fixture(autouse=True)
def _isolate_preexisting_active_admins():
    """Keep the sole-owner contract independent of administrators from earlier tests."""
    with SessionLocal() as db:
        active_admin_ids = list(
            db.scalars(select(Admin.id).where(Admin.is_active.is_(True)))
        )
        if active_admin_ids:
            db.execute(
                update(Admin)
                .where(Admin.id.in_(active_admin_ids))
                .values(is_active=False)
            )
            db.commit()

    try:
        yield
    finally:
        if active_admin_ids:
            with SessionLocal() as db:
                db.execute(
                    update(Admin)
                    .where(Admin.id.in_(active_admin_ids))
                    .values(is_active=True)
                )
                db.commit()


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(kind)
    checksum = zlib.crc32(data, checksum)
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)


def _valid_png(width: int = 64, height: int = 64) -> bytes:
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    row = b"\x00" + (b"\xff\x5c\x35\xff" * width)
    pixels = zlib.compress(row * height)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", pixels)
        + _png_chunk(b"IEND", b"")
    )


def _encoded_logo(image_format: str) -> bytes:
    output = BytesIO()
    Image.new("RGBA" if image_format != "JPEG" else "RGB", (64, 64), "#ff5c35").save(
        output,
        format=image_format,
    )
    return output.getvalue()


def test_owner_brand_setup_publish_and_logo_lifecycle() -> None:
    suffix = uuid.uuid4().hex[:10]
    owner_email = f"brand-owner-{suffix}@example.com"
    other_email = f"brand-other-{suffix}@example.com"
    password = "BrandOwnerPassword123"
    with SessionLocal() as db:
        owner = Admin(email=owner_email, password_hash=hash_password(password))
        db.add(owner)
        db.commit()
        owner_id = owner.id
    other_id = None

    try:
        with TestClient(app) as anonymous:
            fallback = anonymous.get("/site/brand")
            assert fallback.status_code == 200
            assert fallback.json() == {
                "schema_version": 1,
                "revision": 0,
                "business_name": "Aperture",
                "short_name": "Aperture",
                "tagline": "Stories worth staying for.",
                "description": "A cinematic home for films and series.",
                "logo_url": None,
                "logo_revision": 0,
                "logo_mark": None,
                "palette": {
                    "accent": "#ff5c35",
                    "accent_hover": "#ff7657",
                    "on_accent": "#000000",
                    "surface": "#090909",
                    "surface_elevated": "#171310",
                    "text": "#f7f2ea",
                    "text_muted": "#b8afa6",
                },
                "locale": {
                    "default_locale": "en-US",
                    "home_market": "US",
                    "currency": "USD",
                },
                "published_at": None,
            }
            assert fallback.headers["cache-control"].startswith("public")
            fallback_etag = fallback.headers["etag"]
            assert (
                anonymous.get("/site/brand", headers={"If-None-Match": fallback_etag}).status_code
                == 304
            )
            assert anonymous.get("/admin/site/brand").status_code == 401

        with TestClient(app) as owner_client:
            login = owner_client.post(
                "/admin/auth/login", json={"email": owner_email, "password": password}
            )
            assert login.status_code == 200
            initial = owner_client.get("/admin/site/brand")
            assert initial.status_code == 200
            assert initial.headers["cache-control"] == "no-store"
            assert initial.json()["revision"] == 0
            assert initial.json()["status"] == "draft"
            with SessionLocal() as db:
                stored = db.get_one(SiteBrandConfiguration, 1)
                assert stored.draft_config["schema_version"] == 1

            changed = owner_client.patch(
                "/admin/site/brand",
                json={
                    "revision": 0,
                    "current_step": 2,
                    "completed_steps": [1],
                    "config": {
                        "business_name": "Northstar Pictures",
                        "short_name": "Northstar",
                        "tagline": "Cinema, charted differently.",
                        "description": "A home for independent films and enduring series.",
                        "palette": {"accent": "#ff5c35"},
                        "locale": {
                            "default_locale": "en-ca",
                            "home_market": "ca",
                            "currency": "cad",
                        },
                    },
                },
            )
            assert changed.status_code == 200, changed.text
            assert changed.json()["revision"] == 1
            assert changed.json()["config"]["locale"] == {
                "default_locale": "en-CA",
                "home_market": "CA",
                "currency": "CAD",
            }
            assert (
                owner_client.patch(
                    "/admin/site/brand",
                    json={"revision": 0, "current_step": 3},
                ).status_code
                == 409
            )
            inaccessible_palette = owner_client.patch(
                "/admin/site/brand",
                json={
                    "revision": 1,
                    "config": {"palette": {"text": "#111111", "surface": "#101010"}},
                },
            )
            assert inaccessible_palette.status_code == 422
            inaccessible_elevated_surface = owner_client.patch(
                "/admin/site/brand",
                json={
                    "revision": 1,
                    "config": {"palette": {"surface_elevated": "#f7f2ea"}},
                },
            )
            assert inaccessible_elevated_surface.status_code == 422
            split_button_contrast = owner_client.patch(
                "/admin/site/brand",
                json={
                    "revision": 1,
                    "config": {
                        "palette": {
                            "accent": "#000000",
                            "accent_hover": "#ffffff",
                            "surface": "#767676",
                            "surface_elevated": "#767676",
                            "text": "#ffffff",
                            "text_muted": "#000000",
                        }
                    },
                },
            )
            assert split_button_contrast.status_code == 422
            assert "share readable black or white" in split_button_contrast.text
            assert owner_client.post(
                "/admin/site/brand/publish", json={"revision": 1}
            ).status_code == 422

            public_before_publish = owner_client.get("/site/brand").json()
            assert public_before_publish["business_name"] == "Aperture"

            ready = owner_client.patch(
                "/admin/site/brand",
                json={
                    "revision": 1,
                    "current_step": 5,
                    "completed_steps": [1, 2, 3, 4, 5],
                },
            )
            assert ready.status_code == 200
            assert ready.json()["revision"] == 2

            logo = _valid_png()
            uploaded = owner_client.put(
                "/admin/site/brand/logo?expected_revision=2",
                content=logo,
                headers={"Content-Type": "image/png"},
            )
            assert uploaded.status_code == 200, uploaded.text
            upload_payload = uploaded.json()
            assert upload_payload["revision"] == 3
            assert upload_payload["config"]["logo_url"].startswith("/admin/site/brand/logo")
            assert upload_payload["config"]["logo_revision"] == 3
            preview = owner_client.get("/admin/site/brand/logo")
            assert preview.status_code == 200
            assert preview.content == logo
            assert preview.headers["cache-control"] == "no-store"
            assert owner_client.get("/site/brand/logo").status_code == 404
            assert (
                owner_client.put(
                    "/admin/site/brand/logo?expected_revision=3",
                    content=logo,
                    headers={"Content-Type": "image/png"},
                ).json()["revision"]
                == 3
            )
            assert (
                owner_client.put(
                    "/admin/site/brand/logo?expected_revision=3",
                    content=b"<svg><script>alert(1)</script></svg>",
                    headers={"Content-Type": "image/svg+xml"},
                ).status_code
                == 415
            )

            published = owner_client.post(
                "/admin/site/brand/publish", json={"revision": 3}
            )
            assert published.status_code == 200, published.text
            assert published.json()["status"] == "published"
            assert published.json()["revision"] == 4
            live = owner_client.get("/site/brand")
            assert live.json()["business_name"] == "Northstar Pictures"
            assert live.json()["short_name"] == "Northstar"
            assert live.json()["revision"] == 4
            assert live.json()["logo_url"].startswith("/site/brand/logo")
            assert live.json()["palette"]["on_accent"] == "#000000"
            logo_revision = live.json()["logo_revision"]
            with SessionLocal() as db:
                stored = db.get_one(SiteBrandConfiguration, 1)
                assert stored.draft_config["schema_version"] == 1
                assert stored.published_snapshot["schema_version"] == 1
            live_logo = owner_client.get("/site/brand/logo")
            assert live_logo.content == logo
            assert live_logo.headers["content-type"] == "image/png"
            assert owner_client.get(
                f"/site/brand/logo?revision={logo_revision}"
            ).content == logo
            assert owner_client.get(
                f"/site/brand/logo?revision={logo_revision + 1}"
            ).status_code == 404
            assert owner_client.get(
                f"/site/brand/logo?revision={max(0, logo_revision - 1)}"
            ).status_code == 404
            assert (
                owner_client.get(
                    f"/site/brand/logo?revision={logo_revision}",
                    headers={"If-None-Match": live_logo.headers["etag"]},
                ).status_code
                == 304
            )

            next_draft = owner_client.patch(
                "/admin/site/brand",
                json={
                    "revision": 4,
                    "config": {"business_name": "Unreleased Company Name"},
                },
            )
            assert next_draft.json()["revision"] == 5
            assert next_draft.json()["status"] == "draft"
            assert owner_client.get("/site/brand").json()["business_name"] == (
                "Northstar Pictures"
            )

            removed = owner_client.delete(
                "/admin/site/brand/logo?expected_revision=5"
            )
            assert removed.status_code == 200
            assert removed.json()["revision"] == 6
            assert removed.json()["config"]["logo_url"] is None
            assert owner_client.get("/admin/site/brand/logo").status_code == 404
            assert owner_client.get("/site/brand/logo").status_code == 200
            republished = owner_client.post(
                "/admin/site/brand/publish", json={"revision": 6}
            )
            assert republished.status_code == 200
            assert republished.json()["revision"] == 7
            assert owner_client.get("/site/brand/logo").status_code == 404

        with SessionLocal() as db:
            other = Admin(email=other_email, password_hash=hash_password(password))
            db.add(other)
            db.commit()
            other_id = other.id

        with TestClient(app) as other_client:
            assert other_client.post(
                "/admin/auth/login", json={"email": other_email, "password": password}
            ).status_code == 200
            forbidden = other_client.get("/admin/site/brand")
            assert forbidden.status_code == 403

        with SessionLocal() as db:
            actions = set(
                db.scalars(select(AuditLog.action).where(AuditLog.actor_id == owner_id))
            )
            assert {
                "site_brand.owner.claimed",
                "site_brand.draft.updated",
                "site_brand.logo.updated",
                "site_brand.logo.deleted",
                "site_brand.published",
            }.issubset(actions)
            assert db.scalar(select(func.count(SiteBrandAsset.id))) == 0
    finally:
        with SessionLocal() as db:
            db.execute(delete(SiteBrandConfiguration))
            db.execute(delete(SiteBrandAsset))
            admin_ids = [owner_id, *([other_id] if other_id is not None else [])]
            db.execute(delete(AuditLog).where(AuditLog.actor_id.in_(admin_ids)))
            db.execute(delete(Admin).where(Admin.id.in_(admin_ids)))
            db.commit()


@pytest.mark.parametrize(
    ("content_type", "image_format"),
    [
        ("image/png", "PNG"),
        ("image/jpeg", "JPEG"),
        ("image/webp", "WEBP"),
    ],
)
def test_logo_validation_fully_decodes_and_rejects_truncated_images(
    content_type: str,
    image_format: str,
) -> None:
    complete = _encoded_logo(image_format)
    validated = validate_logo(complete, content_type)
    assert (validated.width, validated.height) == (64, 64)

    with pytest.raises(HTTPException) as rejected:
        validate_logo(complete[: len(complete) // 2], content_type)
    assert rejected.value.status_code == 422


def test_brand_owner_claim_requires_one_active_admin() -> None:
    suffix = uuid.uuid4().hex[:10]
    password_hash = hash_password("ProvisionedOwner123")
    with SessionLocal() as db:
        intended_owner = Admin(
            email=f"intended-owner-{suffix}@example.com",
            password_hash=password_hash,
        )
        unexpected_admin = Admin(
            email=f"unexpected-admin-{suffix}@example.com",
            password_hash=password_hash,
        )
        db.add_all([intended_owner, unexpected_admin])
        db.commit()
        intended_owner_id = intended_owner.id
        unexpected_admin_id = unexpected_admin.id

    try:
        with SessionLocal() as db:
            with pytest.raises(HTTPException) as ambiguous:
                get_or_claim_configuration(db, db.get_one(Admin, intended_owner_id))
            assert ambiguous.value.status_code == 409
            assert db.get(SiteBrandConfiguration, 1) is None

        with SessionLocal() as db:
            db.get_one(Admin, unexpected_admin_id).is_active = False
            db.commit()
        with SessionLocal() as db:
            configuration, claimed = get_or_claim_configuration(
                db, db.get_one(Admin, intended_owner_id)
            )
            db.commit()
            assert claimed is True
            assert configuration.owner_admin_id == intended_owner_id

        with SessionLocal() as db:
            db.get_one(Admin, unexpected_admin_id).is_active = True
            db.commit()
        with SessionLocal() as db:
            with pytest.raises(HTTPException) as forbidden:
                get_or_claim_configuration(db, db.get_one(Admin, unexpected_admin_id))
            assert forbidden.value.status_code == 403
    finally:
        with SessionLocal() as db:
            db.execute(delete(SiteBrandConfiguration))
            db.execute(delete(Admin).where(Admin.id.in_([intended_owner_id, unexpected_admin_id])))
            db.commit()


def test_brand_owner_claim_is_concurrency_safe_for_the_provisioned_admin() -> None:
    suffix = uuid.uuid4().hex[:10]
    with SessionLocal() as db:
        admin = Admin(
            email=f"concurrent-owner-{suffix}@example.com",
            password_hash=hash_password("ConcurrentOwner123"),
        )
        db.add(admin)
        db.commit()
        admin_id = admin.id

    barrier = Barrier(2)

    def claim() -> tuple[uuid.UUID, bool]:
        with SessionLocal() as db:
            claimant = db.get_one(Admin, admin_id)
            barrier.wait(timeout=5)
            configuration, claimed = get_or_claim_configuration(db, claimant)
            db.commit()
            return configuration.owner_admin_id, claimed

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _index: claim(), range(2)))
        assert results.count((admin_id, True)) == 1
        assert results.count((admin_id, False)) == 1
        with SessionLocal() as db:
            assert db.scalar(select(func.count(SiteBrandConfiguration.id))) == 1
    finally:
        with SessionLocal() as db:
            db.execute(delete(SiteBrandConfiguration))
            db.execute(delete(Admin).where(Admin.id == admin_id))
            db.commit()


def test_brand_owner_recovery_is_offline_verified_and_audited() -> None:
    suffix = uuid.uuid4().hex[:10]
    with SessionLocal() as db:
        current = Admin(
            email=f"recovery-current-{suffix}@example.com",
            password_hash=hash_password("RecoveryCurrent123"),
        )
        replacement = Admin(
            email=f"recovery-new-{suffix}@example.com",
            password_hash=hash_password("RecoveryReplace123"),
        )
        db.add_all([current, replacement])
        db.flush()
        db.add(
            SiteBrandConfiguration(
                id=1,
                owner_admin_id=current.id,
                draft_config={"schema_version": 1, **default_config().model_dump(mode="json")},
                revision=0,
                current_step=1,
                completed_steps=[],
            )
        )
        db.commit()
        current_id = current.id
        replacement_id = replacement.id

    try:
        with SessionLocal() as db:
            previous, new = reassign_site_brand_owner(
                db,
                current_owner_email=f"recovery-current-{suffix}@example.com",
                new_owner_email=f"recovery-new-{suffix}@example.com",
                reason="Approved owner recovery incident INC-1234",
            )
            db.commit()
            assert previous.id == current_id
            assert new.id == replacement_id

        with SessionLocal() as db:
            configuration = db.get_one(SiteBrandConfiguration, 1)
            assert configuration.owner_admin_id == replacement_id
            audit = db.scalar(
                select(AuditLog).where(AuditLog.action == "site_brand.owner.reassigned")
            )
            assert audit is not None
            assert audit.detail["previous_owner_id"] == str(current_id)
            assert audit.detail["new_owner_id"] == str(replacement_id)
            assert audit.detail["reason"] == "Approved owner recovery incident INC-1234"
    finally:
        with SessionLocal() as db:
            db.execute(delete(SiteBrandConfiguration))
            db.execute(
                delete(AuditLog).where(AuditLog.action == "site_brand.owner.reassigned")
            )
            db.execute(delete(Admin).where(Admin.id.in_([current_id, replacement_id])))
            db.commit()


def test_brand_snapshots_parse_legacy_v1_and_reject_unknown_versions() -> None:
    suffix = uuid.uuid4().hex[:10]
    legacy_snapshot = default_config().model_dump(mode="json")
    legacy_snapshot["palette"].pop("on_accent")
    with SessionLocal() as db:
        admin = Admin(
            email=f"snapshot-owner-{suffix}@example.com",
            password_hash=hash_password("SnapshotOwner123"),
        )
        db.add(admin)
        db.flush()
        configuration = SiteBrandConfiguration(
            id=1,
            owner_admin_id=admin.id,
            draft_config=legacy_snapshot,
            published_snapshot=legacy_snapshot,
            revision=1,
            published_revision=1,
            current_step=1,
            completed_steps=[],
        )
        db.add(configuration)
        db.commit()
        admin_id = admin.id

    try:
        with SessionLocal() as db:
            configuration = db.get_one(SiteBrandConfiguration, 1)
            assert admin_response(db, configuration).config.business_name == "Aperture"
            assert public_response(db).business_name == "Aperture"
            configuration, _changed = patch_configuration(
                db,
                configuration,
                SiteBrandPatchRequest(
                    revision=1,
                    config={"business_name": "Versioned Cinema"},
                ),
            )
            db.commit()
            assert configuration.draft_config["schema_version"] == 1

        with SessionLocal() as db:
            configuration = db.get_one(SiteBrandConfiguration, 1)
            configuration.draft_config = {
                "schema_version": 999,
                **legacy_snapshot,
            }
            configuration.published_snapshot = {
                "schema_version": 999,
                **legacy_snapshot,
            }
            db.commit()
        with SessionLocal() as db:
            configuration = db.get_one(SiteBrandConfiguration, 1)
            with pytest.raises(HTTPException) as admin_error:
                admin_response(db, configuration)
            assert admin_error.value.status_code == 503
            with pytest.raises(HTTPException) as public_error:
                public_response(db)
            assert public_error.value.status_code == 503
    finally:
        with SessionLocal() as db:
            db.execute(delete(SiteBrandConfiguration))
            db.execute(delete(Admin).where(Admin.id == admin_id))
            db.commit()


def test_brand_schema_rejects_unknown_fields_and_invalid_stage_sequences() -> None:
    suffix = uuid.uuid4().hex[:10]
    email = f"brand-validation-{suffix}@example.com"
    password = "test-password"
    with SessionLocal() as db:
        admin = Admin(email=email, password_hash=hash_password(password))
        db.add(admin)
        db.commit()
        admin_id = admin.id
    try:
        with TestClient(app) as client:
            assert client.post(
                "/admin/auth/login", json={"email": email, "password": password}
            ).status_code == 200
            assert client.get("/admin/site/brand").status_code == 200
            assert client.patch(
                "/admin/site/brand",
                json={"revision": 0, "completed_steps": [1, 3]},
            ).status_code == 422
            assert client.patch(
                "/admin/site/brand",
                json={"revision": 0, "config": {"logo_url": "https://attacker.invalid/a.png"}},
            ).status_code == 422
            assert client.patch(
                "/admin/site/brand",
                json={"revision": 0, "config": {"business_name": "X"}},
            ).status_code == 422
    finally:
        with SessionLocal() as db:
            db.execute(delete(SiteBrandConfiguration))
            db.execute(delete(AuditLog).where(AuditLog.actor_id == admin_id))
            db.execute(delete(Admin).where(Admin.id == admin_id))
            db.commit()


def test_password_reset_email_uses_runtime_brand_without_header_injection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_messages = []

    class FakeSmtp:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def starttls(self, *, context: object) -> None:
            assert context is not None
            pass

        def login(self, _username: str, _password: str) -> None:
            pass

        def send_message(self, message) -> None:
            sent_messages.append(message)

    monkeypatch.setattr(
        "app.email_delivery.get_settings",
        lambda: SimpleNamespace(
            smtp_host="smtp.example.test",
            smtp_port=587,
            smtp_username="mailer",
            smtp_password="secret",
            smtp_from_email="support@example.test",
            smtp_starttls=True,
            web_origin="https://watch.example.test",
        ),
    )
    monkeypatch.setattr("app.email_delivery.smtplib.SMTP", FakeSmtp)

    _send_password_reset(
        "viewer@example.test",
        "one-time-token",
        "Northstar\r\nBcc: attacker@example.test",
        "https://watch.customer.example",
    )

    message = sent_messages[0]
    assert message["Subject"] == "Reset your Northstar Bcc: attacker@example.test password"
    assert "Northstar Bcc: attacker@example.test account" in message.get_content()
    assert (
        "https://watch.customer.example/reset-password?token=one-time-token"
        in message.get_content()
    )
