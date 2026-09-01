import hashlib
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.auth import token_hash, verify_password
from app.config import Settings, get_settings
from app.db import SessionLocal
from app.main import app
from app.models import SiteDomain
from app.platform_models import (
    LegalAcceptance,
    PlatformAccount,
    PlatformAuditEvent,
    PlatformEmailVerificationToken,
    PlatformSession,
    PlatformTemplate,
    PlatformTemplateVersion,
    RentalAgreementVersion,
    TemplateRental,
    TenantMembership,
    TenantReservation,
)
from app.platform_schemas import TemplatePreviewAsset
from app.platform_security import platform_rate_limit_identifier, require_platform_origin
from app.routes import platform_auth

PASSWORD = "StrongPlatformPassword123"
API_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _isolate_platform_auth_rate_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    async def allow(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(platform_auth, "enforce_rate_limit", allow)


def _response_datetime(value: object) -> datetime:
    assert isinstance(value, str)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _published_template() -> dict[str, object]:
    suffix = uuid.uuid4().hex
    template_id = uuid.uuid4()
    version_id = uuid.uuid4()
    agreement_id = uuid.uuid4()
    slug = f"fixture-{suffix[:16]}"
    agreement_content = (
        "This immutable fixture agreement records the exact terms accepted by the renter. "
        f"Reference {suffix}. "
    ) * 4
    agreement_sha256 = hashlib.sha256(agreement_content.encode()).hexdigest()
    version_name = f"1.0.0-{suffix[:8]}"
    agreement_name = f"2026-{suffix[:8]}"
    published_at = datetime.now(UTC)

    with SessionLocal() as db:
        template = PlatformTemplate(
            id=template_id,
            slug=slug,
            name=f"Fixture {suffix[:8]}",
            description="A published test-only marketplace template.",
            category="streaming",
            thumbnail_url="/marketplace/fixture.jpg",
            preview_assets=[
                {
                    "kind": "image",
                    "url": "https://assets.example.test/fixture.jpg",
                    "alt": "Fixture storefront preview",
                }
            ],
            demo_url="https://demo.example.test/",
            status="preview",
        )
        db.add(template)
        db.commit()

        db.add_all(
            [
                PlatformTemplateVersion(
                    id=version_id,
                    template_id=template_id,
                    version=version_name,
                    source_commit=(suffix + "0" * 8),
                    release_manifest_sha256=hashlib.sha256(
                        f"manifest:{suffix}".encode()
                    ).hexdigest(),
                    feature_manifest={"explore": True, "studio": True},
                    configuration_schema={"type": "object", "additionalProperties": False},
                    published_at=published_at,
                ),
                RentalAgreementVersion(
                    id=agreement_id,
                    template_id=template_id,
                    version=agreement_name,
                    title="Fixture rental agreement",
                    content=agreement_content,
                    content_sha256=agreement_sha256,
                    published_at=published_at,
                ),
            ]
        )
        db.commit()

        template.current_version_id = version_id
        template.current_agreement_version_id = agreement_id
        template.rental_price_cents = 4900
        template.rental_currency = "CAD"
        template.rental_interval = "month"
        template.status = "published"
        db.commit()

    return {
        "template_id": template_id,
        "template_slug": slug,
        "template_version_id": version_id,
        "template_version": version_name,
        "agreement_version_id": agreement_id,
        "agreement_version": agreement_name,
        "agreement_sha256": agreement_sha256,
    }


def _register(
    client: TestClient,
    label: str,
    *,
    verify: bool = True,
) -> tuple[str, dict[str, object]]:
    email = f"platform-{label}-{uuid.uuid4().hex}@example.com"
    response = client.post(
        "/platform/auth/register",
        json={
            "email": email.upper(),
            "password": PASSWORD,
            "captcha_token": "local-captcha-pass",
        },
    )
    assert response.status_code == 201, response.text
    registration = response.json()
    assert registration["email"] == email
    assert registration["email_verified"] is False
    assert registration["unverified_account_expires_at"] is not None
    assert registration["verification_delivery"] == "development"
    assert registration["verification_token_expires_at"] is not None
    assert _response_datetime(registration["verification_token_expires_at"]) <= (
        _response_datetime(registration["unverified_account_expires_at"])
    )
    token = registration["development_verification_token"]
    assert isinstance(token, str) and len(token) >= 32
    if not verify:
        return email, registration
    confirmation = client.post(
        "/platform/auth/email-verification/confirm",
        json={"token": token},
    )
    assert confirmation.status_code == 200, confirmation.text
    account = confirmation.json()
    assert account["email_verified"] is True
    assert account["unverified_account_expires_at"] is None
    return email, account


def _intent_payload(
    publication: dict[str, object],
    *,
    tenant_slug: str | None = None,
) -> dict[str, object]:
    return {
        "template_slug": publication["template_slug"],
        "template_version_id": str(publication["template_version_id"]),
        "agreement_version_id": str(publication["agreement_version_id"]),
        "agreement_version": publication["agreement_version"],
        "agreement_sha256": publication["agreement_sha256"],
        "accepted": True,
        "business_name": "Fixture Cinema Company",
        "requested_tenant_slug": tenant_slug or f"cinema-{uuid.uuid4().hex[:12]}",
    }


def _row_counts() -> dict[type[object], int]:
    models: tuple[type[object], ...] = (
        TenantReservation,
        TenantMembership,
        LegalAcceptance,
        TemplateRental,
        SiteDomain,
    )
    with SessionLocal() as db:
        return {model: db.scalar(select(func.count()).select_from(model)) or 0 for model in models}


def _request(origin: str | None, asserted: str | None = None, secret: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    for name, value in (
        ("origin", origin),
        ("x-aperture-public-origin", asserted),
        ("x-aperture-edge-secret", secret),
    ):
        if value is not None:
            headers.append((name.encode(), value.encode()))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "https",
            "path": "/platform/rental-intents",
            "raw_path": b"/platform/rental-intents",
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 1234),
            "server": ("api.apertures.online", 443),
        }
    )


def test_platform_registry_preview_is_honest_and_public_urls_fail_closed() -> None:
    assert Settings.model_fields["platform_control_plane_enabled"].default is False
    oversized_base_domain = f"{'a' * 63}.{'b' * 63}.{'c' * 62}"
    with pytest.raises(ValueError, match="at most 189"):
        Settings(platform_tenant_base_domain=oversized_base_domain)

    with TestClient(app) as client:
        listing = client.get("/platform/templates")
        assert listing.status_code == 200
        assert listing.headers["cache-control"].startswith("private, no-store")
        assert "Cookie" in listing.headers["vary"]
        preview = next(item for item in listing.json()["items"] if item["slug"] == "apertures")
        assert preview["status"] == "preview"
        assert preview["current_version"] is None
        assert preview["starting_price"] is None
        assert preview["rental_available"] is False

        detail = client.get("/platform/templates/apertures")
        assert detail.status_code == 200
        assert detail.json()["rental_agreement"] is None

        unauthorized = client.get("/platform/rentals")
        assert unauthorized.status_code == 401
        assert unauthorized.headers["cache-control"].startswith("private, no-store")

    for unsafe in (
        "//evil.example/image.jpg",
        "javascript:alert(1)",
        "http://assets.example/image.jpg",
        "https://user:password@assets.example/image.jpg",
        "/\\evil.example/image.jpg",
    ):
        with pytest.raises(ValidationError):
            TemplatePreviewAsset(kind="image", url=unsafe, alt="Unsafe")
    assert TemplatePreviewAsset(kind="image", url="/safe/image.jpg", alt="Safe")
    assert TemplatePreviewAsset(kind="video", url="https://assets.example/video", alt="Safe")


def test_platform_migration_matches_orm_metadata() -> None:
    configuration = AlembicConfig(str(API_ROOT / "alembic.ini"))
    configuration.set_main_option("script_location", str(API_ROOT / "migrations"))
    command.check(configuration)


