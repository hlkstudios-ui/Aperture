"""Create or remove an isolated administrator for local browser tests only."""

import json
import sys

from e2e_guard import require_e2e_test_environment
from sqlalchemy import delete, select

from app.auth import hash_password
from app.community_models import ModerationAction
from app.db import SessionLocal
from app.models import Admin, AuditLog


def main() -> None:
    require_e2e_test_environment()
    payload = json.load(sys.stdin)
    email = payload["email"].lower()
    if not email.endswith("@example.com"):
        raise SystemExit("E2E administrator email must use example.com")

    with SessionLocal() as db:
        admin = db.scalar(select(Admin).where(Admin.email == email))
        if payload["action"] == "create":
            if admin is None:
                admin = Admin(email=email, password_hash=hash_password(payload["password"]))
                db.add(admin)
            else:
                admin.password_hash = hash_password(payload["password"])
        elif payload["action"] == "delete" and admin is not None:
            db.execute(delete(ModerationAction).where(ModerationAction.admin_id == admin.id))
            db.execute(delete(AuditLog).where(AuditLog.actor_id == admin.id))
            db.delete(admin)
        else:
            raise SystemExit("Unsupported E2E administrator action")
        db.commit()


if __name__ == "__main__":
    main()
