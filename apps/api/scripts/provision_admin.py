import argparse
import getpass

from sqlalchemy import func, select

from app.auth import hash_password
from app.db import SessionLocal
from app.models import Admin, AuditLog


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision the platform's single administrator")
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    password = getpass.getpass("Administrator password: ")
    confirmation = getpass.getpass("Confirm administrator password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match")
    if len(password) < 14 or not all(
        (
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
        )
    ):
        raise SystemExit(
            "Password must be at least 14 characters with uppercase, lowercase, "
            "and numeric characters"
        )

    with SessionLocal() as db:
        existing_count = db.scalar(select(func.count(Admin.id)))
        existing = db.scalar(select(Admin).where(Admin.email == args.email.lower()))
        if existing_count and existing is None:
            raise SystemExit(
                "An administrator is already provisioned; a second administrator is not allowed"
            )
        if existing:
            existing.password_hash = hash_password(password)
            action = "admin.password_rotated"
            admin = existing
        else:
            admin = Admin(email=args.email.lower(), password_hash=hash_password(password))
            db.add(admin)
            db.flush()
            action = "admin.provisioned"
        db.add(AuditLog(actor_type="system", actor_id=admin.id, action=action, outcome="succeeded"))
        db.commit()
        print(
            f"Administrator {admin.email} provisioned successfully; "
            "MFA enrollment remains required before production."
        )


if __name__ == "__main__":
    main()