def test_platform_migration_rejects_preexisting_platform_accounts_before_alter() -> None:
    migration_path = (
        API_ROOT
        / "migrations"
        / "versions"
        / "20260831_0037_platform_rental_safety.py"
    )
    upgrade_source = migration_path.read_text(encoding="utf-8").split(
        "def upgrade() -> None:",
        maxsplit=1,
    )[1]
    table_lock = '"LOCK TABLE platform_accounts, template_rentals, platform_tenants, "'
    account_preflight = "IF EXISTS (SELECT 1 FROM platform_accounts)"
    first_account_alter = 'op.add_column(\n        "platform_accounts"'
    assert account_preflight in upgrade_source
    assert table_lock in upgrade_source
    assert "requires platform_accounts to be empty" in upgrade_source
    assert upgrade_source.index(table_lock) < upgrade_source.index(account_preflight)
    assert upgrade_source.index(account_preflight) < upgrade_source.index(
        first_account_alter
    )

    downgrade_source = migration_path.read_text(encoding="utf-8").split(
        "def downgrade() -> None:",
        maxsplit=1,
    )[1]
    downgrade_lock = (
        '"LOCK TABLE platform_accounts, platform_email_verification_tokens, '
        'template_rentals, "'
    )
    downgrade_account_preflight = "OR EXISTS (SELECT 1 FROM platform_accounts)"
    first_downgrade_drop = 'op.drop_index(\n        "uq_platform_audit_events_rental_expired"'
    assert downgrade_lock in downgrade_source
    assert downgrade_account_preflight in downgrade_source
    assert downgrade_source.index(downgrade_lock) < downgrade_source.index(
        downgrade_account_preflight
    )
    assert downgrade_source.index(downgrade_account_preflight) < downgrade_source.index(
        first_downgrade_drop
    )


def test_database_rejects_token_expiry_beyond_unverified_account_deadline() -> None:
    account_id = uuid.uuid4()
    suffix = uuid.uuid4().hex
    with SessionLocal() as db:
        issued_at = db.scalar(select(func.transaction_timestamp()))
        assert isinstance(issued_at, datetime)
        account_deadline = issued_at + timedelta(hours=1)
        db.add(
            PlatformAccount(
                id=account_id,
                email=f"token-deadline-{suffix}@example.com",
                password_hash="unused-fixture-hash",
                email_verification_expires_at=account_deadline,
            )
        )
        db.commit()

    with SessionLocal() as db, pytest.raises(SQLAlchemyError):
        db.add(
            PlatformEmailVerificationToken(
                account_id=account_id,
                token_hash=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
                expires_at=account_deadline + timedelta(seconds=1),
                state="pending_delivery",
                created_at=issued_at,
            )
        )
        db.commit()

    with SessionLocal() as db:
        assert db.scalar(
            select(func.count())
            .select_from(PlatformEmailVerificationToken)
            .where(PlatformEmailVerificationToken.account_id == account_id)
        ) == 0


def test_verification_token_defaults_fail_safe_to_pending_delivery() -> None:
    account_ids = (uuid.uuid4(), uuid.uuid4())
    issued_at: datetime
    with SessionLocal() as db:
        issued_at = db.scalar(select(func.transaction_timestamp()))
        assert isinstance(issued_at, datetime)
        for index, account_id in enumerate(account_ids):
            db.add(
                PlatformAccount(
                    id=account_id,
                    email=f"pending-default-{index}-{uuid.uuid4().hex}@example.com",
                    password_hash="unused-fixture-hash",
                    email_verification_expires_at=issued_at + timedelta(hours=1),
                )
            )
        db.commit()

    with SessionLocal() as db:
        token = PlatformEmailVerificationToken(
            account_id=account_ids[0],
            token_hash=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
            expires_at=issued_at + timedelta(minutes=30),
            created_at=issued_at,
        )
        db.add(token)
        db.flush()
        assert token.state == "pending_delivery"
        db.commit()

    raw_id = uuid.uuid4()
    with SessionLocal() as db:
        db.execute(
            text(
                """
                INSERT INTO platform_email_verification_tokens
                    (id, account_id, token_hash, expires_at, created_at)
                VALUES (:id, :account_id, :token_hash, :expires_at, :created_at)
                """
            ),
            {
                "id": raw_id,
                "account_id": account_ids[1],
                "token_hash": hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
                "expires_at": issued_at + timedelta(minutes=30),
                "created_at": issued_at,
            },
        )
        db.commit()

    with SessionLocal() as db:
        raw_token = db.get(PlatformEmailVerificationToken, raw_id)
        assert raw_token is not None
        assert raw_token.state == "pending_delivery"


def test_database_rejects_preverified_platform_account_insert() -> None:
    account_id = uuid.uuid4()
    with SessionLocal() as db, pytest.raises(SQLAlchemyError):
        database_now = db.scalar(select(func.transaction_timestamp()))
        assert isinstance(database_now, datetime)
        db.add(
            PlatformAccount(
                id=account_id,
                email=f"preverified-{uuid.uuid4().hex}@example.com",
                password_hash="unused-fixture-hash",
                email_verified_at=database_now,
            )
        )
        db.commit()

    with SessionLocal() as db:
        assert db.get(PlatformAccount, account_id) is None


def test_database_rejects_orphan_tenant_and_membership_inserts() -> None:
    suffix = uuid.uuid4().hex
    account_id = uuid.uuid4()
    with SessionLocal() as db:
        database_now = db.scalar(select(func.transaction_timestamp()))
        assert isinstance(database_now, datetime)
        db.add(
            PlatformAccount(
                id=account_id,
                email=f"orphan-owner-{suffix}@example.com",
                password_hash="unused-fixture-hash",
                email_verification_expires_at=database_now + timedelta(hours=24),
            )
        )
        db.commit()

    orphan_tenant_id = uuid.uuid4()
    with SessionLocal() as db, pytest.raises(SQLAlchemyError):
        db.add(
            TenantReservation(
                id=orphan_tenant_id,
                slug=f"orphan-{suffix[:12]}",
                hosted_hostname=f"orphan-{suffix[:12]}.apertures.online",
                business_name="Orphan tenant fixture",
                status="reserved",
            )
        )
        db.commit()

    membership_tenant_id = uuid.uuid4()
    membership_id = uuid.uuid4()
    with SessionLocal() as db, pytest.raises(SQLAlchemyError):
        db.add(
            TenantReservation(
                id=membership_tenant_id,
                slug=f"member-{suffix[:12]}",
                hosted_hostname=f"member-{suffix[:12]}.apertures.online",
                business_name="Orphan membership fixture",
                status="reserved",
            )
        )
        db.flush()
        db.add(
            TenantMembership(
                id=membership_id,
                tenant_id=membership_tenant_id,
                account_id=account_id,
                role="owner",
                status="active",
            )
        )
        db.flush()
        db.execute(
            text(
                "SET CONSTRAINTS "
                "trg_tenant_memberships_rental_lifecycle_consistency IMMEDIATE"
            )
        )

    with SessionLocal() as db:
        assert db.get(TenantReservation, orphan_tenant_id) is None
        assert db.get(TenantReservation, membership_tenant_id) is None
        assert db.get(TenantMembership, membership_id) is None


def test_platform_origin_is_exact_and_never_authorized_by_tenant_domains(monkeypatch) -> None:
    edge_secret = "e" * 40
    production = SimpleNamespace(
        web_origin="https://apertures.online",
        api_origin="https://api.apertures.online",
        custom_domain_edge_secret=SecretStr(edge_secret),
        app_env="production",
    )
    monkeypatch.setattr("app.platform_security.get_settings", lambda: production)

    require_platform_origin(_request("https://apertures.online"))
    require_platform_origin(
        _request(
            "https://apertures.online",
            asserted="https://apertures.online",
            secret=edge_secret,
        )
    )
    for request in (
        _request(None),
        _request("https://tenant-owned.example"),
        _request(
            "https://tenant-owned.example",
            asserted="https://tenant-owned.example",
            secret=edge_secret,
        ),
        _request(
            "https://apertures.online",
            asserted="https://apertures.online",
            secret="wrong-secret",
        ),
    ):
        with pytest.raises(HTTPException) as denied:
            require_platform_origin(request)
        assert denied.value.status_code == 403


