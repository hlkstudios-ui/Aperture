import asyncio
import uuid
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app.routes import customer_auth
from app.schemas import PasswordResetRequest


class FakeDb:
    def __init__(self) -> None:
        self.user = SimpleNamespace(
            id=uuid.uuid4(),
            email="viewer@example.com",
            is_active=True,
        )
        self.committed = False

    def scalar(self, _statement):
        return self.user

    def execute(self, _statement) -> None:
        return None

    def add(self, _record) -> None:
        return None

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        return None


@pytest.mark.parametrize(
    "request_origin",
    ["https://apertures.online", "https://watch.customer.com"],
)
def test_password_reset_email_uses_the_validated_requesting_front_door(
    monkeypatch: pytest.MonkeyPatch, request_origin: str
) -> None:
    db = FakeDb()
    sent: list[str] = []

    async def allow_rate_limit(*_args, **_kwargs) -> None:
        return None

    async def send_reset(_email: str, _token: str, _brand: str, origin: str) -> None:
        sent.append(origin)

    monkeypatch.setattr(
        customer_auth,
        "settings",
        SimpleNamespace(app_env="production"),
    )
    monkeypatch.setattr(customer_auth, "enforce_rate_limit", allow_rate_limit)
    monkeypatch.setattr(customer_auth, "new_session_token", lambda: ("raw-token", "hash"))
    monkeypatch.setattr(
        customer_auth,
        "public_brand_response",
        lambda _db: SimpleNamespace(short_name="Aperture"),
    )
    monkeypatch.setattr(
        customer_auth,
        "resolve_request_public_origin",
        lambda actual_db, _request: request_origin if actual_db is db else "unexpected",
    )
    monkeypatch.setattr(customer_auth, "send_password_reset", send_reset)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/password-reset/request",
            "headers": [(b"origin", request_origin.encode())],
            "client": ("203.0.113.10", 443),
        }
    )

    asyncio.run(
        customer_auth.request_password_reset(
            PasswordResetRequest(email="viewer@example.com"), request, db
        )
    )

    assert sent == [request_origin]
    assert db.committed
