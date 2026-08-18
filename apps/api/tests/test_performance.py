import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import delete, event

from app.auth import hash_password
from app.db import SessionLocal, engine
from app.main import app
from app.models import Admin, AuditLog


@contextmanager
def statement_counter() -> Iterator[list[str]]:
    statements: list[str] = []

    def record_statement(_connection, _cursor, statement, _parameters, _context, _many) -> None:
        statements.append(statement.lstrip().split(None, 1)[0].upper())

    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)


def test_public_catalog_queries_remain_bounded() -> None:
    budgets = {"/catalog/movies": 8, "/catalog/series": 8, "/homepage": 6}
    with TestClient(app) as client:
        for path, budget in budgets.items():
            with statement_counter() as statements:
                response = client.get(path)
            assert response.status_code == 200
            detail = f"{path} used {len(statements)} statements: {statements}"
            assert len(statements) <= budget, detail


def test_admin_analytics_title_resolution_is_not_n_plus_one() -> None:
    token = uuid.uuid4().hex
    email = f"performance-{token}@example.com"
    password = "PerformanceAdministrator123"
    with SessionLocal() as db:
        admin = Admin(email=email, password_hash=hash_password(password))
        db.add(admin)
        db.commit()
        admin_id = admin.id

    with TestClient(app) as client:
        assert (
            client.post(
                "/admin/auth/login", json={"email": email, "password": password}
            ).status_code
            == 200
        )
        with statement_counter() as statements:
            response = client.get("/admin/analytics/summary")
        assert response.status_code == 200
        # Two authentication reads plus five summary/bulk-title reads.
        assert len(statements) <= 7, statements

    with SessionLocal() as db:
        db.execute(delete(AuditLog).where(AuditLog.actor_id == admin_id))
        db.execute(delete(Admin).where(Admin.id == admin_id))
        db.commit()