def test_platform_auth_uses_a_separate_hashed_revocable_session() -> None:
    settings = get_settings()
    with TestClient(app) as client:
        configuration = client.get("/platform/auth/config")
        assert configuration.status_code == 200
        assert set(configuration.json()["captcha"]) == {"required", "test_mode"}

        email, account_body = _register(client, "auth", verify=False)
        assert account_body["email"] == email
        assert account_body["email_verified"] is False
        raw_verification_token = account_body["development_verification_token"]
        assert raw_verification_token

        with SessionLocal() as db:
            account = db.scalar(select(PlatformAccount).where(PlatformAccount.email == email))
            assert account is not None
            verification = db.scalar(
                select(PlatformEmailVerificationToken).where(
                    PlatformEmailVerificationToken.account_id == account.id,
                    PlatformEmailVerificationToken.state == "active",
                )
            )
            assert verification is not None
            assert verification.used_at is None
            assert verification.token_hash == token_hash(raw_verification_token)
            assert verification.token_hash != raw_verification_token
            assert raw_verification_token not in json.dumps(verification.__dict__, default=str)

        set_cookie = client.post(
            "/platform/auth/login",
            json={"email": email, "password": PASSWORD},
        )
        assert set_cookie.status_code == 200
        assert settings.platform_session_cookie in set_cookie.headers["set-cookie"]
        assert "HttpOnly" in set_cookie.headers["set-cookie"]
        assert "SameSite=lax" in set_cookie.headers["set-cookie"]
        raw_token = client.cookies.get(settings.platform_session_cookie)
        assert raw_token

        confirmed = client.post(
            "/platform/auth/email-verification/confirm",
            json={"token": raw_verification_token},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["email_verified"] is True
        assert confirmed.json()["unverified_account_expires_at"] is None
        already_verified = client.post("/platform/auth/email-verification/resend")
        assert already_verified.json()["status"] == "already_verified"
        assert already_verified.json()["verification_token_expires_at"] is None

        with SessionLocal() as db:
            account = db.scalar(select(PlatformAccount).where(PlatformAccount.email == email))
            assert account is not None
            assert account.password_hash != PASSWORD
            assert verify_password(account.password_hash, PASSWORD)
            sessions = list(
                db.scalars(select(PlatformSession).where(PlatformSession.account_id == account.id))
            )
            assert sessions
            assert all(session.token_hash != raw_token for session in sessions)
            assert any(session.token_hash == token_hash(raw_token) for session in sessions)
            assert account.email_verified_at is not None
            assert account.email_verification_expires_at is None
            assert not list(
                db.scalars(
                    select(PlatformEmailVerificationToken).where(
                        PlatformEmailVerificationToken.account_id == account.id,
                        PlatformEmailVerificationToken.state.in_(
                            ("active", "pending_delivery")
                        ),
                    )
                )
            )
            actions = set(
                db.scalars(
                    select(PlatformAuditEvent.action).where(
                        PlatformAuditEvent.actor_account_id == account.id
                    )
                )
            )
            assert {
                "platform_account.registered",
                "platform_account.login",
                "platform_account.email_verification_confirmed",
            } <= actions
            audit_details = list(
                db.scalars(
                    select(PlatformAuditEvent.detail).where(
                        PlatformAuditEvent.actor_account_id == account.id
                    )
                )
            )
            assert raw_verification_token not in json.dumps(audit_details)

        assert client.get("/platform/auth/me").json()["email"] == email
        assert client.post("/platform/auth/logout").status_code == 204
        client.cookies.set(settings.platform_session_cookie, raw_token)
        assert client.get("/platform/auth/me").status_code == 401

    with TestClient(
        app,
        cookies={settings.customer_session_cookie: raw_token},
    ) as customer_cookie_only:
        assert customer_cookie_only.get("/platform/auth/me").status_code == 401
    with TestClient(
        app,
        cookies={settings.admin_session_cookie: raw_token},
    ) as admin_cookie_only:
        assert admin_cookie_only.get("/platform/auth/me").status_code == 401


def test_successful_auth_audit_and_session_commit_atomically(monkeypatch) -> None:
    with TestClient(app) as registering:
        email, body = _register(registering, "atomic-audit")
        assert registering.post("/platform/auth/logout").status_code == 204

    account_id = uuid.UUID(str(body["id"]))
    with SessionLocal() as db:
        session_count_before = db.scalar(
            select(func.count())
            .select_from(PlatformSession)
            .where(PlatformSession.account_id == account_id)
        )

    def fail_audit(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("simulated audit persistence failure")

    monkeypatch.setattr(platform_auth, "_audit", fail_audit)
    with TestClient(app) as client:
        failed = client.post(
            "/platform/auth/login",
            json={"email": email, "password": PASSWORD},
        )
        assert failed.status_code == 500
        assert get_settings().platform_session_cookie not in client.cookies

    with SessionLocal() as db:
        session_count_after = db.scalar(
            select(func.count())
            .select_from(PlatformSession)
            .where(PlatformSession.account_id == account_id)
        )
    assert session_count_after == session_count_before


def test_unverified_accounts_cannot_reserve_and_verification_is_account_bound() -> None:
    publication = _published_template()
    payload = _intent_payload(publication)
    counts_before = _row_counts()

    with TestClient(app) as owner, TestClient(app) as other:
        owner_email, owner_body = _register(owner, "unverified-owner", verify=False)
        _, other_body = _register(other, "unverified-other", verify=False)
        owner_token = str(owner_body["development_verification_token"])

        blocked = owner.post(
            "/platform/rental-intents",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json=payload,
        )
        assert blocked.status_code == 403
        assert blocked.json()["detail"]["code"] == "platform_email_verification_required"
        assert _row_counts() == counts_before

        cross_account = other.post(
            "/platform/auth/email-verification/confirm",
            json={"token": owner_token},
        )
        assert cross_account.status_code == 400
        assert cross_account.json()["detail"]["code"] == (
            "platform_email_verification_invalid"
        )

        confirmed = owner.post(
            "/platform/auth/email-verification/confirm",
            json={"token": owner_token},
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["email_verified"] is True
        assert owner.get("/platform/auth/me").json()["email"] == owner_email

        original_other_token = str(other_body["development_verification_token"])
        resent = other.post("/platform/auth/email-verification/resend")
        assert resent.status_code == 200
        assert resent.json()["status"] == "development"
        assert resent.json()["verification_token_expires_at"] is not None
        assert _response_datetime(
            resent.json()["verification_token_expires_at"]
        ) <= _response_datetime(other_body["unverified_account_expires_at"])
        replacement_token = resent.json()["development_verification_token"]
        assert replacement_token and replacement_token != original_other_token
        invalidated = other.post(
            "/platform/auth/email-verification/confirm",
            json={"token": original_other_token},
        )
        assert invalidated.status_code == 400
        assert (
            other.post(
                "/platform/auth/email-verification/confirm",
                json={"token": replacement_token},
            ).status_code
            == 200
        )


def test_concurrent_email_confirmation_is_one_way_and_idempotent() -> None:
    settings = get_settings()
    with TestClient(app) as registering:
        _, registration = _register(registering, "verify-race", verify=False)
        session_token = registering.cookies.get(settings.platform_session_cookie)
        verification_token = registration["development_verification_token"]
        account_id = uuid.UUID(str(registration["id"]))
    assert session_token and verification_token
    barrier = threading.Barrier(2)

    def confirm() -> tuple[int, dict[str, object]]:
        with TestClient(
            app,
            cookies={settings.platform_session_cookie: session_token},
        ) as client:
            barrier.wait(timeout=10)
            response = client.post(
                "/platform/auth/email-verification/confirm",
                json={"token": verification_token},
            )
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: confirm(), range(2)))

    assert [result[0] for result in results] == [200, 200]
    assert all(result[1]["email_verified"] is True for result in results)
    with SessionLocal() as db:
        account = db.get(PlatformAccount, account_id)
        assert account is not None and account.email_verified_at is not None
        successful_audits = db.scalar(
            select(func.count())
            .select_from(PlatformAuditEvent)
            .where(
                PlatformAuditEvent.actor_account_id == account_id,
                PlatformAuditEvent.action == "platform_account.email_verification_confirmed",
                PlatformAuditEvent.outcome == "succeeded",
            )
        )
        assert successful_audits == 1


def test_verification_delivery_failure_keeps_recoverable_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed_attempts: list[tuple[str, str, datetime]] = []

    async def fail_delivery(
        attempted_email: str,
        attempted_token: str,
        attempted_expires_at: datetime,
    ) -> None:
        failed_attempts.append(
            (attempted_email, attempted_token, attempted_expires_at)
        )
        raise RuntimeError("simulated SMTP outage")

    monkeypatch.setattr(platform_auth.settings, "app_env", "staging")
    monkeypatch.setattr(platform_auth, "send_platform_email_verification", fail_delivery)
    email = f"platform-delivery-{uuid.uuid4().hex}@example.com"
    with TestClient(app, base_url="https://testserver") as client:
        response = client.post(
            "/platform/auth/register",
            json={"email": email, "password": PASSWORD, "captcha_token": "local-captcha-pass"},
        )
        assert response.status_code == 201, response.text
        assert response.json()["verification_delivery"] == "unavailable"
        assert response.json()["verification_token_expires_at"] is None
        assert response.json()["development_verification_token"] is None
        assert client.get("/platform/auth/me").status_code == 200
        assert len(failed_attempts) == 1
        assert failed_attempts[0][0] == email

        with SessionLocal() as db:
            account = db.scalar(select(PlatformAccount).where(PlatformAccount.email == email))
            assert account is not None and account.email_verified_at is None
            failed_token = db.scalar(
                select(PlatformEmailVerificationToken).where(
                    PlatformEmailVerificationToken.account_id == account.id,
                    PlatformEmailVerificationToken.token_hash
                    == token_hash(failed_attempts[0][1]),
                )
            )
            assert failed_token is not None
            assert failed_token.state == "delivery_failed"
            assert failed_token.used_at is not None
            assert failed_token.expires_at <= account.email_verification_expires_at
            assert not list(
                db.scalars(
                    select(PlatformEmailVerificationToken).where(
                        PlatformEmailVerificationToken.account_id == account.id,
                        PlatformEmailVerificationToken.state.in_(
                            ("active", "pending_delivery")
                        ),
                    )
                )
            )

        delivered: list[tuple[str, str, datetime]] = []

        async def recover_delivery(
            recovered_email: str,
            recovered_token: str,
            recovered_expires_at: datetime,
        ) -> None:
            delivered.append(
                (recovered_email, recovered_token, recovered_expires_at)
            )

        monkeypatch.setattr(
            platform_auth,
            "send_platform_email_verification",
            recover_delivery,
        )
        recovered = client.post("/platform/auth/email-verification/resend")
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["status"] == "sent"
        assert recovered.json()["verification_token_expires_at"] is not None
        assert recovered.json()["development_verification_token"] is None
        assert len(delivered) == 1
        recovered_token = delivered[0][1]
        with SessionLocal() as db:
            account = db.scalar(select(PlatformAccount).where(PlatformAccount.email == email))
            assert account is not None
            active = db.scalar(
                select(PlatformEmailVerificationToken).where(
                    PlatformEmailVerificationToken.account_id == account.id,
                    PlatformEmailVerificationToken.state == "active",
                )
            )
            assert active is not None
            assert active.token_hash == token_hash(recovered_token)
            assert active.expires_at <= account.email_verification_expires_at

        confirmation = client.post(
            "/platform/auth/email-verification/confirm",
            json={"token": recovered_token},
        )
        assert confirmation.status_code == 200, confirmation.text
        assert confirmation.json()["email_verified"] is True


def test_registration_delivery_lease_blocks_concurrent_resend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    email = f"platform-registration-lease-{uuid.uuid4().hex}@example.com"
    delivery_paused = threading.Event()
    allow_delivery = threading.Event()
    original_deliver = platform_auth._deliver_verification

    async def pause_after_phase_one(
        delivery_email: str,
        raw_token: str,
        expires_at: datetime,
    ) -> object:
        delivery_paused.set()
        assert allow_delivery.wait(timeout=10)
        return await original_deliver(delivery_email, raw_token, expires_at)

    monkeypatch.setattr(
        platform_auth,
        "_deliver_verification",
        pause_after_phase_one,
    )

    def register() -> tuple[int, str, dict[str, object], str | None]:
        with TestClient(app) as client:
            response = client.post(
                "/platform/auth/register",
                json={
                    "email": email,
                    "password": PASSWORD,
                    "captcha_token": "local-captcha-pass",
                },
            )
            return (
                response.status_code,
                response.text,
                response.json(),
                client.cookies.get(settings.platform_session_cookie),
            )

    with ThreadPoolExecutor(max_workers=1) as executor:
        registration_future = executor.submit(register)
        assert delivery_paused.wait(timeout=10)
        try:
            with SessionLocal() as db:
                account = db.scalar(
                    select(PlatformAccount).where(PlatformAccount.email == email)
                )
                assert account is not None
                pending = db.scalar(
                    select(PlatformEmailVerificationToken).where(
                        PlatformEmailVerificationToken.account_id == account.id,
                        PlatformEmailVerificationToken.state == "pending_delivery",
                    )
                )
                assert pending is not None
                assert db.scalar(
                    select(func.count())
                    .select_from(PlatformSession)
                    .where(
                        PlatformSession.account_id == account.id,
                        PlatformSession.revoked_at.is_(None),
                    )
                ) == 1

            with TestClient(app) as concurrent:
                login = concurrent.post(
                    "/platform/auth/login",
                    json={"email": email, "password": PASSWORD},
                )
                assert login.status_code == 200, login.text
                resend = concurrent.post("/platform/auth/email-verification/resend")
                assert resend.status_code == 409, resend.text
                assert resend.json()["detail"]["code"] == (
                    "platform_email_verification_delivery_in_progress"
                )
        finally:
            allow_delivery.set()
        status_code, response_text, registration, registration_session = (
            registration_future.result(timeout=15)
        )

    assert status_code == 201, response_text
    assert registration["verification_delivery"] == "development"
    assert registration["verification_token_expires_at"] is not None
    raw_token = str(registration["development_verification_token"])
    assert raw_token
    assert registration_session
    with SessionLocal() as db:
        account = db.scalar(select(PlatformAccount).where(PlatformAccount.email == email))
        assert account is not None
        active = db.scalar(
            select(PlatformEmailVerificationToken).where(
                PlatformEmailVerificationToken.account_id == account.id,
                PlatformEmailVerificationToken.state == "active",
            )
        )
        assert active is not None
        assert active.token_hash == token_hash(raw_token)
        assert active.expires_at <= account.email_verification_expires_at
        assert not list(
            db.scalars(
                select(PlatformEmailVerificationToken).where(
                    PlatformEmailVerificationToken.account_id == account.id,
                    PlatformEmailVerificationToken.state == "pending_delivery",
                )
            )
        )
    with TestClient(
        app,
        cookies={settings.platform_session_cookie: registration_session},
    ) as original_registration:
        assert original_registration.get("/platform/auth/me").status_code == 200
        confirmed = original_registration.post(
            "/platform/auth/email-verification/confirm",
            json={"token": raw_token},
        )
        assert confirmed.status_code == 200, confirmed.text


def test_failed_resend_preserves_previous_active_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivered: list[tuple[str, str, datetime]] = []

    async def fail_delivery(email: str, token: str, expires_at: datetime) -> None:
        delivered.append((email, token, expires_at))
        raise RuntimeError("simulated resend SMTP outage")

    settings = get_settings()
    with TestClient(app) as client:
        email, registration = _register(client, "failed-resend", verify=False)
        account_id = uuid.UUID(str(registration["id"]))
        original_token = str(registration["development_verification_token"])
        original_expiry = registration["verification_token_expires_at"]
        with SessionLocal() as db:
            original = db.scalar(
                select(PlatformEmailVerificationToken).where(
                    PlatformEmailVerificationToken.account_id == account_id,
                    PlatformEmailVerificationToken.state == "active",
                )
            )
            assert original is not None
            original_id = original.id
            original_hash = original.token_hash

        monkeypatch.setattr(platform_auth.settings, "app_env", "staging")
        monkeypatch.setattr(
            platform_auth,
            "send_platform_email_verification",
            fail_delivery,
        )
        failed = client.post("/platform/auth/email-verification/resend")
        assert failed.status_code == 200, failed.text
        assert failed.json() == {
            "status": "unavailable",
            "verification_token_expires_at": original_expiry,
            "development_verification_token": None,
        }
        assert len(delivered) == 1
        assert delivered[0][0] == email
        assert delivered[0][1] != original_token

        with SessionLocal() as db:
            active = db.scalar(
                select(PlatformEmailVerificationToken).where(
                    PlatformEmailVerificationToken.account_id == account_id,
                    PlatformEmailVerificationToken.state == "active",
                )
            )
            assert active is not None
            assert active.id == original_id
            assert active.token_hash == original_hash == token_hash(original_token)
            assert active.used_at is None
            failed_tokens = list(
                db.scalars(
                    select(PlatformEmailVerificationToken).where(
                        PlatformEmailVerificationToken.account_id == account_id,
                        PlatformEmailVerificationToken.state == "delivery_failed",
                    )
                )
            )
            assert len(failed_tokens) == 1
            assert failed_tokens[0].used_at is not None
            assert db.scalar(
                select(func.count())
                .select_from(PlatformEmailVerificationToken)
                .where(
                    PlatformEmailVerificationToken.account_id == account_id,
                    PlatformEmailVerificationToken.state == "pending_delivery",
                )
            ) == 0

        confirmed = client.post(
            "/platform/auth/email-verification/confirm",
            json={"token": original_token},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["email_verified"] is True
        assert settings.platform_session_cookie in client.cookies


def test_resend_near_account_expiry_does_not_issue_a_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "platform_unverified_account_hours", 0.01)
    with TestClient(app) as client:
        _, registration = _register(client, "closing-window", verify=False)
        account_id = uuid.UUID(str(registration["id"]))
        account_expiry = _response_datetime(
            registration["unverified_account_expires_at"]
        )
        token_expiry = _response_datetime(
            registration["verification_token_expires_at"]
        )
        assert token_expiry <= account_expiry
        with SessionLocal() as db:
            issued_before = set(
                db.scalars(
                    select(PlatformEmailVerificationToken.id).where(
                        PlatformEmailVerificationToken.account_id == account_id
                    )
                )
            )
            assert len(issued_before) == 1

        resend = client.post("/platform/auth/email-verification/resend")
        assert resend.status_code == 200, resend.text
        assert resend.json() == {
            "status": "unavailable",
            "verification_token_expires_at": registration[
                "verification_token_expires_at"
            ],
            "development_verification_token": None,
        }
        with SessionLocal() as db:
            issued_after = set(
                db.scalars(
                    select(PlatformEmailVerificationToken.id).where(
                        PlatformEmailVerificationToken.account_id == account_id
                    )
                )
            )
            assert issued_after == issued_before
            assert db.scalar(
                select(func.count())
                .select_from(PlatformEmailVerificationToken)
                .where(
                    PlatformEmailVerificationToken.account_id == account_id,
                    PlatformEmailVerificationToken.state == "pending_delivery",
                )
            ) == 0


def test_unauthenticated_verification_claim_secures_the_account() -> None:
    settings = get_settings()
    replacement_password = "MailboxOwnerReplacementPassword456"
    with TestClient(app) as attacker:
        email, registration = _register(attacker, "claim", verify=False)
        account_id = uuid.UUID(str(registration["id"]))
        verification_token = str(registration["development_verification_token"])
        attacker_session = attacker.cookies.get(settings.platform_session_cookie)
    assert attacker_session

    with TestClient(app) as mailbox_owner:
        assert mailbox_owner.cookies.get(settings.platform_session_cookie) is None
        claimed = mailbox_owner.post(
            "/platform/auth/email-verification/claim",
            json={
                "token": verification_token,
                "password": replacement_password,
                "captcha_token": "local-captcha-pass",
            },
        )
        assert claimed.status_code == 200, claimed.text
        assert claimed.json()["email"] == email
        assert claimed.json()["email_verified"] is True
        assert claimed.json()["unverified_account_expires_at"] is None
        replacement_session = mailbox_owner.cookies.get(settings.platform_session_cookie)
        assert replacement_session and replacement_session != attacker_session
        assert mailbox_owner.get("/platform/auth/me").status_code == 200

    with TestClient(
        app,
        cookies={settings.platform_session_cookie: attacker_session},
    ) as stale_attacker:
        assert stale_attacker.get("/platform/auth/me").status_code == 401

    with TestClient(app) as password_check:
        old_login = password_check.post(
            "/platform/auth/login",
            json={"email": email, "password": PASSWORD},
        )
        assert old_login.status_code == 401
        new_login = password_check.post(
            "/platform/auth/login",
            json={"email": email, "password": replacement_password},
        )
        assert new_login.status_code == 200, new_login.text
        assert password_check.get("/platform/auth/me").status_code == 200

    with SessionLocal() as db:
        account = db.get(PlatformAccount, account_id)
        assert account is not None
        assert account.email_verified_at is not None
        assert account.email_verification_expires_at is None
        assert verify_password(account.password_hash, replacement_password)
        assert not verify_password(account.password_hash, PASSWORD)
        verification = db.scalar(
            select(PlatformEmailVerificationToken).where(
                PlatformEmailVerificationToken.account_id == account_id,
                PlatformEmailVerificationToken.token_hash == token_hash(verification_token),
            )
        )
        assert verification is not None
        assert verification.state == "used"
        assert verification.used_at == account.email_verified_at
        attacker_record = db.scalar(
            select(PlatformSession).where(
                PlatformSession.account_id == account_id,
                PlatformSession.token_hash == token_hash(attacker_session),
            )
        )
        assert attacker_record is not None and attacker_record.revoked_at is not None
        replacement_record = db.scalar(
            select(PlatformSession).where(
                PlatformSession.account_id == account_id,
                PlatformSession.token_hash == token_hash(replacement_session),
            )
        )
        assert replacement_record is not None and replacement_record.revoked_at is None


def test_platform_rate_limit_identifier_never_contains_raw_email() -> None:
    email = "rate-limit-sensitive@example.com"
    identifier = platform_rate_limit_identifier("login-email", email)
    assert email not in identifier
    assert len(identifier) == 64
    assert identifier == platform_rate_limit_identifier("login-email", email)
    assert identifier != platform_rate_limit_identifier("verification-email", email)


def test_expired_unverified_registration_can_be_reclaimed_and_revokes_old_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "platform_unverified_account_hours", 0.0003)
    new_password = "ReplacementPlatformPassword456"
    with TestClient(app) as first:
        email, original = _register(first, "reclaim", verify=False)
        original_account_id = original["id"]
        old_session = first.cookies.get(settings.platform_session_cookie)
    assert old_session
    time.sleep(1.25)

    with TestClient(app) as client:
        expired_login = client.post(
            "/platform/auth/login",
            json={"email": email, "password": PASSWORD},
        )
        assert expired_login.status_code == 403
        assert expired_login.json()["detail"]["code"] == (
            "platform_email_verification_expired"
        )

        reclaimed = client.post(
            "/platform/auth/register",
            json={
                "email": email,
                "password": new_password,
                "captcha_token": "local-captcha-pass",
            },
        )
        assert reclaimed.status_code == 201, reclaimed.text
        assert reclaimed.json()["id"] == original_account_id
        assert reclaimed.json()["email_verified"] is False
        assert reclaimed.json()["unverified_account_expires_at"] is not None
        assert reclaimed.json()["verification_token_expires_at"] is not None
        assert reclaimed.json()["development_verification_token"]

    with TestClient(
        app,
        cookies={settings.platform_session_cookie: old_session},
    ) as stale:
        assert stale.get("/platform/auth/me").status_code == 401

    with TestClient(app) as current:
        assert current.post(
            "/platform/auth/login",
            json={"email": email, "password": PASSWORD},
        ).status_code == 401
        assert current.post(
            "/platform/auth/login",
            json={"email": email, "password": new_password},
        ).status_code == 200


