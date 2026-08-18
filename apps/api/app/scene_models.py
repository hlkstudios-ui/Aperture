import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class IntelligenceVersionState(StrEnum):
    draft = "draft"
    review = "review"
    validated = "validated"
    published = "published"


class EnrichmentJobState(StrEnum):
    queued = "queued"
    running = "running"
    failed = "failed"
    completed = "completed"


class ProvenanceKind(StrEnum):
    manual = "manual"
    subtitle = "subtitle"
    transcript = "transcript"
    chapter = "chapter"
    production = "production"
    external = "external"


class SceneIntelligenceVersion(Base):
    __tablename__ = "scene_intelligence_versions"
    __table_args__ = (
        UniqueConstraint("playback_source_id", "number", name="uq_scene_versions_source_number"),
        CheckConstraint("number > 0", name="ck_scene_versions_number_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    playback_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playback_sources.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    state: Mapped[IntelligenceVersionState] = mapped_column(
        Enum(IntelligenceVersionState, name="scene_intelligence_version_state"),
        default=IntelligenceVersionState.draft,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(String(1000))
    created_by_admin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admins.id", ondelete="RESTRICT")
    )
    validated_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admins.id", ondelete="SET NULL")
    )
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    scenes: Mapped[list["Scene"]] = relationship(
        cascade="all, delete-orphan", order_by="Scene.ordinal"
    )
    chapters: Mapped[list["Chapter"]] = relationship(
        cascade="all, delete-orphan", order_by="Chapter.ordinal"
    )
    sources: Mapped[list["SceneSource"]] = relationship(cascade="all, delete-orphan")


class SceneSource(Base):
    __tablename__ = "scene_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scene_intelligence_versions.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[ProvenanceKind] = mapped_column(Enum(ProvenanceKind, name="scene_provenance_kind"))
    label: Mapped[str] = mapped_column(String(200))
    source_uri: Mapped[str | None] = mapped_column(String(1000))
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    license_basis: Mapped[str] = mapped_column(String(500))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_admin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admins.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TimedRecord:
    start_seconds: Mapped[float] = mapped_column(Float)
    end_seconds: Mapped[float] = mapped_column(Float)


