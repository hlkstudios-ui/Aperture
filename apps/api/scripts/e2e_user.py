"""Remove an isolated customer created by local browser tests."""

import json
import sys

from sqlalchemy import delete

from app.config import get_settings
from app.db import SessionLocal
from app.models import User


def main() -> None:
    if get_settings().app_env not in {"development", "test"}:
        raise SystemExit("E2E customer helpers are disabled outside development/test")
    email = json.load(sys.stdin)["email"].lower()
    if not email.endswith("@example.com"):
        raise SystemExit("E2E customer email must use example.com")
    with SessionLocal() as db:
        db.execute(delete(User).where(User.email == email))
        db.commit()


if __name__ == "__main__":
    main()
