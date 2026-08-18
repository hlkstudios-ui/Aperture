import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, func, select

from app.auth import DbSession, require_customer, require_customer_session, require_trusted_origin
from app.models import AnalyticsEvent, DeviceSession, Profile, ProfilePreference, User
from app.schemas import ProfileCreate, ProfilePrivacyUpdate, ProfileResponse, ProfileUpdate

router = APIRouter(
    prefix="/profiles", tags=["profiles"], dependencies=[Depends(require_trusted_origin)]
)


def owned_profile(db: DbSession, user_id: uuid.UUID, profile_id: uuid.UUID) -> Profile:
    profile = db.scalar(select(Profile).where(Profile.id == profile_id, Profile.user_id == user_id))
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found")
    return profile


def apply_preference(preference: ProfilePreference, data) -> None:
    for field, value in data.model_dump().items():
        if field in {"analytics_enabled", "consent_updated_at"}:
            continue
        setattr(preference, field, value)


@router.get("", response_model=list[ProfileResponse])
def list_profiles(user: Annotated[User, Depends(require_customer)]) -> list[Profile]:
    return user.profiles


@router.post("", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
def create_profile(
    payload: ProfileCreate, db: DbSession, user: Annotated[User, Depends(require_customer)]
) -> Profile:
    if db.scalar(select(func.count(Profile.id)).where(Profile.user_id == user.id)) >= 5:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account can have at most five profiles")
    profile = Profile(
        user_id=user.id,
        name=payload.name.strip(),
        avatar_key=payload.avatar_key,
        maturity_level=payload.maturity_level,
        language=payload.language,
        is_kids=payload.is_kids,
    )
    profile.preference = ProfilePreference()
    apply_preference(profile.preference, payload.preference)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.patch("/{profile_id}", response_model=ProfileResponse)
def update_profile(
    profile_id: uuid.UUID,
    payload: ProfileUpdate,
    db: DbSession,
    user: Annotated[User, Depends(require_customer)],
) -> Profile:
    profile = owned_profile(db, user.id, profile_id)
    values = payload.model_dump(exclude_unset=True, exclude={"preference"})
    for field, value in values.items():
        setattr(profile, field, value.strip() if field == "name" else value)
    if payload.preference is not None:
        apply_preference(profile.preference, payload.preference)
    db.commit()
    db.refresh(profile)
    return profile


@router.put("/{profile_id}/privacy", response_model=ProfileResponse)
def update_privacy(
    profile_id: uuid.UUID,
    payload: ProfilePrivacyUpdate,
    db: DbSession,
    user: Annotated[User, Depends(require_customer)],
) -> Profile:
    profile = owned_profile(db, user.id, profile_id)
    preference = profile.preference
    was_enabled = preference.analytics_enabled
    preference.analytics_enabled = payload.analytics_enabled
    preference.homepage_mode = payload.homepage_mode
    preference.consent_updated_at = datetime.now(UTC)
    if was_enabled and not payload.analytics_enabled:
        db.execute(delete(AnalyticsEvent).where(AnalyticsEvent.profile_id == profile.id))
    db.commit()
    db.refresh(profile)
    return profile


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(
    profile_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(require_customer)],
) -> Response:
    profile = owned_profile(db, user.id, profile_id)
    if db.scalar(select(func.count(Profile.id)).where(Profile.user_id == user.id)) <= 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The account must retain at least one profile"
        )
    db.delete(profile)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{profile_id}/switch", response_model=ProfileResponse)
def switch_profile(
    profile_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(require_customer)],
    session: Annotated[DeviceSession, Depends(require_customer_session)],
) -> Profile:
    profile = owned_profile(db, user.id, profile_id)
    session.active_profile_id = profile.id
    db.commit()
    return profile
