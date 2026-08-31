import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update

from app.auth import hash_password
from app.db import SessionLocal
from app.main import app
from app.models import (
    Admin,
    AuditLog,
    Plan,
    SiteBrandConfiguration,
    ViewerPaymentConnection,
)
from app.site_brand_service import default_config


@dataclass(frozen=True)
class OwnerFixture:
    owner_id: uuid.UUID
    owner_email: str
    other_id: uuid.UUID
    other_email: str
    password: str
    code_prefix: str


def _brand_snapshot() -> dict[str, object]:
    return {
        "schema_version": 1,
        **default_config().model_dump(mode="json"),
    }


@pytest.fixture
def viewer_plan_owner() -> Iterator[OwnerFixture]:
    suffix = uuid.uuid4().hex[:10]
    password = "ViewerPlanOwnerPassword123"
    owner_email = f"viewer-plan-owner-{suffix}@example.com"
    other_email = f"viewer-plan-other-{suffix}@example.com"
    with SessionLocal() as db:
        owner = Admin(email=owner_email, password_hash=hash_password(password))
        other = Admin(email=other_email, password_hash=hash_password(password))
        db.add_all([owner, other])
        db.flush()
        fixture = OwnerFixture(
            owner_id=owner.id,
            owner_email=owner_email,
            other_id=other.id,
            other_email=other_email,
            password=password,
            code_prefix=f"owner-{suffix}",
        )
        db.add(
            SiteBrandConfiguration(
                id=1,
                owner_admin_id=owner.id,
                draft_config=_brand_snapshot(),
                revision=0,
                current_step=1,
                completed_steps=[],
            )
        )
        db.commit()

    try:
        yield fixture
    finally:
        with SessionLocal() as db:
            db.execute(
                delete(ViewerPaymentConnection).where(
                    ViewerPaymentConnection.owner_admin_id == fixture.owner_id
                )
            )
            db.execute(delete(Plan).where(Plan.code.like(f"{fixture.code_prefix}%")))
            db.execute(delete(SiteBrandConfiguration).where(SiteBrandConfiguration.id == 1))
            db.execute(
                delete(AuditLog).where(AuditLog.actor_id.in_([fixture.owner_id, fixture.other_id]))
            )
            db.execute(delete(Admin).where(Admin.id.in_([fixture.owner_id, fixture.other_id])))
            db.commit()


def _login(client: TestClient, email: str, password: str) -> None:
    response = client.post(
        "/admin/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text


def _payload(code: str) -> dict[str, object]:
    return {
        "code": code,
        "name": "Cinema Monthly",
        "description": "Two streams with the complete tenant catalog.",
        "price_cents": 1299,
        "currency": "CAD",
        "interval": "month",
        "max_streams": 2,
        "max_resolution": "1080p",
    }


def _assert_no_store(response) -> None:
    assert response.headers["cache-control"] == ("private, no-store, max-age=0, must-revalidate")
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["expires"] == "0"
    assert response.headers["vary"] == "Cookie"


def test_viewer_plan_api_is_owner_only_and_never_cached(viewer_plan_owner: OwnerFixture) -> None:
    fixture = viewer_plan_owner
    payload = _payload(f"{fixture.code_prefix}-monthly")

    with TestClient(app) as anonymous:
        assert anonymous.get("/admin/viewer-plans").status_code == 401
        assert anonymous.post("/admin/viewer-plans", json=payload).status_code == 401
        assert (
            anonymous.post(
                f"/admin/viewer-plans/{uuid.uuid4()}/archive",
                json={"confirmation_code": "unknown-plan"},
            ).status_code
            == 401
        )

    with TestClient(app) as owner:
        _login(owner, fixture.owner_email, fixture.password)
        listed = owner.get("/admin/viewer-plans")
        assert listed.status_code == 200, listed.text
        _assert_no_store(listed)

        created = owner.post("/admin/viewer-plans", json=payload)
        assert created.status_code == 201, created.text
        _assert_no_store(created)
        plan_id = created.json()["id"]
        assert created.json() == {
            "id": plan_id,
            **payload,
            "is_active": True,
            "created_at": created.json()["created_at"],
            "updated_at": created.json()["updated_at"],
        }

        listed = owner.get("/admin/viewer-plans")
        assert any(item["id"] == plan_id for item in listed.json())
        immutable = owner.patch(
            f"/admin/viewer-plans/{plan_id}",
            json={"price_cents": 1},
        )
        assert immutable.status_code == 404

        assert owner.post(f"/admin/viewer-plans/{plan_id}/archive").status_code == 422
        mismatch = owner.post(
            f"/admin/viewer-plans/{plan_id}/archive",
            json={"confirmation_code": f"{payload['code']}-wrong"},
        )
        assert mismatch.status_code == 422
        assert "does not match" in mismatch.json()["detail"]
        extra_field = owner.post(
            f"/admin/viewer-plans/{plan_id}/archive",
            json={"confirmation_code": payload["code"], "confirm": True},
        )
        assert extra_field.status_code == 422

        archived = owner.post(
            f"/admin/viewer-plans/{plan_id}/archive",
            json={"confirmation_code": payload["code"]},
        )
        assert archived.status_code == 200, archived.text
        _assert_no_store(archived)
        assert archived.json()["is_active"] is False
        archived_again = owner.post(
            f"/admin/viewer-plans/{plan_id}/archive",
            json={"confirmation_code": payload["code"]},
        )
        assert archived_again.status_code == 200
        assert archived_again.json()["is_active"] is False

    with TestClient(app) as other:
        _login(other, fixture.other_email, fixture.password)
        assert other.get("/admin/viewer-plans").status_code == 403
        assert (
            other.post(
                "/admin/viewer-plans",
                json=_payload(f"{fixture.code_prefix}-forbidden"),
            ).status_code
            == 403
        )
        assert (
            other.post(
                f"/admin/viewer-plans/{plan_id}/archive",
                json={"confirmation_code": payload["code"]},
            ).status_code
            == 403
        )

    with SessionLocal() as db:
        audits = list(
            db.scalars(
                select(AuditLog)
                .where(
                    AuditLog.actor_id == fixture.owner_id,
                    AuditLog.action.in_(["viewer_plan.created", "viewer_plan.archived"]),
                )
                .order_by(AuditLog.created_at)
            )
        )
        assert [item.action for item in audits] == [
            "viewer_plan.created",
            "viewer_plan.archived",
        ]
        assert all(item.detail["plan_id"] == plan_id for item in audits)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("code", "Uppercase-Code"),
        ("code", "bad_code"),
        ("code", "-bad-code"),
        ("name", "   "),
        ("name", "Bad\nName"),
        ("description", ""),
        ("description", "Bad\u0085Description"),
        ("price_cents", 0),
        ("price_cents", -1),
        ("price_cents", "1299"),
        ("price_cents", 100_000_001),
        ("currency", "cad"),
        ("currency", "CA1"),
        ("currency", "JPY"),
        ("currency", "ZZZ"),
        ("interval", "week"),
        ("max_streams", 0),
        ("max_streams", 101),
        ("max_streams", "2"),
        ("max_resolution", "8K"),
    ],
)
def test_viewer_plan_creation_validates_immutable_terms(
    viewer_plan_owner: OwnerFixture,
    field: str,
    value: object,
) -> None:
    fixture = viewer_plan_owner
    payload = _payload(f"{fixture.code_prefix}-invalid")
    payload[field] = value
    with TestClient(app) as owner:
        _login(owner, fixture.owner_email, fixture.password)
        response = owner.post("/admin/viewer-plans", json=payload)
        assert response.status_code == 422, response.text

    with SessionLocal() as db:
        assert (
            db.scalar(select(func.count(Plan.id)).where(Plan.code.like(f"{fixture.code_prefix}%")))
            == 0
        )


