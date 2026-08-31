import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ExploreEntry(Base):
    __tablename__ = "explore_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    label: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(String(180), default="", server_default="")
    icon: Mapped[str] = mapped_column(String(16), default="↗", server_default="↗")
    position: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    criteria: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'::json"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    cards: Mapped[list["ExploreEntryCard"]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="ExploreEntryCard.position",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("position", name="uq_explore_entries_position"),
        CheckConstraint("position >= 0", name="ck_explore_entries_position"),
        Index("uq_explore_entries_label_ci", func.lower(label), unique=True),
    )


class ExploreEntryCard(Base):
    __tablename__ = "explore_entry_cards"
    __table_args__ = (
        CheckConstraint(
            "(movie_id IS NOT NULL)::integer + (series_id IS NOT NULL)::integer = 1",
            name="ck_explore_entry_cards_exactly_one_title",
        ),
        CheckConstraint("position >= 0", name="ck_explore_entry_cards_position"),
        UniqueConstraint("entry_id", "position", name="uq_explore_entry_cards_position"),
        UniqueConstraint("entry_id", "movie_id", name="uq_explore_entry_cards_movie"),
        UniqueConstraint("entry_id", "series_id", name="uq_explore_entry_cards_series"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("explore_entries.id", ondelete="CASCADE"), index=True
    )
    movie_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), index=True
    )
    series_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    entry: Mapped[ExploreEntry] = relationship(back_populates="cards")
