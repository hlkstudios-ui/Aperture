import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, func, or_, select

from app.auth import DbSession, require_customer_session, require_trusted_origin
from app.catalog_models import Movie
from app.community_models import (
    CommunityActivity,
    CommunityActivityKind,
    CommunityReport,
    ModerationStatus,
    ProfileFollow,
    ProfileSafetyRelation,
    Rating,
    Review,
    SafetyRelationKind,
)
from app.community_schemas import (
    ActivityResponse,
    FollowResponse,
    MovieCommunityResponse,
    RatingResponse,
    RatingWrite,
    ReportResponse,
    ReportWrite,
    ReviewResponse,
    ReviewWrite,
    SafetyResponse,
)
from app.curation_models import Collection, CollectionKind
from app.curation_schemas import CollectionResponse
from app.curation_service import collection_response, load_collection
from app.geo import OptionalViewerCountry
from app.models import DeviceSession, Profile
from app.rate_limit import enforce_rate_limit
from app.routes.recommendations import active_profile
from app.scheduling import availability_clause

router = APIRouter(
    prefix="/community",
    tags=["customer community"],
    dependencies=[Depends(require_trusted_origin)],
)
CurrentSession = Annotated[DeviceSession, Depends(require_customer_session)]


def available_movie(db: DbSession, movie_id: uuid.UUID, country: str | None) -> Movie:
    movie = db.scalar(
        select(Movie).where(Movie.id == movie_id, availability_clause(Movie, country=country))
    )
    if movie is None:
        raise HTTPException(404, "Movie was not found")
    return movie


def review_response(db: DbSession, review: Review, *, public: bool = False) -> ReviewResponse:
    profile_name = db.scalar(select(Profile.name).where(Profile.id == review.profile_id))
    return ReviewResponse(
        id=review.id,
        movie_id=review.movie_id,
        profile_id=review.profile_id,
        profile_name=profile_name if public else None,
        headline=review.headline,
        body=review.body,
        contains_spoilers=review.contains_spoilers,
        status=review.status,
        moderation_note=None if public else review.moderation_note,
        created_at=review.created_at,
        updated_at=review.updated_at,
        published_at=review.published_at,
    )


@router.put("/movies/{movie_id}/rating", response_model=RatingResponse)
async def put_rating(
    movie_id: uuid.UUID,
    payload: RatingWrite,
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
) -> Rating:
    profile = active_profile(db, session)
    available_movie(db, movie_id, country)
    await enforce_rate_limit(f"community:rating:{profile.id}", limit=30, window_seconds=3600)
    rating = db.scalar(
        select(Rating).where(Rating.profile_id == profile.id, Rating.movie_id == movie_id)
    )
    if rating is None:
        rating = Rating(profile_id=profile.id, movie_id=movie_id, score=payload.score)
        db.add(rating)
    else:
        rating.score = payload.score
    db.commit()
    db.refresh(rating)
    return rating


@router.put("/movies/{movie_id}/review", response_model=ReviewResponse)
async def put_review(
    movie_id: uuid.UUID,
    payload: ReviewWrite,
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
) -> ReviewResponse:
    profile = active_profile(db, session)
    available_movie(db, movie_id, country)
    await enforce_rate_limit(f"community:review:{profile.id}", limit=8, window_seconds=3600)
    review = db.scalar(
        select(Review).where(Review.profile_id == profile.id, Review.movie_id == movie_id)
    )
    if review is None:
        review = Review(profile_id=profile.id, movie_id=movie_id, **payload.model_dump())
        db.add(review)
    else:
        for key, value in payload.model_dump().items():
            setattr(review, key, value)
        review.status = ModerationStatus.pending
        review.moderation_note = None
        review.published_at = None
    db.commit()
    db.refresh(review)
    return review_response(db, review)


@router.get("/me/reviews", response_model=list[ReviewResponse])
def my_reviews(db: DbSession, session: CurrentSession) -> list[ReviewResponse]:
    profile = active_profile(db, session)
    records = db.scalars(
        select(Review).where(Review.profile_id == profile.id).order_by(Review.updated_at.desc())
    )
    return [review_response(db, review) for review in records]


def hidden_profile_ids(db: DbSession, profile_id: uuid.UUID) -> set[uuid.UUID]:
    rows = db.execute(
        select(
            ProfileSafetyRelation.actor_profile_id,
            ProfileSafetyRelation.target_profile_id,
            ProfileSafetyRelation.kind,
        ).where(
            or_(
                ProfileSafetyRelation.actor_profile_id == profile_id,
                ProfileSafetyRelation.target_profile_id == profile_id,
            )
        )
    )
    hidden = set()
    for actor_id, target_id, kind in rows:
        if kind == SafetyRelationKind.block or actor_id == profile_id:
            hidden.add(target_id if actor_id == profile_id else actor_id)
    return hidden


