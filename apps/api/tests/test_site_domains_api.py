import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update

import app.routes.site_domains as site_domains_route
from app.auth import hash_password
from app.config import get_settings
from app.custom_domain_provider import (
    DomainDnsRecord,
    DomainProviderError,
    DomainProviderNotFound,
    ProviderHostname,
)
from app.db import SessionLocal
from app.main import app
from app.models import Admin, AuditLog, SiteBrandConfiguration, SiteDomain, SiteDomainStatus
from app.site_domain_service import platform_hostname, preferred_public_origin


class FakeDomainProvider:
    def __init__(self) -> None:
        self.active = False
        self.fail_next_publish = False
        self.fail_publish_hostname: str | None = None
        self.fail_delete_allowlist = False
        self.fail_delete_hostname = False
        self.fail_turnstile = False
        self.hostname_not_found = False
        self.turnstile_calls: list[tuple[set[str], set[str]]] = []
        self.events: list[tuple[str, str]] = []

    def _hostname(self, hostname: str) -> ProviderHostname:
        return ProviderHostname(
            id="d" * 32,
            hostname=hostname,
            hostname_status="active" if self.active else "pending",
            ssl_status="active" if self.active else "pending_validation",
            dns_records=(
                DomainDnsRecord(
                    type="TXT",
                    name=f"_cf-custom-hostname.{hostname}",
                    value="ownership-value",
                    purpose="ownership",
                ),
            ),
        )

    def create_hostname(self, hostname: str) -> ProviderHostname:
        self.events.append(("hostname-create", hostname))
        return self._hostname(hostname)

    def get_hostname(self, _provider_hostname_id: str) -> ProviderHostname:
        if self.hostname_not_found:
            raise DomainProviderNotFound("provider_hostname_not_found")
        return self._hostname("watch.customer.com")

    def delete_hostname(self, _provider_hostname_id: str) -> None:
        self.events.append(("hostname-delete", "watch.customer.com"))
        if self.fail_delete_hostname:
            raise DomainProviderError("provider_unavailable")

    def publish_domain_allowlist(self, hostname: str, _payload) -> None:
        self.events.append(("kv-put", hostname))
        if self.fail_next_publish or self.fail_publish_hostname == hostname:
            self.fail_next_publish = False
            raise DomainProviderError("provider_unavailable")

    def delete_domain_allowlist(self, hostname: str) -> None:
        self.events.append(("kv-delete", hostname))
        if self.fail_delete_allowlist:
            raise DomainProviderError("provider_unavailable")

    def reconcile_turnstile_domains(
        self, *, required: set[str], remove: set[str] | None = None
    ) -> tuple[str, ...]:
        removed = remove or set()
        self.turnstile_calls.append((set(required), set(removed)))
        self.events.append(("turnstile", ",".join(sorted(required))))
        if self.fail_turnstile:
            raise DomainProviderError("turnstile_unavailable")
        return tuple(sorted(required))


@pytest.fixture(autouse=True)
def _isolate_preexisting_active_admins():
    with SessionLocal() as db:
        active_admin_ids = list(db.scalars(select(Admin.id).where(Admin.is_active.is_(True))))
        if active_admin_ids:
            db.execute(
                update(Admin).where(Admin.id.in_(active_admin_ids)).values(is_active=False)
            )
            db.commit()
    try:
        yield
    finally:
        if active_admin_ids:
            with SessionLocal() as db:
                db.execute(update(Admin).where(Admin.id.in_(active_admin_ids)).values(is_active=True))
                db.commit()


def _new_admin(prefix: str) -> tuple[uuid.UUID, str, str]:
    email = f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"
    password = "CustomDomainOwner123"
    with SessionLocal() as db:
        admin = Admin(email=email, password_hash=hash_password(password))
        db.add(admin)
        db.commit()
        return admin.id, email, password


def _cleanup(*admin_ids: uuid.UUID) -> None:
    with SessionLocal() as db:
        db.execute(delete(SiteDomain))
        db.execute(delete(SiteBrandConfiguration))
        db.execute(delete(AuditLog).where(AuditLog.actor_id.in_(admin_ids)))
        db.execute(delete(Admin).where(Admin.id.in_(admin_ids)))
        db.commit()