def test_login_started_with_old_credentials_cannot_survive_expired_reclaim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "platform_unverified_account_hours", 0.0003)
    replacement_password = "ConcurrentReclaimReplacementPassword456"
    with TestClient(app) as registering:
        email, registration = _register(registering, "login-reclaim-race", verify=False)
    account_id = uuid.UUID(str(registration["id"]))

    login_validated = threading.Event()
    allow_login_commit = threading.Event()
    reclaim_started = threading.Event()
    original_issue_session = platform_auth._issue_session
    original_verify_captcha = platform_auth.verify_captcha

    def gated_issue_session(*args: object, **kwargs: object) -> object:
        if kwargs.get("action") == "platform_account.login":
            login_validated.set()
            assert allow_login_commit.wait(timeout=10)
        return original_issue_session(*args, **kwargs)

    async def observe_reclaim_captcha(token: str | None, request: Request) -> None:
        await original_verify_captcha(token, request)
        if request.url.path == "/platform/auth/register":
            reclaim_started.set()

    monkeypatch.setattr(platform_auth, "_issue_session", gated_issue_session)
    monkeypatch.setattr(platform_auth, "verify_captcha", observe_reclaim_captcha)

    def old_password_login() -> tuple[int, str, str | None]:
        with TestClient(app) as client:
            response = client.post(
                "/platform/auth/login",
                json={"email": email, "password": PASSWORD},
            )
            return (
                response.status_code,
                response.text,
                client.cookies.get(settings.platform_session_cookie),
            )

    def reclaim() -> tuple[int, str, str | None]:
        with TestClient(app) as client:
            response = client.post(
                "/platform/auth/register",
                json={
                    "email": email,
                    "password": replacement_password,
                    "captcha_token": "local-captcha-pass",
                },
            )
            return (
                response.status_code,
                response.text,
                client.cookies.get(settings.platform_session_cookie),
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        login_future = executor.submit(old_password_login)
        assert login_validated.wait(timeout=10)
        time.sleep(1.25)
        monkeypatch.setattr(settings, "platform_unverified_account_hours", 24)
        reclaim_future = executor.submit(reclaim)
        assert reclaim_started.wait(timeout=10)
        allow_login_commit.set()
        login_status, login_text, old_credential_session = login_future.result(timeout=15)
        reclaim_status, reclaim_text, reclaim_session = reclaim_future.result(timeout=15)

    assert login_status in {200, 401, 403}, login_text
    assert reclaim_status == 201, reclaim_text
    assert reclaim_session
    if login_status == 200:
        assert old_credential_session
        with TestClient(
            app,
            cookies={settings.platform_session_cookie: old_credential_session},
        ) as stale_login:
            assert stale_login.get("/platform/auth/me").status_code == 401
        with SessionLocal() as db:
            stale_record = db.scalar(
                select(PlatformSession).where(
                    PlatformSession.account_id == account_id,
                    PlatformSession.token_hash == token_hash(old_credential_session),
                )
            )
            assert stale_record is not None and stale_record.revoked_at is not None

    with TestClient(app) as credentials:
        assert credentials.post(
            "/platform/auth/login",
            json={"email": email, "password": PASSWORD},
        ).status_code == 401
        assert credentials.post(
            "/platform/auth/login",
            json={"email": email, "password": replacement_password},
        ).status_code == 200


def test_resend_paused_before_lock_cannot_invalidate_reclaim_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "platform_unverified_account_hours", 0.0003)
    replacement_password = "ResendReclaimReplacementPassword456"
    with TestClient(app) as registering:
        email, registration = _register(registering, "resend-reclaim-race", verify=False)
        stale_session = registering.cookies.get(settings.platform_session_cookie)
    assert stale_session
    account_id = uuid.UUID(str(registration["id"]))
    original_token = str(registration["development_verification_token"])

    resend_before_account_lock = threading.Event()
    allow_resend_account_lock = threading.Event()
    original_enforce_rate_limit = platform_auth.enforce_rate_limit

    async def gate_resend_before_account_lock(
        key: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> None:
        await original_enforce_rate_limit(
            key,
            limit=limit,
            window_seconds=window_seconds,
        )
        if key.startswith("platform-email-verification-resend:ip:"):
            resend_before_account_lock.set()
            assert allow_resend_account_lock.wait(timeout=10)

    monkeypatch.setattr(
        platform_auth,
        "enforce_rate_limit",
        gate_resend_before_account_lock,
    )

    def resend() -> tuple[int, str]:
        with TestClient(
            app,
            cookies={settings.platform_session_cookie: stale_session},
        ) as client:
            response = client.post("/platform/auth/email-verification/resend")
            return response.status_code, response.text

    with ThreadPoolExecutor(max_workers=1) as executor:
        resend_future = executor.submit(resend)
        assert resend_before_account_lock.wait(timeout=10)
        time.sleep(1.25)
        monkeypatch.setattr(settings, "platform_unverified_account_hours", 24)
        with TestClient(app) as reclaiming:
            reclaimed = reclaiming.post(
                "/platform/auth/register",
                json={
                    "email": email,
                    "password": replacement_password,
                    "captcha_token": "local-captcha-pass",
                },
            )
            assert reclaimed.status_code == 201, reclaimed.text
            replacement_token = str(reclaimed.json()["development_verification_token"])
            assert replacement_token and replacement_token != original_token
            replacement_session = reclaiming.cookies.get(settings.platform_session_cookie)
            assert replacement_session
        allow_resend_account_lock.set()
        resend_status, resend_text = resend_future.result(timeout=15)

    assert resend_status == 401, resend_text
    with SessionLocal() as db:
        active = db.scalar(
            select(PlatformEmailVerificationToken).where(
                PlatformEmailVerificationToken.account_id == account_id,
                PlatformEmailVerificationToken.state == "active",
            )
        )
        assert active is not None
        assert active.token_hash == token_hash(replacement_token)
        assert active.used_at is None
        original = db.scalar(
            select(PlatformEmailVerificationToken).where(
                PlatformEmailVerificationToken.account_id == account_id,
                PlatformEmailVerificationToken.token_hash == token_hash(original_token),
            )
        )
        assert original is not None
        assert original.state == "superseded"
        assert db.scalar(
            select(func.count())
            .select_from(PlatformEmailVerificationToken)
            .where(
                PlatformEmailVerificationToken.account_id == account_id,
                PlatformEmailVerificationToken.state == "pending_delivery",
            )
        ) == 0

    with TestClient(
        app,
        cookies={settings.platform_session_cookie: replacement_session},
    ) as mailbox_owner:
        confirmed = mailbox_owner.post(
            "/platform/auth/email-verification/confirm",
            json={"token": replacement_token},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["email_verified"] is True


def test_rental_intent_is_exact_atomic_idempotent_and_owner_scoped() -> None:
    publication = _published_template()
    payload = _intent_payload(publication)
    idempotency_key = str(uuid.uuid4())
    counts_before = _row_counts()

    with TestClient(app) as owner, TestClient(app) as stranger:
        _, owner_body = _register(owner, "rental-owner")
        _register(stranger, "rental-stranger")

        created = owner.post(
            "/platform/rental-intents",
            headers={"Idempotency-Key": idempotency_key},
            json=payload,
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["status"] == "awaiting_payment"
        assert body["reservation_active"] is True
        assert body["reservation_expires_at"] > body["created_at"]
        assert body["status_changed_at"] >= body["created_at"]
        assert body["expired_at"] is None
        assert body["next_action"] == "platform_billing_unavailable"
        assert body["tenant"]["status"] == "reserved"
        assert body["tenant"]["hosted_hostname"] == (
            f"{payload['requested_tenant_slug']}.{get_settings().platform_tenant_base_domain}"
        )
        assert body["template"]["version_id"] == str(publication["template_version_id"])
        assert body["legal_acceptance"]["agreement_version_id"] == str(
            publication["agreement_version_id"]
        )
        assert body["price_snapshot"] == {
            "price_cents": 4900,
            "currency": "CAD",
            "interval": "month",
        }
        assert body["platform_billing"] == {
            "status": "disabled",
            "checkout_available": False,
        }
        assert body["provisioning_status"] == "not_started"
        assert body["domain_status"] == "not_created"
        assert "provider" not in json.dumps(body).lower()
        assert created.headers["location"] == f"/platform/rentals/{body['id']}"

        detail = owner.get(created.headers["location"])
        assert detail.status_code == 200
        assert detail.json() == body
        assert stranger.get(created.headers["location"]).status_code == 404

        replay = owner.post(
            "/platform/rental-intents",
            headers={"Idempotency-Key": idempotency_key},
            json=payload,
        )
        assert replay.status_code == 200
        assert replay.headers["idempotency-replayed"] == "true"
        assert replay.json() == body

        changed = dict(payload, business_name="A Different Business")
        conflict = owner.post(
            "/platform/rental-intents",
            headers={"Idempotency-Key": idempotency_key},
            json=changed,
        )
        assert conflict.status_code == 409

        collision = stranger.post(
            "/platform/rental-intents",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json=payload,
        )
        assert collision.status_code == 409
        assert stranger.get("/platform/rentals").json()["rentals"] == []
        assert [item["id"] for item in owner.get("/platform/rentals").json()["rentals"]] == [
            body["id"]
        ]

    counts_after = _row_counts()
    assert counts_after[TenantReservation] == counts_before[TenantReservation] + 1
    assert counts_after[TenantMembership] == counts_before[TenantMembership] + 1
    assert counts_after[LegalAcceptance] == counts_before[LegalAcceptance] + 1
    assert counts_after[TemplateRental] == counts_before[TemplateRental] + 1
    assert counts_after[SiteDomain] == counts_before[SiteDomain]

    with SessionLocal() as db:
        rental = db.get(TemplateRental, uuid.UUID(body["id"]))
        assert rental is not None
        assert rental.account_id == uuid.UUID(str(owner_body["id"]))
        membership = db.scalar(
            select(TenantMembership).where(TenantMembership.tenant_id == rental.tenant_id)
        )
        assert membership is not None
        assert membership.role == "owner"
        assert membership.id == rental.owner_membership_id
        assert rental.owner_membership_role == "owner"
        audit = db.scalar(
            select(PlatformAuditEvent).where(
                PlatformAuditEvent.resource_type == "template_rental",
                PlatformAuditEvent.resource_id == rental.id,
            )
        )
        assert audit is not None
        serialized_audit = json.dumps(audit.detail)
        assert payload["business_name"] not in serialized_audit
        assert publication["agreement_sha256"] not in serialized_audit

        template = db.get(PlatformTemplate, uuid.UUID(str(publication["template_id"])))
        assert template is not None
        template.rental_price_cents = 9900
        db.commit()

    with TestClient(app) as owner_again:
        login = owner_again.post(
            "/platform/auth/login",
            json={
                "email": db_account_email(uuid.UUID(str(owner_body["id"]))),
                "password": PASSWORD,
            },
        )
        assert login.status_code == 200
        snapshot = owner_again.get(created.headers["location"])
        assert snapshot.status_code == 200
        assert snapshot.json()["price_snapshot"]["price_cents"] == 4900


def db_account_email(account_id: uuid.UUID) -> str:
    with SessionLocal() as db:
        email = db.scalar(select(PlatformAccount.email).where(PlatformAccount.id == account_id))
    assert email is not None
    return email


def test_rental_intent_rejects_stale_bindings_without_side_effects() -> None:
    publication = _published_template()
    base = _intent_payload(publication)
    with TestClient(app) as client:
        _register(client, "stale-offer")
        counts_before = _row_counts()
        attempts = (
            dict(base, template_version_id=str(uuid.uuid4())),
            dict(base, agreement_version_id=str(uuid.uuid4())),
            dict(base, agreement_sha256="0" * 64),
        )
        for payload in attempts:
            response = client.post(
                "/platform/rental-intents",
                headers={"Idempotency-Key": str(uuid.uuid4())},
                json=payload,
            )
            assert response.status_code == 409

        refused_consent = client.post(
            "/platform/rental-intents",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json=dict(base, accepted=False),
        )
        assert refused_consent.status_code == 422
        assert _row_counts() == counts_before


def test_rental_offer_bindings_and_legal_records_are_immutable() -> None:
    publication = _published_template()
    payload = _intent_payload(publication)
    with TestClient(app) as client:
        _register(client, "immutable")
        created = client.post(
            "/platform/rental-intents",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json=payload,
        )
        assert created.status_code == 201
    body = created.json()
    with SessionLocal() as db:
        audit_id = db.scalar(
            select(PlatformAuditEvent.id).where(
                PlatformAuditEvent.resource_type == "template_rental",
                PlatformAuditEvent.resource_id == uuid.UUID(body["id"]),
            )
        )
    assert audit_id is not None

    mutations = (
        update(PlatformTemplateVersion)
        .where(PlatformTemplateVersion.id == uuid.UUID(str(publication["template_version_id"])))
        .values(source_commit="f" * 40),
        update(RentalAgreementVersion)
        .where(RentalAgreementVersion.id == uuid.UUID(str(publication["agreement_version_id"])))
        .values(title="Changed terms"),
        update(LegalAcceptance)
        .where(LegalAcceptance.id == uuid.UUID(body["legal_acceptance"]["id"]))
        .values(ip_address="203.0.113.9"),
        update(TemplateRental)
        .where(TemplateRental.id == uuid.UUID(body["id"]))
        .values(price_cents=1),
        update(PlatformAuditEvent)
        .where(PlatformAuditEvent.id == audit_id)
        .values(outcome="failed"),
    )
    for mutation in mutations:
        with SessionLocal() as db, pytest.raises(SQLAlchemyError):
            db.execute(mutation)
            db.commit()


def test_database_rejects_cross_account_tenant_binding_and_identity_mutation() -> None:
    publication = _published_template()
    suffix = uuid.uuid4().hex
    payload = _intent_payload(publication, tenant_slug=f"bound-{suffix[:12]}")
    with TestClient(app) as owner, TestClient(app) as intruder:
        _, owner_account = _register(owner, "binding-owner")
        _, intruder_account = _register(intruder, "binding-intruder")
        created = owner.post(
            "/platform/rental-intents",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json=payload,
        )
        assert created.status_code == 201, created.text

    owner_id = uuid.UUID(str(owner_account["id"]))
    intruder_id = uuid.UUID(str(intruder_account["id"]))
    legitimate_rental_id = uuid.UUID(created.json()["id"])
    with SessionLocal() as db:
        legitimate_rental = db.get(TemplateRental, legitimate_rental_id)
        assert legitimate_rental is not None
        protected_tenant_id = legitimate_rental.tenant_id
        protected_membership_id = legitimate_rental.owner_membership_id

    tenant_id = uuid.uuid4()
    acceptance_id = uuid.uuid4()
    membership_id = uuid.uuid4()
    with SessionLocal() as db, pytest.raises(SQLAlchemyError):
        now = db.scalar(select(func.transaction_timestamp()))
        assert isinstance(now, datetime)
        db.add_all(
            [
                TenantReservation(
                    id=tenant_id,
                    slug=f"binding-{suffix[:12]}",
                    hosted_hostname=f"binding-{suffix[:12]}.apertures.online",
                    business_name="Binding Fixture",
                    status="reserved",
                ),
                LegalAcceptance(
                    id=acceptance_id,
                    account_id=intruder_id,
                    agreement_version_id=uuid.UUID(str(publication["agreement_version_id"])),
                    agreement_content_sha256=str(publication["agreement_sha256"]),
                    accepted_at=now,
                ),
            ]
        )
        db.flush()
        db.add(
            TenantMembership(
                id=membership_id,
                tenant_id=tenant_id,
                account_id=owner_id,
                role="owner",
                status="active",
            )
        )
        db.flush()
        db.add(
            TemplateRental(
                account_id=intruder_id,
                tenant_id=tenant_id,
                template_id=uuid.UUID(str(publication["template_id"])),
                template_version_id=uuid.UUID(str(publication["template_version_id"])),
                agreement_version_id=uuid.UUID(str(publication["agreement_version_id"])),
                legal_acceptance_id=acceptance_id,
                owner_membership_id=membership_id,
                owner_membership_role="owner",
                idempotency_key=uuid.uuid4(),
                request_fingerprint="a" * 64,
                status="awaiting_payment",
                price_cents=4900,
                currency="CAD",
                billing_interval="month",
                reservation_expires_at=now + timedelta(hours=24),
                status_changed_at=now,
                created_at=now,
            )
        )
        db.commit()

    protected_mutations = (
        update(TenantReservation)
        .where(TenantReservation.id == protected_tenant_id)
        .values(slug=f"changed-{suffix[:12]}"),
        delete(TenantReservation).where(TenantReservation.id == protected_tenant_id),
        update(TenantMembership)
        .where(TenantMembership.id == protected_membership_id)
        .values(role="member"),
        delete(TenantMembership).where(TenantMembership.id == protected_membership_id),
    )
    for mutation in protected_mutations:
        with SessionLocal() as db, pytest.raises(SQLAlchemyError):
            db.execute(mutation)
            db.commit()


def test_concurrent_same_key_same_payload_replays_one_atomic_intent() -> None:
    publication = _published_template()
    payload = _intent_payload(publication)
    idempotency_key = str(uuid.uuid4())
    settings = get_settings()
    with TestClient(app) as registering:
        _register(registering, "concurrent")
        raw_token = registering.cookies.get(settings.platform_session_cookie)
        assert raw_token

    barrier = threading.Barrier(2)

    def submit() -> tuple[int, str | None, dict[str, object]]:
        with TestClient(
            app,
            cookies={settings.platform_session_cookie: raw_token},
        ) as client:
            barrier.wait(timeout=10)
            response = client.post(
                "/platform/rental-intents",
                headers={"Idempotency-Key": idempotency_key},
                json=payload,
            )
            return (
                response.status_code,
                response.headers.get("idempotency-replayed"),
                response.json(),
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: submit(), range(2)))

    assert sorted(status for status, _, _ in results) == [200, 201]
    assert sorted(replayed for _, replayed, _ in results if replayed is not None) == ["true"]
    assert results[0][2] == results[1][2]
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(TemplateRental)
                .where(TemplateRental.idempotency_key == uuid.UUID(idempotency_key))
            )
            == 1
        )


