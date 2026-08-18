from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth import DbSession, require_customer_session, require_trusted_origin
from app.geo import OptionalViewerCountry
from app.homepage_schemas import HomepageModeUpdate, HomepagePublicResponse
from app.homepage_service import get_configuration, render_homepage, render_no_algorithm_homepage
from app.models import DeviceSession, HomepageMode, Profile
from app.routes.recommendations import active_profile

router = APIRouter(prefix="/homepage", tags=["customer homepage"])


@router.get("", response_model=HomepagePublicResponse)
def homepage(db: DbSession, country: OptionalViewerCountry) -> HomepagePublicResponse:
    config = get_configuration(db)
    return render_homepage(
        db, config.published_snapshot, published_at=config.published_at, country=country
    )


@router.get("/profile", response_model=HomepagePublicResponse)
def profile_homepage(
    db: DbSession,
    session: Annotated[DeviceSession, Depends(require_customer_session)],
    country: OptionalViewerCountry,
) -> HomepagePublicResponse:
    profile = active_profile(db, session)
    if profile.preference.homepage_mode == HomepageMode.no_algorithm:
        return render_no_algorithm_homepage(db, country)
    config = get_configuration(db)
    response = render_homepage(
        db, config.published_snapshot, published_at=config.published_at, country=country
    )
    response.mode = HomepageMode.curated.value
    response.strategy = "published_editorial_snapshot"
    return response


@router.patch(
    "/mode",
    response_model=HomepagePublicResponse,
    dependencies=[Depends(require_trusted_origin)],
)
def update_homepage_mode(
    payload: HomepageModeUpdate,
    db: DbSession,
    session: Annotated[DeviceSession, Depends(require_customer_session)],
    country: OptionalViewerCountry,
) -> HomepagePublicResponse:
    profile: Profile = active_profile(db, session)
    profile.preference.homepage_mode = HomepageMode(payload.mode)
    db.commit()
    return profile_homepage(db, session, country)