def test_owner_custom_domain_lifecycle_and_edge_fail_closed(monkeypatch) -> None:
    owner_id, email, password = _new_admin("domain-owner")
    fake = FakeDomainProvider()
    settings = get_settings()

    def provider_contract():
        return fake, settings, "customers.apertures.online"

    monkeypatch.setattr("app.routes.site_domains._provider", provider_contract)

    try:
        with TestClient(app) as client:
            assert client.post(
                "/admin/auth/login", json={"email": email, "password": password}
            ).status_code == 200
            initial = client.get("/admin/site/domains")
            assert initial.status_code == 200
            assert initial.json()["primary_domain_id"] is None
            assert initial.json()["custom_domains_available"] is False
            public_initial = client.get("/site/domain")
            assert public_initial.json() == {
                "primary_origin": str(settings.web_origin).rstrip("/")
            }
            assert public_initial.headers["cache-control"].startswith("public, max-age=60")

            created = client.post(
                "/admin/site/domains", json={"hostname": "WATCH.Customer.com"}
            )
            assert created.status_code == 201, created.text
            created_domain = created.json()["domains"][0]
            assert created_domain["hostname"] == "watch.customer.com"
            assert created_domain["status"] == "pending_dns"
            assert created_domain["dns_records"][0] == {
                "type": "CNAME",
                "name": "watch.customer.com",
                "value": "customers.apertures.online",
                "purpose": "routing",
            }

            fake.active = True
            fake.fail_next_publish = True
            failed_activation = client.post(
                f"/admin/site/domains/{created_domain['id']}/refresh",
                json={"revision": created_domain["revision"]},
            )
            assert failed_activation.status_code == 503
            after_failure = client.get("/admin/site/domains").json()["domains"][0]
            assert after_failure["status"] == "pending_edge"
            assert after_failure["failure_reason"] == "provider_unavailable"

            activated = client.post(
                f"/admin/site/domains/{created_domain['id']}/refresh",
                json={"revision": after_failure["revision"]},
            )
            assert activated.status_code == 200, activated.text
            active = activated.json()["domains"][0]
            assert active["status"] == "active"
            assert not active["is_primary"]

            stale = client.post(
                f"/admin/site/domains/{active['id']}/make-primary",
                json={"revision": active["revision"] - 1},
            )
            assert stale.status_code == 409
            primary = client.post(
                f"/admin/site/domains/{active['id']}/make-primary",
                json={"revision": active["revision"]},
            )
            assert primary.status_code == 200, primary.text
            primary_domain = primary.json()["domains"][0]
            assert primary_domain["is_primary"]
            with SessionLocal() as db:
                assert preferred_public_origin(db) == "https://watch.customer.com"
            assert client.get("/site/domain").json() == {
                "primary_origin": "https://watch.customer.com"
            }

            event_count = len(fake.events)
            stale_platform = client.post(
                "/admin/site/domains/use-platform",
                json={"revision": primary.json()["revision"] - 1},
            )
            assert stale_platform.status_code == 409
            assert len(fake.events) == event_count

            def unavailable_provider():
                raise HTTPException(503, "Custom domains are not configured")

            monkeypatch.setattr(
                site_domains_route, "_provider", unavailable_provider
            )
            platform_failure = client.post(
                "/admin/site/domains/use-platform",
                json={"revision": primary.json()["revision"]},
            )
            assert platform_failure.status_code == 200, platform_failure.text
            platform_state = platform_failure.json()
            assert platform_state["primary_domain_id"] is None
            assert platform_state["domains"][0]["failure_reason"] == (
                "edge_reconciliation_required"
            )

            monkeypatch.setattr(
                site_domains_route, "_provider", provider_contract
            )
            platform_success = client.post(
                "/admin/site/domains/use-platform",
                json={"revision": platform_state["revision"]},
            )
            assert platform_success.status_code == 200, platform_success.text
            assert platform_success.json()["primary_domain_id"] is None
            primary_domain = platform_success.json()["domains"][0]
            assert primary_domain["hostname"] == "watch.customer.com"
            assert primary_domain["status"] == "active"
            assert primary_domain["is_primary"] is False
            assert client.get("/site/domain").json() == {
                "primary_origin": str(settings.web_origin).rstrip("/")
            }
            with SessionLocal() as db:
                assert preferred_public_origin(db) == str(settings.web_origin).rstrip("/")

            event_count = len(fake.events)
            mismatched_confirmation = client.delete(
                f"/admin/site/domains/{active['id']}",
                params={
                    "revision": primary_domain["revision"],
                    "confirmation": "other.customer.com",
                },
            )
            assert mismatched_confirmation.status_code == 409
            assert len(fake.events) == event_count
            removed = client.delete(
                f"/admin/site/domains/{active['id']}",
                params={
                    "revision": primary_domain["revision"],
                    "confirmation": "watch.customer.com",
                },
            )
            assert removed.status_code == 200, removed.text
            assert removed.json()["domains"] == []
            removal_events = fake.events[event_count:]
            assert removal_events[:2] == [
                ("kv-delete", "watch.customer.com"),
                ("hostname-delete", "watch.customer.com"),
            ]
            with SessionLocal() as db:
                assert preferred_public_origin(db) == str(settings.web_origin).rstrip("/")
    finally:
        _cleanup(owner_id)


