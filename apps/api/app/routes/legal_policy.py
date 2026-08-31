import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response

from app.auth import DbSession, require_admin, require_trusted_origin
from app.legal_policy_schemas import LegalPolicyAdminResponse, LegalPolicyPutRequest
from app.legal_policy_service import admin_response, put_configuration
from app.models import Admin, AuditLog, LegalPolicyConfiguration
from app.site_brand_service import get_or_claim_configuration

router = APIRouter(
    prefix="/admin/site/legal-policy",
    tags=["administrator legal policy setup"],
    dependencies=[Depends(require_trusted_origin), Depends(require_admin)],
)
AdminIdentity = Annotated[Admin, Depends(require_admin)]
PRIVATE_NO_STORE_HEADERS = {
    "Cache-Control": "private, no-store, max-age=0, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
    "Vary": "Cookie",
}


def _private_no_store(response: Response) -> None:
    response.headers.update(PRIVATE_NO_STORE_HEADERS)


def _audit(
    db: DbSession,
    request: Request,
    admin: Admin | uuid.UUID,
    action: str,
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_type="admin",
            actor_id=admin.id if isinstance(admin, Admin) else admin,
            action=action,
            outcome="succeeded",
            ip_address=request.client.host if request.client else None,
            detail=detail or {},
        )
    )


def _require_owner(db: DbSession, request: Request, admin: Admin) -> None:
    _, claimed = get_or_claim_configuration(db, admin)
    if claimed:
        _audit(db, request, admin, "site_brand.owner.claimed", {"schema_version": 1})


@router.get("", response_model=LegalPolicyAdminResponse)
def get_legal_policy(
    request: Request,
    response: Response,
    db: DbSession,
    admin: AdminIdentity,
) -> LegalPolicyAdminResponse:
    _private_no_store(response)
    _require_owner(db, request, admin)
    db.commit()
    return admin_response(db.get(LegalPolicyConfiguration, 1))


@router.put("", response_model=LegalPolicyAdminResponse)
def put_legal_policy(
    payload: LegalPolicyPutRequest,
    request: Request,
    response: Response,
    db: DbSession,
    admin: AdminIdentity,
) -> LegalPolicyAdminResponse:
    _private_no_store(response)
    _require_owner(db, request, admin)
    configuration, changed_fields = put_configuration(db, payload)
    if changed_fields:
        _audit(
            db,
            request,
            admin,
            "legal_policy.draft.updated",
            {
                "schema_version": 1,
                "revision": configuration.revision if configuration is not None else 0,
                "changed_fields": changed_fields,
            },
        )
    db.commit()
    if configuration is not None:
        db.refresh(configuration)
    return admin_response(configuration)
