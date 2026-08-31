import argparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Admin, AuditLog, SiteBrandConfiguration

CONFIRMATION = "TRANSFER SITE BRAND OWNERSHIP"


def reassign_site_brand_owner(
    db: Session,
    *,
    current_owner_email: str,
    new_owner_email: str,
    reason: str,
) -> tuple[Admin, Admin]:
    current_email = current_owner_email.strip().lower()
    target_email = new_owner_email.strip().lower()
    reason = " ".join(reason.split())
    if current_email == target_email:
        raise RuntimeError("Current and new owner must be different administrators")
    if len(reason) < 10:
        raise RuntimeError("A recovery reason of at least 10 characters is required")

    configuration = db.scalar(
        select(SiteBrandConfiguration)
        .where(SiteBrandConfiguration.id == 1)
        .with_for_update()
    )
    if configuration is None:
        raise RuntimeError("No site brand configuration exists; use normal first-run claiming")
    current_owner = db.get(Admin, configuration.owner_admin_id)
    if current_owner is None or current_owner.email.lower() != current_email:
        raise RuntimeError("The supplied current owner does not match the stored owner")
    new_owner = db.scalar(select(Admin).where(Admin.email == target_email))
    if new_owner is None or not new_owner.is_active:
        raise RuntimeError("The new owner must be an existing active administrator")

    configuration.owner_admin_id = new_owner.id
    db.add(
        AuditLog(
            actor_type="system",
            actor_id=None,
            action="site_brand.owner.reassigned",
            outcome="succeeded",
            detail={
                "previous_owner_id": str(current_owner.id),
                "new_owner_id": str(new_owner.id),
                "reason": reason,
            },
        )
    )
    db.flush()
    return current_owner, new_owner


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audited offline recovery for site-brand ownership"
    )
    parser.add_argument("--current-owner", required=True)
    parser.add_argument("--new-owner", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit(f'Confirmation must be exactly "{CONFIRMATION}"')

    with SessionLocal() as db:
        try:
            previous, new = reassign_site_brand_owner(
                db,
                current_owner_email=args.current_owner,
                new_owner_email=args.new_owner,
                reason=args.reason,
            )
            db.commit()
        except RuntimeError as error:
            db.rollback()
            raise SystemExit(str(error)) from error
    print(f"Site-brand ownership transferred from {previous.email} to {new.email}; audit recorded")


if __name__ == "__main__":
    main()
