import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
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


class ClubRole(StrEnum):
    owner = "owner"
    moderator = "moderator"
    member = "member"


class ClubMembershipStatus(StrEnum):
    invited = "invited"
    active = "active"
    left = "left"
    removed = "removed"


class ClubWatchStatus(StrEnum):
    scheduled = "scheduled"
    active = "active"
    completed = "completed"
    cancelled = "cancelled"


class PartyState(StrEnum):
    waiting = "waiting"
    playing = "playing"
    paused = "paused"
    ended = "ended"


class PartyEventKind(StrEnum):
    play = "play"
    pause = "pause"
    seek = "seek"
    ended = "ended"


class PartyMessageKind(StrEnum):
    message = "message"
    reaction = "reaction"


class MovieClub(Base):
    __tablename__ = "movie_clubs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    slug: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    invite_token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    members: Mapped[list["ClubMembership"]] = relationship(cascade="all, delete-orphan")


class ClubMembership(Base):
    __tablename__ = "club_memberships"
    __table_args__ = (
        UniqueConstraint("club_id", "profile_id", name="uq_club_memberships_profile"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("movie_clubs.id", ondelete="CASCADE"), index=True
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[ClubRole] = mapped_column(
        Enum(ClubRole, name="club_role"), default=ClubRole.member
    )
    status: Mapped[ClubMembershipStatus] = mapped_column(
        Enum(ClubMembershipStatus, name="club_membership_status"),
        default=ClubMembershipStatus.invited,
        index=True,
    )
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClubScheduledWatch(Base):
    __tablename__ = "club_scheduled_watches"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("movie_clubs.id", ondelete="CASCADE"), index=True
    )
    movie_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), index=True
    )
    playback_source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("playback_sources.id", ondelete="SET NULL")
    )
    created_by_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(String(160))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[ClubWatchStatus] = mapped_column(
        Enum(ClubWatchStatus, name="club_watch_status"),
        default=ClubWatchStatus.scheduled,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClubPoll(Base):
    __tablename__ = "club_polls"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("movie_clubs.id", ondelete="CASCADE"), index=True
    )
    created_by_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE")
    )
    question: Mapped[str] = mapped_column(String(300))
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    options: Mapped[list["ClubPollOption"]] = relationship(
        cascade="all, delete-orphan", order_by="ClubPollOption.position"
    )


class ClubPollOption(Base):
    __tablename__ = "club_poll_options"
    __table_args__ = (
        UniqueConstraint("poll_id", "position", name="uq_club_poll_options_position"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    poll_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("club_polls.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(200))
    movie_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("movies.id", ondelete="SET NULL"))
    position: Mapped[int] = mapped_column(Integer)


class ClubPollVote(Base):
    __tablename__ = "club_poll_votes"
    __table_args__ = (UniqueConstraint("poll_id", "profile_id", name="uq_club_poll_votes_profile"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    poll_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("club_polls.id", ondelete="CASCADE"), index=True
    )
    option_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("club_poll_options.id", ondelete="CASCADE")
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClubDiscussionPost(Base):
    __tablename__ = "club_discussion_posts"
    __table_args__ = (
        CheckConstraint("char_length(body) BETWEEN 1 AND 3000", name="ck_club_posts_body"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("movie_clubs.id", ondelete="CASCADE"), index=True
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    body: Mapped[str] = mapped_column(Text)
    contains_spoilers: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ClubCollection(Base):
    __tablename__ = "club_collections"
    __table_args__ = (UniqueConstraint("club_id", "collection_id", name="uq_club_collections"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("movie_clubs.id", ondelete="CASCADE"), index=True
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE")
    )
    added_by_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClubWatchHistory(Base):
    __tablename__ = "club_watch_history"
    __table_args__ = (
        UniqueConstraint("scheduled_watch_id", "profile_id", name="uq_club_watch_history_profile"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scheduled_watch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("club_scheduled_watches.id", ondelete="CASCADE"), index=True
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class WatchParty(Base):
    __tablename__ = "watch_parties"
    __table_args__ = (CheckConstraint("position_seconds >= 0", name="ck_watch_parties_position"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scheduled_watch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("club_scheduled_watches.id", ondelete="CASCADE"), unique=True
    )
    playback_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playback_sources.id", ondelete="CASCADE"), index=True
    )
    host_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    access_token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    state: Mapped[PartyState] = mapped_column(
        Enum(PartyState, name="party_state"), default=PartyState.waiting
    )
    position_seconds: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    state_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WatchPartyParticipant(Base):
    __tablename__ = "watch_party_participants"
    __table_args__ = (
        UniqueConstraint("party_id", "profile_id", name="uq_watch_party_participants_profile"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    party_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("watch_parties.id", ondelete="CASCADE"), index=True
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    entitlement_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WatchPartyEvent(Base):
    __tablename__ = "watch_party_events"
    __table_args__ = (
        UniqueConstraint("party_id", "revision", name="uq_watch_party_events_revision"),
        CheckConstraint("position_seconds >= 0", name="ck_watch_party_events_position"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    party_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("watch_parties.id", ondelete="CASCADE"), index=True
    )
    actor_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE")
    )
    kind: Mapped[PartyEventKind] = mapped_column(Enum(PartyEventKind, name="party_event_kind"))
    position_seconds: Mapped[float] = mapped_column(Float)
    revision: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WatchPartyMessage(Base):
    __tablename__ = "watch_party_messages"
    __table_args__ = (
        CheckConstraint("char_length(body) BETWEEN 1 AND 500", name="ck_watch_party_messages_body"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    party_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("watch_parties.id", ondelete="CASCADE"), index=True
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[PartyMessageKind] = mapped_column(
        Enum(PartyMessageKind, name="party_message_kind")
    )
    body: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