def test_non_owner_cannot_list_or_mutate_site_domains(monkeypatch) -> None:
    owner_id, owner_email, password = _new_admin("domain-owner")
    other_id = None
    fake = FakeDomainProvider()
    monkeypatch.setattr(
        "app.routes.site_domains._provider",
        lambda: (fake, get_settings(), "customers.apertures.online"),
    )
    try:
        with TestClient(app) as owner_client:
            assert owner_client.post(
                "/admin/auth/login", json={"email": owner_email, "password": password}
            ).status_code == 200
            assert owner_client.get("/admin/site/domains").status_code == 200

        other_id, other_email, _ = _new_admin("domain-other")
        with TestClient(app) as other_client:
            assert other_client.post(
                "/admin/auth/login", json={"email": other_email, "password": password}
            ).status_code == 200
            assert other_client.get("/admin/site/domains").status_code == 403
            assert other_client.post(
                "/admin/site/domains", json={"hostname": "watch.customer.com"}
            ).status_code == 403
    finally:
        _cleanup(*[value for value in (owner_id, other_id) if value is not None])


def test_create_compensates_provider_hostname_when_local_persistence_fails(monkeypatch) -> None:
    owner_id, email, password = _new_admin("domain-compensation")
    fake = FakeDomainProvider()
    fake.fail_delete_hostname = True
    monkeypatch.setattr(
        site_domains_route,
        "_provider",
        lambda: (fake, get_settings(), "customers.apertures.online"),
    )

    def fail_persistence(*_args, **_kwargs) -> None:
        raise RuntimeError("simulated local persistence failure")

    monkeypatch.setattr(site_domains_route, "apply_provider_hostname", fail_persistence)
    try:
        with TestClient(app) as client:
            assert client.post(
                "/admin/auth/login", json={"email": email, "password": password}
            ).status_code == 200
            response = client.post(
                "/admin/site/domains", json={"hostname": "watch.customer.com"}
            )
            assert response.status_code == 500
        assert fake.events[:2] == [
            ("hostname-create", "watch.customer.com"),
            ("hostname-delete", "watch.customer.com"),
        ]
        with SessionLocal() as db:
            domain = db.scalar(
                select(SiteDomain).where(SiteDomain.hostname == "watch.customer.com")
            )
            assert domain is not None
            assert domain.status == SiteDomainStatus.provisioning
            assert domain.provider_hostname_id is None
    finally:
        _cleanup(owner_id)


def test_activation_publishes_candidate_last_and_flags_uncertain_compensation(
    monkeypatch,
) -> None:
    owner_id, email, password = _new_admin("domain-edge-order")
    fake = FakeDomainProvider()
    fake.active = True
    fake.fail_publish_hostname = "watch.customer.com"
    fake.fail_delete_allowlist = True
    monkeypatch.setattr(
        site_domains_route,
        "_provider",
        lambda: (fake, get_settings(), "customers.apertures.online"),
    )
    try:
        with TestClient(app) as client:
            assert client.post(
                "/admin/auth/login", json={"email": email, "password": password}
            ).status_code == 200
            assert client.get("/admin/site/domains").status_code == 200
            with SessionLocal() as db:
                configuration = db.get_one(SiteBrandConfiguration, 1)
                db.add(
                    SiteDomain(
                        id=uuid.uuid4(),
                        site_brand_configuration_id=1,
                        hostname="alpha.customer.com",
                        status=SiteDomainStatus.active,
                        is_primary=True,
                        provider="cloudflare",
                        provider_hostname_id="a" * 32,
                        dns_records=[],
                        revision=1,
                    )
                )
                configuration.domains_revision += 1
                db.commit()

            response = client.post(
                "/admin/site/domains", json={"hostname": "watch.customer.com"}
            )
            assert response.status_code == 503
            assert response.json()["detail"] == (
                "Edge admission could not be confirmed; reconciliation is required"
            )
            kv_events = [event for event in fake.events if event[0].startswith("kv-")]
            assert kv_events == [
                ("kv-put", "alpha.customer.com"),
                ("kv-put", "watch.customer.com"),
                ("kv-delete", "watch.customer.com"),
            ]
            domains = client.get("/admin/site/domains").json()["domains"]
            candidate = next(
                domain for domain in domains if domain["hostname"] == "watch.customer.com"
            )
            assert candidate["status"] == "pending_edge"
            assert candidate["failure_reason"] == "edge_reconciliation_required"
    finally:
        _cleanup(owner_id)


