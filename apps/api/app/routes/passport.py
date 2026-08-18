from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.auth import DbSession, require_customer_session, require_trusted_origin
from app.models import DeviceSession
from app.passport_schemas import PassportReport
from app.passport_service import passport_report
from app.routes.recommendations import active_profile

router = APIRouter(
    prefix="/passport",
    tags=["customer cinema passport"],
    dependencies=[Depends(require_trusted_origin)],
)
CurrentSession = Annotated[DeviceSession, Depends(require_customer_session)]


@router.get("", response_model=PassportReport)
def passport(
    db: DbSession,
    session: CurrentSession,
    year: int | None = Query(default=None, ge=2000, le=2100),
) -> PassportReport:
    return passport_report(db, active_profile(db, session), year)