@router.get("/movies/{movie_id}", response_model=MovieCommunityResponse)
def movie_community(
    movie_id: uuid.UUID,
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
) -> MovieCommunityResponse:
    profile = active_profile(db, session)
    available_movie(db, movie_id, country)
    hidden = hidden_profile_ids(db, profile.id)
    statement = select(Review).where(
        Review.movie_id == movie_id,
        Review.status == ModerationStatus.approved,
    )
    if hidden:
        statement = statement.where(Review.profile_id.not_in(hidden))
    reviews = list(db.scalars(statement.order_by(Review.published_at.desc())).all())
    rating_count, average = db.execute(
        select(func.count(Rating.id), func.avg(Rating.score)).where(Rating.movie_id == movie_id)
    ).one()
    viewer_rating = db.scalar(
        select(Rating.score).where(Rating.movie_id == movie_id, Rating.profile_id == profile.id)
    )
    return MovieCommunityResponse(
        movie_id=movie_id,
        rating_count=rating_count,
        average_rating=round(float(average), 2) if average is not None else None,
        viewer_rating=viewer_rating,
        reviews=[review_response(db, review, public=True) for review in reviews],
    )


def visible_list_statement(hidden: set[uuid.UUID]):
    statement = select(Collection).where(
        Collection.kind == CollectionKind.user_list,
        Collection.visibility == "public",
        Collection.moderation_status == ModerationStatus.approved.value,
    )
    if hidden:
        statement = statement.where(Collection.owner_profile_id.not_in(hidden))
    return statement


@router.get("/lists", response_model=list[CollectionResponse])
def public_lists(
    db: DbSession, session: CurrentSession, country: OptionalViewerCountry
) -> list[CollectionResponse]:
    profile = active_profile(db, session)
    records = db.scalars(
        visible_list_statement(hidden_profile_ids(db, profile.id)).order_by(
            Collection.updated_at.desc(), Collection.id
        )
    )
    return [collection_response(db, load_collection(db, record.id), country) for record in records]


@router.get("/lists/{slug}", response_model=CollectionResponse)
def public_list(
    slug: str,
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
) -> CollectionResponse:
    profile = active_profile(db, session)
    record = db.scalar(
        visible_list_statement(hidden_profile_ids(db, profile.id)).where(Collection.slug == slug)
    )
    if record is None:
        raise HTTPException(404, "List was not found")
    return collection_response(db, load_collection(db, record.id), country)