def test_expired_rental_is_terminal_and_new_key_can_reuse_released_slug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publication = _published_template()
    tenant_slug = f"expiry-{uuid.uuid4().hex[:12]}"
    payload = _intent_payload(publication, tenant_slug=tenant_slug)
    settings = get_settings()
    monkeypatch.setattr(settings, "platform_rental_intent_hours", 0.0003)
    first_key = str(uuid.uuid4())

    with TestClient(app) as client:
        _register(client, "expiry")
        created = client.post(
            "/platform/rental-intents",
            headers={"Idempotency-Key": first_key},
            json=payload,
        )
        assert created.status_code == 201, created.text
        first_id = created.json()["id"]
        time.sleep(1.25)

        detail = client.get(created.headers["location"])
        assert detail.status_code == 200, detail.text
        expired = detail.json()
        assert expired["id"] == first_id
        assert expired["status"] == "expired"
        assert expired["tenant"]["status"] == "released"
        assert expired["reservation_active"] is False
        assert expired["expired_at"] is not None
        assert expired["next_action"] == "start_new_rental_request"
        with SessionLocal() as db:
            persisted = db.get(TemplateRental, uuid.UUID(first_id))
            assert persisted is not None and persisted.status == "expired"
            tenant = db.get(TenantReservation, persisted.tenant_id)
            assert tenant is not None and tenant.status == "released"
            assert db.scalar(
                select(func.count())
                .select_from(PlatformAuditEvent)
                .where(
                    PlatformAuditEvent.resource_id == persisted.id,
                    PlatformAuditEvent.action == "template_rental.intent_expired",
                )
            ) == 1

        replay = client.post(
            "/platform/rental-intents",
            headers={"Idempotency-Key": first_key},
            json=payload,
        )
        assert replay.status_code == 200, replay.text
        assert replay.headers["idempotency-replayed"] == "true"
        assert replay.json() == expired

        replacement = client.post(
            "/platform/rental-intents",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json=payload,
        )
        assert replacement.status_code == 201, replacement.text
        assert replacement.json()["id"] != first_id
        assert replacement.json()["tenant"]["slug"] == tenant_slug

    with SessionLocal() as db:
        rentals = list(
            db.scalars(
                select(TemplateRental)
                .join(TenantReservation, TenantReservation.id == TemplateRental.tenant_id)
                .where(TenantReservation.slug == tenant_slug)
                .order_by(TemplateRental.created_at)
            )
        )
        assert [rental.status for rental in rentals] == ["expired", "awaiting_payment"]
        assert db.scalar(
            select(func.count())
            .select_from(PlatformAuditEvent)
            .where(
                PlatformAuditEvent.resource_id == uuid.UUID(first_id),
                PlatformAuditEvent.action == "template_rental.intent_expired",
            )
        ) == 1


