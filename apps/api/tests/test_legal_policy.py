import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from time import monotonic, sleep

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, text

from app.auth import hash_password
from app.db import SessionLocal
from app.legal_policy_schemas import LegalPolicyPutRequest
from app.legal_policy_service import put_configuration
from app.main import app
from app.models import Admin, AuditLog, LegalPolicyConfiguration, SiteBrandConfiguration
from app.site_brand_service import default_config


def _empty_payload(revision: int = 0) -> dict[str, object | None]:
    return {
        "revision": revision,
        "legal_operator_name": None,
        "country_code": None,
        "region": None,
        "support_email": None,
        "privacy_email": None,
        "copyright_email": None,
        "minimum_user_age": None,
        "governing_law_jurisdiction": None,
    }


def _brand_snapshot() -> dict[str, object]:
    return {
        "schema_version": 1,
        **default_config().model_dump(mode="json"),
    }


def test_legal_policy_draft_is_owner_only_revisioned_and_privacy_minimized() -> None:
    suffix = uuid.uuid4().hex[:10]
    password = "LegalPolicyTestPassword123"
    owner_email = f"legal-owner-{suffix}@example.com"
    other_email = f"legal-other-{suffix}@example.com"
    with SessionLocal() as db:
        owner = Admin(email=owner_email, password_hash=hash_password(password))
        other = Admin(email=other_email, password_hash=hash_password(password))
        db.add_all([owner, other])
        db.flush()
        owner_id = owner.id
        other_id = other.id
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
        with TestClient(app) as anonymous:
            assert anonymous.get("/admin/site/legal-policy").status_code == 401
            assert (
                anonymous.put("/admin/site/legal-policy", json=_empty_payload()).status_code == 401
            )

        with TestClient(app) as owner_client:
            login = owner_client.post(
                "/admin/auth/login",
                json={"email": owner_email, "password": password},
            )
            assert login.status_code == 200

            initial = owner_client.get("/admin/site/legal-policy")
            assert initial.status_code == 200, initial.text
            assert initial.headers["cache-control"] == (
                "private, no-store, max-age=0, must-revalidate"
            )
            assert initial.headers["pragma"] == "no-cache"
            assert initial.headers["vary"] == "Cookie"
            assert initial.json() == {
                "schema_version": 1,
                "revision": 0,
                "status": "draft",
                "updated_at": None,
                **{key: value for key, value in _empty_payload().items() if key != "revision"},
            }
            with SessionLocal() as db:
                assert db.get(LegalPolicyConfiguration, 1) is None

            blank_save = owner_client.put("/admin/site/legal-policy", json=_empty_payload())
            assert blank_save.status_code == 200
            assert blank_save.json()["revision"] == 0
            with SessionLocal() as db:
                assert db.get(LegalPolicyConfiguration, 1) is None
                assert (
                    db.scalar(
                        select(func.count(AuditLog.id)).where(
                            AuditLog.actor_id == owner_id,
                            AuditLog.action == "legal_policy.draft.updated",
                        )
                    )
                    == 0
                )

            valid = {
                "revision": 0,
                "legal_operator_name": "  HLK   Studios  ",
                "country_code": "ca",
                "region": " Ontario ",
                "support_email": "support@example.com",
                "privacy_email": "privacy@example.com",
                "copyright_email": "copyright@example.com",
                "minimum_user_age": 13,
                "governing_law_jurisdiction": " Ontario,   Canada ",
            }
            untrusted = owner_client.put(
                "/admin/site/legal-policy",
                json=valid,
                headers={"Origin": "https://untrusted.example"},
            )
            assert untrusted.status_code == 403

            invalid_payloads = []
            for field, value in (
                ("country_code", "C"),
                ("country_code", "ZZ"),
                ("support_email", "not-an-email"),
                ("minimum_user_age", -1),
                ("minimum_user_age", 121),
                ("minimum_user_age", "13"),
                ("legal_operator_name", "HLK\u0000Studios"),
                ("region", "Ontario\u0085Province"),
            ):
                payload = {**valid, field: value}
                invalid_payloads.append(payload)
            invalid_payloads.append({**valid, "approved": True})
            for payload in invalid_payloads:
                rejected = owner_client.put("/admin/site/legal-policy", json=payload)
                assert rejected.status_code == 422, rejected.text

            created = owner_client.put("/admin/site/legal-policy", json=valid)
            assert created.status_code == 200, created.text
            created_body = created.json()
            assert created_body == {
                "schema_version": 1,
                "revision": 1,
                "status": "draft",
                "updated_at": created_body["updated_at"],
                "legal_operator_name": "HLK Studios",
                "country_code": "CA",
                "region": "Ontario",
                "support_email": "support@example.com",
                "privacy_email": "privacy@example.com",
                "copyright_email": "copyright@example.com",
                "minimum_user_age": 13,
                "governing_law_jurisdiction": "Ontario, Canada",
            }
            assert created_body["updated_at"] is not None
            assert "approved" not in created_body
            assert "published" not in created_body

            no_op = owner_client.put(
                "/admin/site/legal-policy",
                json={
                    "revision": 1,
                    **{
                        key: value
                        for key, value in created_body.items()
                        if key not in {"schema_version", "revision", "status", "updated_at"}
                    },
                },
            )
            assert no_op.status_code == 200
            assert no_op.json()["revision"] == 1

            updated_payload = {
                "revision": 1,
                **{
                    key: value
                    for key, value in created_body.items()
                    if key not in {"schema_version", "revision", "status", "updated_at"}
                },
                "privacy_email": None,
                "minimum_user_age": 18,
            }
            updated = owner_client.put("/admin/site/legal-policy", json=updated_payload)
            assert updated.status_code == 200, updated.text
            assert updated.json()["revision"] == 2
            assert updated.json()["privacy_email"] is None
            assert updated.json()["minimum_user_age"] == 18

            stale = owner_client.put(
                "/admin/site/legal-policy", json={**updated_payload, "revision": 1}
            )
            assert stale.status_code == 409

        with TestClient(app) as other_client:
            assert (
                other_client.post(
                    "/admin/auth/login",
                    json={"email": other_email, "password": password},
                ).status_code
                == 200
            )
            assert other_client.get("/admin/site/legal-policy").status_code == 403
            assert (
                other_client.put("/admin/site/legal-policy", json=_empty_payload()).status_code
                == 403
            )

        with SessionLocal() as db:
            stored = db.get_one(LegalPolicyConfiguration, 1)
            assert stored.revision == 2
            assert stored.legal_operator_name == "HLK Studios"
            audits = list(
                db.scalars(
                    select(AuditLog)
                    .where(
                        AuditLog.actor_id == owner_id,
                        AuditLog.action == "legal_policy.draft.updated",
                    )
                    .order_by(AuditLog.created_at)
                )
            )
            assert len(audits) == 2
            assert audits[0].detail == {
                "schema_version": 1,
                "revision": 1,
                "changed_fields": [
                    "legal_operator_name",
                    "country_code",
                    "region",
                    "support_email",
                    "privacy_email",
                    "copyright_email",
                    "minimum_user_age",
                    "governing_law_jurisdiction",
                ],
            }
            assert audits[1].detail == {
                "schema_version": 1,
                "revision": 2,
                "changed_fields": ["privacy_email", "minimum_user_age"],
            }
            audit_text = json.dumps([audit.detail for audit in audits])
            for private_value in (
                "HLK Studios",
                "support@example.com",
                "privacy@example.com",
                "copyright@example.com",
                "Ontario, Canada",
            ):
                assert private_value not in audit_text
    finally:
        with SessionLocal() as db:
            db.execute(delete(LegalPolicyConfiguration))
            db.execute(delete(SiteBrandConfiguration))
            db.execute(delete(AuditLog).where(AuditLog.actor_id.in_([owner_id, other_id])))
            db.execute(delete(Admin).where(Admin.id.in_([owner_id, other_id])))
            db.commit()