def test_viewer_plan_code_cannot_be_reused(viewer_plan_owner: OwnerFixture) -> None:
    fixture = viewer_plan_owner
    payload = _payload(f"{fixture.code_prefix}-unique")
    with TestClient(app) as owner:
        _login(owner, fixture.owner_email, fixture.password)
        first = owner.post("/admin/viewer-plans", json=payload)
        assert first.status_code == 201, first.text
        duplicate = owner.post("/admin/viewer-plans", json=payload)
        assert duplicate.status_code == 409, duplicate.text
        assert "code already exists" in duplicate.json()["detail"]

        assert (
            owner.post(
                f"/admin/viewer-plans/{first.json()['id']}/archive",
                json={"confirmation_code": payload["code"]},
            ).status_code
            == 200
        )
        reused_after_archive = owner.post("/admin/viewer-plans", json=payload)
        assert reused_after_archive.status_code == 409

    with SessionLocal() as db:
        assert db.scalar(select(func.count(Plan.id)).where(Plan.code == payload["code"])) == 1


def test_last_plan_cannot_be_archived_while_subscription_access_is_required(
    viewer_plan_owner: OwnerFixture,
) -> None:
    fixture = viewer_plan_owner
    with SessionLocal() as db:
        original_states = dict(db.execute(select(Plan.id, Plan.is_active)).all())
        db.execute(update(Plan).values(is_active=False))
        db.commit()

    target_code = f"{fixture.code_prefix}-required"
    replacement_code = f"{fixture.code_prefix}-replacement"
    try:
        with TestClient(app) as owner:
            _login(owner, fixture.owner_email, fixture.password)
            target = owner.post("/admin/viewer-plans", json=_payload(target_code))
            assert target.status_code == 201, target.text
            target_id = target.json()["id"]

            with SessionLocal() as db:
                db.add(
                    ViewerPaymentConnection(
                        id=1,
                        owner_admin_id=fixture.owner_id,
                        provider="stripe_connect",
                        access_mode="subscription_required",
                        stripe_connected_account_id=f"acct_{uuid.uuid4().hex[:24]}",
                        livemode=False,
                        details_submitted=True,
                        charges_enabled=True,
                        payouts_enabled=True,
                        requirements_due=[],
                        revision=1,
                    )
                )
                db.commit()

            refused = owner.post(
                f"/admin/viewer-plans/{target_id}/archive",
                json={"confirmation_code": target_code},
            )
            assert refused.status_code == 409, refused.text
            assert "final plan" in refused.json()["detail"]
            with SessionLocal() as db:
                assert db.get_one(Plan, uuid.UUID(target_id)).is_active is True

            replacement = owner.post(
                "/admin/viewer-plans",
                json={
                    **_payload(replacement_code),
                    "interval": "year",
                    "price_cents": 12999,
                },
            )
            assert replacement.status_code == 201, replacement.text
            archived = owner.post(
                f"/admin/viewer-plans/{target_id}/archive",
                json={"confirmation_code": target_code},
            )
            assert archived.status_code == 200, archived.text
            assert archived.json()["is_active"] is False
            assert replacement.json()["is_active"] is True
    finally:
        with SessionLocal() as db:
            db.execute(
                delete(ViewerPaymentConnection).where(
                    ViewerPaymentConnection.owner_admin_id == fixture.owner_id
                )
            )
            db.execute(delete(Plan).where(Plan.code.in_([target_code, replacement_code])))
            for plan_id, is_active in original_states.items():
                db.execute(update(Plan).where(Plan.id == plan_id).values(is_active=is_active))
            db.commit()