def test_concurrent_different_rentals_enforce_one_active_unpaid_quota() -> None:
    publication = _published_template()
    settings = get_settings()
    with TestClient(app) as registering:
        _, account = _register(registering, "quota-race")
        raw_token = registering.cookies.get(settings.platform_session_cookie)
    assert raw_token
    account_id = uuid.UUID(str(account["id"]))
    barrier = threading.Barrier(2)

    def submit(index: int) -> tuple[int, str | None, dict[str, object]]:
        payload = _intent_payload(
            publication,
            tenant_slug=f"quota-{index}-{uuid.uuid4().hex[:10]}",
        )
        with TestClient(
            app,
            cookies={settings.platform_session_cookie: raw_token},
        ) as client:
            barrier.wait(timeout=10)
            response = client.post(
                "/platform/rental-intents",
                headers={"Idempotency-Key": str(uuid.uuid4())},
                json=payload,
            )
            return response.status_code, response.headers.get("retry-after"), response.json()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(submit, range(2)))

    assert sorted(result[0] for result in results) == [201, 429]
    denied = next(result for result in results if result[0] == 429)
    assert denied[1] and int(denied[1]) >= 1
    assert denied[2]["detail"]["code"] == "active_unpaid_reservation_quota_exceeded"
    with SessionLocal() as db:
        assert db.scalar(
            select(func.count())
            .select_from(TemplateRental)
            .where(
                TemplateRental.account_id == account_id,
                TemplateRental.status == "awaiting_payment",
            )
        ) == 1


