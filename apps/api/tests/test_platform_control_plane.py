import hashlib
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError
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
    PlatformSession,
    PlatformTemplate,
    PlatformTemplateVersion,
    RentalAgreementVersion,
    TemplateRental,
    TenantMembership,
    TenantReservation,
)
from app.platform_schemas import TemplatePreviewAsset
from app.platform_security import require_platform_origin
from app.routes import platform_auth

PASSWORD = "StrongPlatformPassword123"
API_ROOT = Path(__file__).resolve().parents[1]


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


def _register(client: TestClient, label: str) -> tuple[str, dict[str, object]]:
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
    return email, response.json()


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

        email, account_body = _register(client, "auth")
        assert account_body["email"] == email
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
            actions = set(
                db.scalars(
                    select(PlatformAuditEvent.action).where(
                        PlatformAuditEvent.actor_account_id == account.id
                    )
                )
            )
            assert {"platform_account.registered", "platform_account.login"} <= actions

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
        assert replay.status_code == 201
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
    owner_id = uuid.uuid4()
    intruder_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    acceptance_id = uuid.uuid4()
    suffix = uuid.uuid4().hex
    with SessionLocal() as db:
        db.add_all(
            [
                PlatformAccount(
                    id=owner_id,
                    email=f"binding-owner-{suffix}@example.com",
                    password_hash="unused-fixture-hash",
                ),
                PlatformAccount(
                    id=intruder_id,
                    email=f"binding-intruder-{suffix}@example.com",
                    password_hash="unused-fixture-hash",
                ),
            ]
        )
        db.commit()
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
                    accepted_at=datetime.now(UTC),
                ),
            ]
        )
        db.flush()
        membership = TenantMembership(
            tenant_id=tenant_id,
            account_id=owner_id,
            role="owner",
            status="active",
        )
        db.add(membership)
        db.commit()
        membership_id = membership.id

    with SessionLocal() as db, pytest.raises(SQLAlchemyError):
        db.add(
            TemplateRental(
                account_id=intruder_id,
                tenant_id=tenant_id,
                template_id=uuid.UUID(str(publication["template_id"])),
                template_version_id=uuid.UUID(str(publication["template_version_id"])),
                agreement_version_id=uuid.UUID(str(publication["agreement_version_id"])),
                legal_acceptance_id=acceptance_id,
                idempotency_key=uuid.uuid4(),
                request_fingerprint="a" * 64,
                status="awaiting_payment",
                price_cents=4900,
                currency="CAD",
                billing_interval="month",
            )
        )
        db.commit()

    protected_mutations = (
        update(TenantReservation)
        .where(TenantReservation.id == tenant_id)
        .values(slug=f"changed-{suffix[:12]}"),
        delete(TenantReservation).where(TenantReservation.id == tenant_id),
        update(TenantMembership).where(TenantMembership.id == membership_id).values(role="member"),
        delete(TenantMembership).where(TenantMembership.id == membership_id),
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

    assert [status for status, _, _ in results] == [201, 201]
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
