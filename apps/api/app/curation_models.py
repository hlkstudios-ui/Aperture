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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class CollectionKind(StrEnum):
    editorial = "editorial"
    user_list = "user_list"
    franchise = "franchise"
    award = "award"
    director = "director"
    actor = "actor"
    country = "country"
    decade = "decade"
    genre = "genre"
    movement = "movement"
    seasonal = "seasonal"
    themed = "themed"


class CurationStatus(StrEnum):
    draft = "draft"
    published = "published"
    archived = "archived"


class Collection(Base):
    __tablename__ = "collections"
    __table_args__ = (
        CheckConstraint(
            "(kind = 'user_list') = (owner_profile_id IS NOT NULL)",
            name="ck_collections_owner_kind",
        ),
        CheckConstraint(
            "visibility IN ('private', 'unlisted', 'public')",
            name="ck_collections_visibility",
        ),
        CheckConstraint(
            "moderation_status IN ('pending', 'approved', 'rejected', 'removed')",
            name="ck_collections_moderation_status",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    visibility: Mapped[str] = mapped_column(String(16), default="private", server_default="private")
    moderation_status: Mapped[str] = mapped_column(
        String(16), default="pending", server_default="pending", index=True
    )
    kind: Mapped[CollectionKind] = mapped_column(
        Enum(CollectionKind, name="collection_kind"), index=True
    )
    status: Mapped[CurationStatus] = mapped_column(
        Enum(CurationStatus, name="curation_status"), default=CurationStatus.draft, index=True
    )
    owner_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    created_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admins.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    items: Mapped[list["CollectionItem"]] = relationship(
        cascade="all, delete-orphan", order_by="CollectionItem.position"
    )


class CollectionItem(Base):
    __tablename__ = "collection_items"
    __table_args__ = (
        CheckConstraint(
            "(movie_id IS NOT NULL)::integer + (series_id IS NOT NULL)::integer = 1",
            name="ck_collection_items_one_title",
        ),
        UniqueConstraint("collection_id", "position", name="uq_collection_items_position"),
        UniqueConstraint("collection_id", "movie_id", name="uq_collection_items_movie"),
        UniqueConstraint("collection_id", "series_id", name="uq_collection_items_series"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), index=True
    )
    movie_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"))
    series_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)


class Journey(Base):
    __tablename__ = "journeys"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[CurationStatus] = mapped_column(
        Enum(CurationStatus, name="curation_status", create_type=False),
        default=CurationStatus.draft,
        index=True,
    )
    created_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admins.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    chapters: Mapped[list["JourneyChapter"]] = relationship(
        cascade="all, delete-orphan", order_by="JourneyChapter.position"
    )


class JourneyChapter(Base):
    __tablename__ = "journey_chapters"
    __table_args__ = (
        UniqueConstraint("journey_id", "position", name="uq_journey_chapters_position"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    journey_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("journeys.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    introduction: Mapped[str | None] = mapped_column(Text)
    items: Mapped[list["JourneyItem"]] = relationship(
        cascade="all, delete-orphan", order_by="JourneyItem.position"
    )


class JourneyItem(Base):
    __tablename__ = "journey_items"
    __table_args__ = (
        CheckConstraint(
            "(movie_id IS NOT NULL)::integer + (series_id IS NOT NULL)::integer = 1",
            name="ck_journey_items_one_title",
        ),
        UniqueConstraint("chapter_id", "position", name="uq_journey_items_position"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chapter_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("journey_chapters.id", ondelete="CASCADE"), index=True
    )
    movie_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"))
    series_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    introduction: Mapped[str | None] = mapped_column(Text)


class JourneyProgress(Base):
    __tablename__ = "journey_progress"
    __table_args__ = (
        UniqueConstraint("profile_id", "journey_item_id", name="uq_journey_progress_profile_item"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    journey_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("journey_items.id", ondelete="CASCADE"), index=True
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
