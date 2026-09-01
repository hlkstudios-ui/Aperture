import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app import platform_verification_service as verification_service
from app.config import Settings
from app.platform_models import PlatformAuditEvent


def test_platform_email_delivery_lease_configuration_is_bounded() -> None:
    assert Settings.model_fields["platform_email_delivery_lease_seconds"].default == 120

    for invalid in (29, 301):
        with pytest.raises(
            ValidationError,
            match="PLATFORM_EMAIL_DELIVERY_LEASE_SECONDS must be between 30 and 300",
        ):
            Settings(
                _env_file=None,
                platform_email_delivery_lease_seconds=invalid,
            )


def test_reconcile_stale_platform_verification_deliveries_is_bounded_and_secret_free(
    monkeypatch,
) -> None:
    observed_at = datetime(2026, 8, 31, 18, 30, tzinfo=UTC)
    account_ids = [uuid.uuid4(), uuid.uuid4()]
    deliveries = [
        SimpleNamespace(
            id=uuid.uuid4(),
            account_id=account_id,
            token_hash=f"sensitive-token-hash-{index}",
            state="pending_delivery",
            used_at=None,
        )
        for index, account_id in enumerate(account_ids)
    ]

    class Db:
        def __init__(self) -> None:
            self.clock_statement = None
            self.delivery_statement = None
            self.added: list[object] = []

        def scalar(self, statement):
            self.clock_statement = statement
            return observed_at

        def scalars(self, statement):
            self.delivery_statement = statement
            return deliveries

        def add(self, value: object) -> None:
            self.added.append(value)

    db = Db()
    monkeypatch.setattr(
        verification_service,
        "get_settings",
        lambda: SimpleNamespace(platform_email_delivery_lease_seconds=120),
    )

    reconciled = verification_service.reconcile_stale_platform_verification_deliveries(
        db,
        limit=2,
    )

    assert reconciled == 2
    assert all(delivery.state == "delivery_failed" for delivery in deliveries)
    assert all(delivery.used_at == observed_at for delivery in deliveries)
    assert db.clock_statement is not None
    assert "transaction_timestamp" in str(db.clock_statement)
    assert db.delivery_statement is not None
    compiled = db.delivery_statement.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    statement = str(compiled)
    assert "platform_email_verification_tokens.state = 'pending_delivery'" in statement
    assert str(observed_at - timedelta(seconds=120)) in statement
    assert "LIMIT 2" in statement
    assert "FOR UPDATE OF platform_email_verification_tokens SKIP LOCKED" in statement

    audits = [value for value in db.added if isinstance(value, PlatformAuditEvent)]
    assert len(audits) == 2
    assert [audit.resource_id for audit in audits] == account_ids
    assert all(audit.actor_type == "system" for audit in audits)
    assert all(audit.actor_account_id is None for audit in audits)
    assert all(audit.resource_type == "platform_account" for audit in audits)
    assert all(audit.action == "platform_account.email_verification_delivery" for audit in audits)
    assert all(audit.outcome == "failed" for audit in audits)
    serialized_audits = json.dumps([audit.detail for audit in audits])
    assert "sensitive-token-hash" not in serialized_audits
    assert all(audit.detail["reason"] == "delivery_lease_expired" for audit in audits)


@pytest.mark.parametrize("limit", [0, 501])
def test_reconcile_stale_platform_verification_deliveries_rejects_unbounded_work(
    limit: int,
) -> None:
    with pytest.raises(
        ValueError,
        match="Verification delivery reconciliation limit must be between 1 and 500",
    ):
        verification_service.reconcile_stale_platform_verification_deliveries(
            object(),
            limit=limit,
        )