def test_captcha_activation_fails_closed_before_edge_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id, email, password = _new_admin("domain-turnstile")
    fake = FakeDomainProvider()
    fake.active = True
    fake.fail_turnstile = True
    settings = get_settings()
    monkeypatch.setattr(settings, "captcha_required", True)
    monkeypatch.setattr(
        site_domains_route,
        "_provider",
        lambda: (fake, settings, "customers.apertures.online"),
    )
    try:
        with TestClient(app) as client:
            assert client.post(
                "/admin/auth/login", json={"email": email, "password": password}
            ).status_code == 200
            response = client.post(
                "/admin/site/domains", json={"hostname": "watch.customer.com"}
            )
            assert response.status_code == 503
            assert not any(event[0] == "kv-put" for event in fake.events)
            required, removed = fake.turnstile_calls[0]
            assert required == {platform_hostname(settings), "watch.customer.com"}
            assert removed == set()
            domain = client.get("/admin/site/domains").json()["domains"][0]
            assert domain["status"] == "pending_edge"
            assert domain["failure_reason"] == "turnstile_unavailable"

            fake.fail_turnstile = False
            event_count = len(fake.events)
            activated = client.post(
                f"/admin/site/domains/{domain['id']}/refresh",
                json={"revision": domain["revision"]},
            )
            assert activated.status_code == 200, activated.text
            active = activated.json()["domains"][0]
            assert active["status"] == "active"
            assert [event[0] for event in fake.events[event_count:]][:2] == [
                "turnstile",
                "kv-put",
            ]

            event_count = len(fake.events)
            removed_response = client.delete(
                f"/admin/site/domains/{active['id']}",
                params={
                    "revision": active["revision"],
                    "confirmation": "watch.customer.com",
                },
            )
            assert removed_response.status_code == 200, removed_response.text
            assert [event[0] for event in fake.events[event_count:]][:3] == [
                "kv-delete",
                "turnstile",
                "hostname-delete",
            ]
            required, removed = fake.turnstile_calls[-1]
            assert required == {platform_hostname(settings)}
            assert removed == {"watch.customer.com"}
    finally:
        _cleanup(owner_id)


def test_authoritative_provider_loss_revokes_active_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id, email, password = _new_admin("domain-provider-loss")
    fake = FakeDomainProvider()
    fake.active = True
    monkeypatch.setattr(
        site_domains_route,
        "_provider",
        lambda: (fake, get_settings(), "customers.apertures.online"),
    )
    try:
        with TestClient(app) as client:
            assert client.post(
                "/admin/auth/login", json={"email": email, "password": password}
            ).status_code == 200
            created = client.post(
                "/admin/site/domains", json={"hostname": "watch.customer.com"}
            )
            assert created.status_code == 201, created.text
            active = created.json()["domains"][0]
            assert active["status"] == "active"

            fake.hostname_not_found = True
            event_count = len(fake.events)
            refreshed = client.post(
                f"/admin/site/domains/{active['id']}/refresh",
                json={"revision": active["revision"]},
            )
            assert refreshed.status_code == 200, refreshed.text
            lost = refreshed.json()["domains"][0]
            assert lost["status"] == "failed"
            assert lost["failure_reason"] == "provider_hostname_not_found"
            assert ("kv-delete", "watch.customer.com") in fake.events[event_count:]
            with SessionLocal() as db:
                assert preferred_public_origin(db) == str(get_settings().web_origin).rstrip("/")
    finally:
        _cleanup(owner_id)