def test_no_op_draft_save_locks_its_revision_until_commit() -> None:
    suffix = uuid.uuid4().hex[:10]
    with SessionLocal() as db:
        owner = Admin(
            email=f"legal-lock-owner-{suffix}@example.com",
            password_hash=hash_password("LegalLockTestPassword123"),
        )
        db.add(owner)
        db.flush()
        owner_id = owner.id
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
        db.flush()
        db.add(
            LegalPolicyConfiguration(
                site_brand_configuration_id=1,
                legal_operator_name="HLK Studios",
                country_code="CA",
                region="Ontario",
                revision=1,
            )
        )
        db.commit()

    original = LegalPolicyPutRequest(
        revision=1,
        legal_operator_name="HLK Studios",
        country_code="CA",
        region="Ontario",
        support_email=None,
        privacy_email=None,
        copyright_email=None,
        minimum_user_age=None,
        governing_law_jurisdiction=None,
    )
    changed = original.model_copy(update={"region": "Quebec"})
    backend_pids: Queue[int] = Queue()

    def concurrent_update() -> tuple[int, list[str]]:
        with SessionLocal() as db:
            backend_pids.put(db.scalar(text("SELECT pg_backend_pid()")))
            configuration, changed_fields = put_configuration(db, changed)
            assert configuration is not None
            revision = configuration.revision
            db.commit()
            return revision, changed_fields

    try:
        with SessionLocal() as locking_db:
            configuration, changed_fields = put_configuration(locking_db, original)
            assert configuration is not None
            assert configuration.revision == 1
            assert changed_fields == []

            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(concurrent_update)
                contender_pid = backend_pids.get(timeout=3)
                waiting_on_lock = False
                deadline = monotonic() + 3
                try:
                    while monotonic() < deadline:
                        with SessionLocal() as inspector:
                            wait_event_type = inspector.scalar(
                                text(
                                    "SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"
                                ),
                                {"pid": contender_pid},
                            )
                        if wait_event_type == "Lock":
                            waiting_on_lock = True
                            break
                        sleep(0.01)
                    assert waiting_on_lock, (
                        "the concurrent update did not wait for the no-op revision lock"
                    )
                finally:
                    locking_db.commit()

                revision, contender_changed_fields = future.result(timeout=3)
                assert revision == 2
                assert contender_changed_fields == ["region"]

        with SessionLocal() as db:
            stored = db.get_one(LegalPolicyConfiguration, 1)
            assert stored.revision == 2
            assert stored.region == "Quebec"
    finally:
        with SessionLocal() as db:
            db.execute(delete(LegalPolicyConfiguration))
            db.execute(delete(SiteBrandConfiguration))
            db.execute(delete(Admin).where(Admin.id == owner_id))
            db.commit()
