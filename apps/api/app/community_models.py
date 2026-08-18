import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ModerationStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    removed = "removed"


class CommunityVisibility(StrEnum):
    private = "private"
    unlisted = "unlisted"
    public = "public"


class SafetyRelationKind(StrEnum):
    block = "block"
    mute = "mute"


class ReportStatus(StrEnum):
    open = "open"
    reviewing = "reviewing"
    resolved = "resolved"
    dismissed = "dismissed"


class ReportReason(StrEnum):
    harassment = "harassment"
    hate = "hate"
    spam = "spam"
    spoiler = "spoiler"
    impersonation = "impersonation"
    other = "other"


class CommunityActivityKind(StrEnum):
    review_published = "review_published"
    list_published = "list_published"
    profile_followed = "profile_followed"


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (
        UniqueConstraint("profile_id", "movie_id", name="uq_ratings_profile_movie"),
        CheckConstraint("score >= 1 AND score <= 5", name="ck_ratings_score"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    movie_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), index=True
    )
    score: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("profile_id", "movie_id", name="uq_reviews_profile_movie"),
        CheckConstraint("char_length(body) BETWEEN 1 AND 5000", name="ck_reviews_body_length"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    movie_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), index=True
    )
    headline: Mapped[str | None] = mapped_column(String(140))
    body: Mapped[str] = mapped_column(Text)
    contains_spoilers: Mapped[bool] = mapped_column(default=False, server_default="false")
    status: Mapped[ModerationStatus] = mapped_column(
        Enum(ModerationStatus, name="moderation_status"),
        default=ModerationStatus.pending,
        server_default=ModerationStatus.pending.value,
        index=True,
    )
    moderation_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProfileFollow(Base):
    __tablename__ = "profile_follows"
    __table_args__ = (
        UniqueConstraint("follower_profile_id", "followed_profile_id", name="uq_profile_follows"),
        CheckConstraint(
            "follower_profile_id <> followed_profile_id", name="ck_profile_follows_not_self"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    follower_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    followed_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProfileSafetyRelation(Base):
    __tablename__ = "profile_safety_relations"
    __table_args__ = (
        UniqueConstraint("actor_profile_id", "target_profile_id", "kind", name="uq_profile_safety"),
        CheckConstraint("actor_profile_id <> target_profile_id", name="ck_profile_safety_not_self"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    target_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[SafetyRelationKind] = mapped_column(
        Enum(SafetyRelationKind, name="safety_relation_kind")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CommunityReport(Base):
    __tablename__ = "community_reports"
    __table_args__ = (
        CheckConstraint(
            "(review_id IS NOT NULL)::integer + (collection_id IS NOT NULL)::integer = 1",
            name="ck_community_reports_one_target",
        ),
        UniqueConstraint("reporter_profile_id", "review_id", name="uq_reports_profile_review"),
        UniqueConstraint(
            "reporter_profile_id", "collection_id", name="uq_reports_profile_collection"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reporter_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    review_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), index=True
    )
    collection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), index=True
    )
    reason: Mapped[ReportReason] = mapped_column(Enum(ReportReason, name="report_reason"))
    details: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus, name="report_status"),
        default=ReportStatus.open,
        server_default=ReportStatus.open.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ModerationAction(Base):
    __tablename__ = "moderation_actions"
    __table_args__ = (
        CheckConstraint(
            "(review_id IS NOT NULL)::integer + (collection_id IS NOT NULL)::integer + "
            "(report_id IS NOT NULL)::integer <= 1",
            name="ck_moderation_actions_at_most_one_target",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admins.id", ondelete="RESTRICT"), index=True
    )
    review_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("reviews.id", ondelete="SET NULL"), index=True
    )
    collection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("collections.id", ondelete="SET NULL"), index=True
    )
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("community_reports.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CommunityActivity(Base):
    __tablename__ = "community_activities"
    __table_args__ = (
        CheckConstraint(
            "(kind = 'review_published' AND review_id IS NOT NULL AND collection_id IS NULL "
            "AND target_profile_id IS NULL) OR "
            "(kind = 'list_published' AND review_id IS NULL AND collection_id IS NOT NULL "
            "AND target_profile_id IS NULL) OR "
            "(kind = 'profile_followed' AND review_id IS NULL AND collection_id IS NULL "
            "AND target_profile_id IS NOT NULL)",
            name="ck_community_activities_target_kind",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[CommunityActivityKind] = mapped_column(
        Enum(CommunityActivityKind, name="community_activity_kind"), index=True
    )
    review_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), index=True
    )
    collection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), index=True
    )
    target_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