def test_database_rejects_unverified_and_zero_quota_rental_inserts() -> None:
    publication = _published_template()
    account_id = uuid.uuid4()
    suffix = uuid.uuid4().hex

    with SessionLocal() as db:
        now = db.scalar(select(func.transaction_timestamp()))
        assert isinstance(now, datetime)
        db.add(
            PlatformAccount(
                id=account_id,
                email=f"raw-rental-{suffix}@example.com",
                password_hash="unused-fixture-hash",
                email_verification_expires_at=now + timedelta(hours=24),
            )
        )
        db.commit()

    def add_raw_rental_graph(db: Session, label: str) -> None:
        graph_now = db.scalar(select(func.transaction_timestamp()))
        assert isinstance(graph_now, datetime)
        tenant_id = uuid.uuid4()
        membership_id = uuid.uuid4()
        acceptance_id = uuid.uuid4()
        db.add_all(
            [
                TenantReservation(
                    id=tenant_id,
                    slug=f"raw-{label}-{suffix[:8]}",
                    hosted_hostname=f"raw-{label}-{suffix[:8]}.apertures.online",
                    business_name="Raw insert fixture",
                    status="reserved",
                ),
                LegalAcceptance(
                    id=acceptance_id,
                    account_id=account_id,
                    agreement_version_id=uuid.UUID(str(publication["agreement_version_id"])),
                    agreement_content_sha256=str(publication["agreement_sha256"]),
                    accepted_at=graph_now,
                ),
            ]
        )
        db.flush()
        db.add(
            TenantMembership(
                id=membership_id,
                tenant_id=tenant_id,
                account_id=account_id,
                role="owner",
                status="active",
            )
        )
        db.flush()
        db.add(
            TemplateRental(
                account_id=account_id,
                tenant_id=tenant_id,
                template_id=uuid.UUID(str(publication["template_id"])),
                template_version_id=uuid.UUID(str(publication["template_version_id"])),
                agreement_version_id=uuid.UUID(str(publication["agreement_version_id"])),
                legal_acceptance_id=acceptance_id,
                owner_membership_id=membership_id,
                owner_membership_role="owner",
                idempotency_key=uuid.uuid4(),
                request_fingerprint="b" * 64,
                status="awaiting_payment",
                price_cents=4900,
                currency="CAD",
                billing_interval="month",
                reservation_expires_at=graph_now + timedelta(hours=24),
                status_changed_at=graph_now,
                created_at=graph_now,
            )
        )

    with SessionLocal() as db, pytest.raises(SQLAlchemyError):
        add_raw_rental_graph(db, "unverified")
        db.commit()

    with SessionLocal() as db:
        account = db.get(PlatformAccount, account_id)
        assert account is not None
        issued_at = db.scalar(select(func.transaction_timestamp()))
        assert isinstance(issued_at, datetime)
        verification = PlatformEmailVerificationToken(
            account_id=account.id,
            token_hash=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
            expires_at=issued_at + timedelta(hours=1),
            state="pending_delivery",
            created_at=issued_at,
        )
        db.add(verification)
        db.flush()
        verification.state = "active"
        db.flush()
        verified_at = issued_at
        account.email_verified_at = verified_at
        account.email_verification_expires_at = None
        account.active_unpaid_reservation_limit = 0
        db.flush()
        verification.state = "used"
        verification.used_at = verified_at
        db.commit()

    with SessionLocal() as db, pytest.raises(SQLAlchemyError):
        add_raw_rental_graph(db, "zero-quota")
        db.commit()

    with SessionLocal() as db:
        assert db.scalar(
            select(func.count())
            .select_from(TemplateRental)
            .where(TemplateRental.account_id == account_id)
        ) == 0
