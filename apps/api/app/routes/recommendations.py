from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.auth import DbSession, require_customer_session, require_trusted_origin
from app.catalog_models import Genre
from app.geo import OptionalViewerCountry
from app.models import DeviceSession, HomepageMode, Profile
from app.prescription_service import prescribe
from app.recommendation_schemas import (
    PrescriptionRequest,
    PrescriptionResponse,
    RecommendationPreferenceUpdate,
    RecommendationResponse,
    TasteDnaResponse,
)
from app.recommendation_service import recommend
from app.taste_service import taste_dna

router = APIRouter(
    prefix="/recommendations",
    tags=["customer recommendations"],
    dependencies=[Depends(require_trusted_origin)],
)
CurrentSession = Annotated[DeviceSession, Depends(require_customer_session)]


def active_profile(db: DbSession, session: DeviceSession) -> Profile:
    if session.active_profile_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Select a profile first")
    profile = db.scalar(
        select(Profile)
        .options(selectinload(Profile.preference))
        .where(Profile.id == session.active_profile_id, Profile.user_id == session.user_id)
    )
    if profile is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Active profile is unavailable")
    return profile


@router.get("", response_model=RecommendationResponse)
def recommendations(
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
    limit: int = Query(default=20, ge=1, le=40),
) -> RecommendationResponse:
    profile = active_profile(db, session)
    return recommend(
        db,
        profile,
        limit,
        personalized=profile.preference.homepage_mode != HomepageMode.no_algorithm,
        country=country,
    )


@router.get("/taste-dna", response_model=TasteDnaResponse)
def profile_taste_dna(db: DbSession, session: CurrentSession) -> TasteDnaResponse:
    return taste_dna(db, active_profile(db, session))


@router.post("/movie-prescription", response_model=PrescriptionResponse)
def movie_prescription(
    payload: PrescriptionRequest,
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
) -> PrescriptionResponse:
    return prescribe(db, active_profile(db, session), payload, country)


@router.put("/preferences", response_model=RecommendationPreferenceUpdate)
def update_preferences(
    payload: RecommendationPreferenceUpdate, db: DbSession, session: CurrentSession
) -> RecommendationPreferenceUpdate:
    profile = active_profile(db, session)
    slugs = sorted({slug.strip().lower() for slug in payload.preferred_genre_slugs if slug.strip()})
    if any(len(slug) > 180 for slug in slugs):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Genre slug is too long")
    existing = set(db.scalars(select(Genre.slug).where(Genre.slug.in_(slugs))))
    if existing != set(slugs):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown genre preference")
    profile.preference.extra = {**(profile.preference.extra or {}), "preferred_genre_slugs": slugs}
    db.commit()
    return RecommendationPreferenceUpdate(preferred_genre_slugs=slugs)