@router.post("/reports", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def report_content(
    payload: ReportWrite, db: DbSession, session: CurrentSession
) -> CommunityReport:
    profile = active_profile(db, session)
    await enforce_rate_limit(f"community:report:{profile.id}", limit=10, window_seconds=3600)
    if payload.review_id:
        review = db.get(Review, payload.review_id)
        if review is None or review.status != ModerationStatus.approved:
            raise HTTPException(404, "Review was not found")
        if review.profile_id == profile.id:
            raise HTTPException(422, "You cannot report your own review")
    if payload.collection_id:
        collection = db.get(Collection, payload.collection_id)
        if (
            collection is None
            or collection.kind != CollectionKind.user_list
            or collection.visibility != "public"
            or collection.moderation_status != ModerationStatus.approved.value
        ):
            raise HTTPException(404, "List was not found")
        if collection.owner_profile_id == profile.id:
            raise HTTPException(422, "You cannot report your own list")
    duplicate = db.scalar(
        select(CommunityReport.id).where(
            CommunityReport.reporter_profile_id == profile.id,
            CommunityReport.review_id == payload.review_id,
            CommunityReport.collection_id == payload.collection_id,
        )
    )
    if duplicate:
        raise HTTPException(409, "You already reported this content")
    report = CommunityReport(reporter_profile_id=profile.id, **payload.model_dump())
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def target_profile(db: DbSession, profile_id: uuid.UUID) -> Profile:
    profile = db.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(404, "Profile was not found")
    return profile


@router.put("/safety/{target_profile_id}/{kind}", response_model=SafetyResponse)
async def put_safety_relation(
    target_profile_id: uuid.UUID,
    kind: SafetyRelationKind,
    db: DbSession,
    session: CurrentSession,
) -> SafetyResponse:
    profile = active_profile(db, session)
    await enforce_rate_limit(f"community:safety:{profile.id}", limit=30, window_seconds=3600)
    target_profile(db, target_profile_id)
    if target_profile_id == profile.id:
        raise HTTPException(422, "You cannot block or mute yourself")
    existing = db.scalar(
        select(ProfileSafetyRelation).where(
            ProfileSafetyRelation.actor_profile_id == profile.id,
            ProfileSafetyRelation.target_profile_id == target_profile_id,
            ProfileSafetyRelation.kind == kind,
        )
    )
    if existing is None:
        db.add(
            ProfileSafetyRelation(
                actor_profile_id=profile.id, target_profile_id=target_profile_id, kind=kind
            )
        )
    if kind == SafetyRelationKind.block:
        db.execute(
            delete(ProfileFollow).where(
                or_(
                    (ProfileFollow.follower_profile_id == profile.id)
                    & (ProfileFollow.followed_profile_id == target_profile_id),
                    (ProfileFollow.follower_profile_id == target_profile_id)
                    & (ProfileFollow.followed_profile_id == profile.id),
                )
            )
        )
    db.commit()
    return SafetyResponse(target_profile_id=target_profile_id, kind=kind)


@router.delete("/safety/{target_profile_id}/{kind}", status_code=status.HTTP_204_NO_CONTENT)
def delete_safety_relation(
    target_profile_id: uuid.UUID,
    kind: SafetyRelationKind,
    db: DbSession,
    session: CurrentSession,
) -> Response:
    profile = active_profile(db, session)
    db.execute(
        delete(ProfileSafetyRelation).where(
            ProfileSafetyRelation.actor_profile_id == profile.id,
            ProfileSafetyRelation.target_profile_id == target_profile_id,
            ProfileSafetyRelation.kind == kind,
        )
    )
    db.commit()
    return Response(status_code=204)


@router.put("/follows/{target_profile_id}", response_model=FollowResponse)
async def follow_profile(
    target_profile_id: uuid.UUID, db: DbSession, session: CurrentSession
) -> FollowResponse:
    profile = active_profile(db, session)
    await enforce_rate_limit(f"community:follow:{profile.id}", limit=30, window_seconds=3600)
    target_profile(db, target_profile_id)
    if target_profile_id == profile.id:
        raise HTTPException(422, "You cannot follow yourself")
    blocked = db.scalar(
        select(ProfileSafetyRelation.id).where(
            ProfileSafetyRelation.kind == SafetyRelationKind.block,
            or_(
                (ProfileSafetyRelation.actor_profile_id == profile.id)
                & (ProfileSafetyRelation.target_profile_id == target_profile_id),
                (ProfileSafetyRelation.actor_profile_id == target_profile_id)
                & (ProfileSafetyRelation.target_profile_id == profile.id),
            ),
        )
    )
    if blocked:
        raise HTTPException(409, "Following is unavailable between these profiles")
    existing = db.scalar(
        select(ProfileFollow).where(
            ProfileFollow.follower_profile_id == profile.id,
            ProfileFollow.followed_profile_id == target_profile_id,
        )
    )
    if existing is None:
        db.add(ProfileFollow(follower_profile_id=profile.id, followed_profile_id=target_profile_id))
        db.add(
            CommunityActivity(
                actor_profile_id=profile.id,
                kind=CommunityActivityKind.profile_followed,
                target_profile_id=target_profile_id,
            )
        )
    db.commit()
    return FollowResponse(target_profile_id=target_profile_id, following=True)


@router.delete("/follows/{target_profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def unfollow_profile(
    target_profile_id: uuid.UUID, db: DbSession, session: CurrentSession
) -> Response:
    profile = active_profile(db, session)
    db.execute(
        delete(ProfileFollow).where(
            ProfileFollow.follower_profile_id == profile.id,
            ProfileFollow.followed_profile_id == target_profile_id,
        )
    )
    db.commit()
    return Response(status_code=204)


@router.get("/activity", response_model=list[ActivityResponse])
def activity_feed(db: DbSession, session: CurrentSession) -> list[ActivityResponse]:
    profile = active_profile(db, session)
    followed = set(
        db.scalars(
            select(ProfileFollow.followed_profile_id).where(
                ProfileFollow.follower_profile_id == profile.id
            )
        )
    )
    hidden = hidden_profile_ids(db, profile.id)
    actor_ids = followed - hidden
    if not actor_ids:
        return []
    activities = db.scalars(
        select(CommunityActivity)
        .where(CommunityActivity.actor_profile_id.in_(actor_ids))
        .order_by(CommunityActivity.created_at.desc(), CommunityActivity.id)
        .limit(100)
    )
    response = []
    for activity in activities:
        if activity.review_id:
            review = db.get(Review, activity.review_id)
            if review is None or review.status != ModerationStatus.approved:
                continue
        if activity.collection_id:
            collection = db.get(Collection, activity.collection_id)
            if (
                collection is None
                or collection.visibility != "public"
                or collection.moderation_status != ModerationStatus.approved.value
            ):
                continue
        if activity.target_profile_id in hidden:
            continue
        actor_name = db.scalar(select(Profile.name).where(Profile.id == activity.actor_profile_id))
        if actor_name:
            response.append(
                ActivityResponse(
                    id=activity.id,
                    kind=activity.kind,
                    actor_profile_id=activity.actor_profile_id,
                    actor_profile_name=actor_name,
                    review_id=activity.review_id,
                    collection_id=activity.collection_id,
                    target_profile_id=activity.target_profile_id,
                    created_at=activity.created_at,
                )
            )
    return response
