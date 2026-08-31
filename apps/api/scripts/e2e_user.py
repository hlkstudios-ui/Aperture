"""Remove an isolated customer created by local browser tests."""

import json
import sys

from e2e_guard import require_e2e_test_environment
from sqlalchemy import delete

from app.db import SessionLocal
from app.models import User


def main() -> None:
    require_e2e_test_environment()
    email = json.load(sys.stdin)["email"].lower()
    if not email.endswith("@example.com"):
        raise SystemExit("E2E customer email must use example.com")
    with SessionLocal() as db:
        db.execute(delete(User).where(User.email == email))
        db.commit()


if __name__ == "__main__":
    main()