class Scene(TimedRecord, Base):
    __tablename__ = "scenes"
    __table_args__ = (
        UniqueConstraint("version_id", "ordinal", name="uq_scenes_version_ordinal"),
        CheckConstraint("ordinal > 0", name="ck_scenes_ordinal_positive"),
        CheckConstraint(
            "start_seconds >= 0 AND end_seconds > start_seconds", name="ck_scenes_time_range"
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_scenes_confidence"),
        Index("ix_scenes_version_time", "version_id", "start_seconds", "end_seconds"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scene_intelligence_versions.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scene_sources.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(250))
    summary: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    manually_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Chapter(TimedRecord, Base):
    __tablename__ = "chapters"
    __table_args__ = (
        UniqueConstraint("version_id", "ordinal", name="uq_chapters_version_ordinal"),
        CheckConstraint("ordinal > 0", name="ck_chapters_ordinal_positive"),
        CheckConstraint(
            "start_seconds >= 0 AND end_seconds > start_seconds", name="ck_chapters_time_range"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scene_intelligence_versions.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scene_sources.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(250))


class SceneCharacter(Base):
    __tablename__ = "scene_characters"
    __table_args__ = (
        UniqueConstraint("scene_id", "character_id", name="uq_scene_characters_scene_character"),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_scene_characters_confidence"
        ),
        CheckConstraint("reveal_seconds >= 0", name="ck_scene_characters_reveal"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scene_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), index=True
    )
    character_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scene_sources.id", ondelete="CASCADE"))
    confidence: Mapped[float] = mapped_column(Float)
    reveal_seconds: Mapped[float] = mapped_column(Float)
    manually_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class SceneEntity(Base):
    __tablename__ = "scene_entities"
    __table_args__ = (
        UniqueConstraint("scene_id", "canonical_key", name="uq_scene_entities_scene_key"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_scene_entities_confidence"),
        CheckConstraint("reveal_seconds >= 0", name="ck_scene_entities_reveal"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scene_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scene_sources.id", ondelete="CASCADE"))
    entity_type: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(250))
    canonical_key: Mapped[str] = mapped_column(String(280))
    description: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    reveal_seconds: Mapped[float] = mapped_column(Float)


class SceneRelationship(Base):
    __tablename__ = "scene_relationships"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_scene_relationships_confidence"
        ),
        CheckConstraint("reveal_seconds >= 0", name="ck_scene_relationships_reveal"),
        CheckConstraint(
            "subject_entity_id <> object_entity_id", name="ck_scene_relationships_distinct"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scene_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scene_sources.id", ondelete="CASCADE"))
    subject_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scene_entities.id", ondelete="CASCADE")
    )
    object_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scene_entities.id", ondelete="CASCADE")
    )
    relationship: Mapped[str] = mapped_column(String(250))
    confidence: Mapped[float] = mapped_column(Float)
    reveal_seconds: Mapped[float] = mapped_column(Float)


class MusicCue(TimedRecord, Base):
    __tablename__ = "music_cues"
    __table_args__ = (
        CheckConstraint(
            "start_seconds >= 0 AND end_seconds > start_seconds", name="ck_music_cues_time_range"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scene_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scene_sources.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(250))
    composer: Mapped[str | None] = mapped_column(String(250))
    performer: Mapped[str | None] = mapped_column(String(250))


class ProductionNote(Base):
    __tablename__ = "production_notes"
    __table_args__ = (CheckConstraint("reveal_seconds >= 0", name="ck_production_notes_reveal"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scene_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scene_sources.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(100))
    note: Mapped[str] = mapped_column(Text)
    reveal_seconds: Mapped[float] = mapped_column(Float)


class SpoilerBoundary(Base):
    __tablename__ = "spoiler_boundaries"
    __table_args__ = (CheckConstraint("reveal_seconds >= 0", name="ck_spoiler_boundaries_reveal"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scene_intelligence_versions.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scene_sources.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(250))
    description: Mapped[str] = mapped_column(Text)
    reveal_seconds: Mapped[float] = mapped_column(Float)


class SceneIntelligenceJob(Base):
    __tablename__ = "scene_intelligence_jobs"
    __table_args__ = (
        CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100", name="ck_scene_jobs_progress"
        ),
        Index("ix_scene_jobs_state_created", "state", "created_at"),
        Index("ix_scene_jobs_lease_expiry", "lease_expires_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scene_intelligence_versions.id", ondelete="CASCADE"), index=True
    )
    state: Mapped[EnrichmentJobState] = mapped_column(
        Enum(EnrichmentJobState, name="scene_enrichment_job_state"), index=True
    )
    stage: Mapped[str] = mapped_column(String(100), default="queued", server_default="queued")
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(String(1000))
    created_by_admin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admins.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[SceneIntelligenceVersion] = relationship()


class TranscriptCue(TimedRecord, Base):
    __tablename__ = "transcript_cues"
    __table_args__ = (
        CheckConstraint(
            "start_seconds >= 0 AND end_seconds > start_seconds",
            name="ck_transcript_cues_time_range",
        ),
        Index("ix_transcript_cues_version_time", "version_id", "start_seconds", "end_seconds"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scene_intelligence_versions.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scene_sources.id", ondelete="CASCADE"), index=True
    )
    scene_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("scenes.id", ondelete="SET NULL"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    speaker_label: Mapped[str | None] = mapped_column(String(250))
    confidence: Mapped[float] = mapped_column(Float, default=1, server_default="1")


class SceneSearchDocument(Base):
    __tablename__ = "scene_search_documents"

    scene_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), primary_key=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scene_intelligence_versions.id", ondelete="CASCADE"), index=True
    )
    searchable_text: Mapped[str] = mapped_column(Text)
    search_vector: Mapped[object] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', coalesce(searchable_text, ''))", persisted=True),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


Index("ix_scene_search_documents_vector", SceneSearchDocument.search_vector, postgresql_using="gin")
