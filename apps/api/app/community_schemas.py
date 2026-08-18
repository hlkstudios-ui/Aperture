import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.community_models import (
    CommunityActivityKind,
    ModerationStatus,
    ReportReason,
    ReportStatus,
    SafetyRelationKind,
)
from app.curation_schemas import CollectionResponse


class RatingWrite(BaseModel):
    score: int = Field(ge=1, le=5)


class RatingResponse(BaseModel):
    id: uuid.UUID
    movie_id: uuid.UUID
    score: int
    updated_at: datetime


class ReviewWrite(BaseModel):
    headline: str | None = Field(default=None, max_length=140)
    body: str = Field(min_length=1, max_length=5000)
    contains_spoilers: bool = False


class ReviewResponse(BaseModel):
    id: uuid.UUID
    movie_id: uuid.UUID
    profile_id: uuid.UUID
    profile_name: str | None = None
    headline: str | None
    body: str
    contains_spoilers: bool
    status: ModerationStatus
    moderation_note: str | None = None
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None


class MovieCommunityResponse(BaseModel):
    movie_id: uuid.UUID
    rating_count: int
    average_rating: float | None
    viewer_rating: int | None
    reviews: list[ReviewResponse]
    moderation_required: bool = True


class ReportWrite(BaseModel):
    review_id: uuid.UUID | None = None
    collection_id: uuid.UUID | None = None
    reason: ReportReason
    details: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def one_target(self):
        if (self.review_id is None) == (self.collection_id is None):
            raise ValueError("Choose exactly one report target")
        return self


class ReportResponse(BaseModel):
    id: uuid.UUID
    reporter_profile_id: uuid.UUID
    review_id: uuid.UUID | None
    collection_id: uuid.UUID | None
    reason: ReportReason
    details: str | None
    status: ReportStatus
    created_at: datetime
    resolved_at: datetime | None


class SafetyResponse(BaseModel):
    target_profile_id: uuid.UUID
    kind: SafetyRelationKind


class FollowResponse(BaseModel):
    target_profile_id: uuid.UUID
    following: bool


class ActivityResponse(BaseModel):
    id: uuid.UUID
    kind: CommunityActivityKind
    actor_profile_id: uuid.UUID
    actor_profile_name: str
    review_id: uuid.UUID | None
    collection_id: uuid.UUID | None
    target_profile_id: uuid.UUID | None
    created_at: datetime


class ModerationDecision(BaseModel):
    status: ModerationStatus
    reason: str = Field(min_length=3, max_length=1000)


class ReportDecision(BaseModel):
    status: ReportStatus
    reason: str = Field(min_length=3, max_length=1000)


class ModerationQueueResponse(BaseModel):
    reviews: list[ReviewResponse]
    lists: list[CollectionResponse]
    reports: list[ReportResponse]
