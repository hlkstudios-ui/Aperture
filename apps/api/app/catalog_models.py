import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class CatalogStatus(StrEnum):
    draft = "draft"
    ready = "ready"
    published = "published"
    archived = "archived"


class ArtworkKind(StrEnum):
    poster = "poster"
    landscape = "landscape"
    backdrop = "backdrop"
    logo = "logo"
    mobile = "mobile"
    still = "still"


class PreviewKind(StrEnum):
    trailer = "trailer"
    clip = "clip"


class EditionDifferenceKind(StrEnum):
    inserted_scene = "inserted_scene"
    removed_scene = "removed_scene"
    presentation = "presentation"
    restoration = "restoration"
    audio = "audio"
    editorial = "editorial"


class TitleRelationshipKind(StrEnum):
    sequel = "sequel"
    prequel = "prequel"
    remake = "remake"
    remade_as = "remade_as"
    adaptation = "adaptation"
    source_material = "source_material"
    influenced_by = "influenced_by"
    influenced = "influenced"
    companion = "companion"


movie_genres = Table(
    "movie_genres",
    Base.metadata,
    Column("movie_id", ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True),
    Column("genre_id", ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
)
movie_themes = Table(
    "movie_themes",
    Base.metadata,
    Column("movie_id", ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True),
    Column("theme_id", ForeignKey("themes.id", ondelete="CASCADE"), primary_key=True),
)
movie_tags = Table(
    "movie_tags",
    Base.metadata,
    Column("movie_id", ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)
series_genres = Table(
    "series_genres",
    Base.metadata,
    Column("series_id", ForeignKey("series.id", ondelete="CASCADE"), primary_key=True),
    Column("genre_id", ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
)


class NamedCatalogRecord:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(180), unique=True, index=True)


class Genre(NamedCatalogRecord, Base):
    __tablename__ = "genres"


class Theme(NamedCatalogRecord, Base):
    __tablename__ = "themes"


class Tag(NamedCatalogRecord, Base):
    __tablename__ = "tags"


class Language(Base):
    __tablename__ = "languages"
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)


class Country(Base):
    __tablename__ = "countries"
    code: Mapped[str] = mapped_column(String(2), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)


class Franchise(NamedCatalogRecord, Base):
    __tablename__ = "franchises"
    description: Mapped[str | None] = mapped_column(Text)


class Company(NamedCatalogRecord, Base):
    __tablename__ = "companies"
    __table_args__ = (
        Index(
            "ix_companies_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )
    country_code: Mapped[str | None] = mapped_column(ForeignKey("countries.code"))


class Person(Base):
    __tablename__ = "people"
    __table_args__ = (
        Index(
            "ix_people_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(180), index=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    biography: Mapped[str | None] = mapped_column(Text)
    birth_date: Mapped[date | None] = mapped_column(Date)
    country_code: Mapped[str | None] = mapped_column(ForeignKey("countries.code"))


class Character(Base):
    __tablename__ = "characters"
    __table_args__ = (
        Index(
            "ix_characters_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(180), index=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)


class Movie(Base):
    __tablename__ = "movies"
    __table_args__ = (
        CheckConstraint("runtime_minutes > 0", name="ck_movies_runtime_positive"),
        CheckConstraint(
            "rights_start_at IS NULL OR rights_end_at IS NULL OR rights_end_at > rights_start_at",
            name="ck_movies_rights_window",
        ),
        CheckConstraint(
            "publish_at IS NULL OR unpublish_at IS NULL OR unpublish_at > publish_at",
            name="ck_movies_publish_window",
        ),
        CheckConstraint(
            "jsonb_typeof(allowed_territories) = 'array'",
            name="ck_movies_allowed_territories_array",
        ),
        Index("ix_movies_status_release_date", "status", "release_date"),
        Index("ix_movies_allowed_territories", "allowed_territories", postgresql_using="gin"),
        Index(
            "ix_movies_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
        Index(
            "ix_movies_original_title_trgm",
            "original_title",
            postgresql_using="gin",
            postgresql_ops={"original_title": "gin_trgm_ops"},
        ),
        Index(
            "uq_movies_provider_external_id",
            "metadata_provider",
            "external_id",
            unique=True,
            postgresql_where=text("metadata_provider IS NOT NULL AND external_id IS NOT NULL"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(250), index=True)
    slug: Mapped[str] = mapped_column(String(280), unique=True, index=True)
    original_title: Mapped[str | None] = mapped_column(String(250))
    short_description: Mapped[str] = mapped_column(String(500))
    synopsis: Mapped[str] = mapped_column(Text)
    release_date: Mapped[date | None] = mapped_column(Date, index=True)
    runtime_minutes: Mapped[int] = mapped_column(Integer)
    maturity_rating: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[CatalogStatus] = mapped_column(
        Enum(CatalogStatus, name="catalog_status"), default=CatalogStatus.draft, index=True
    )
    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    unpublish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    rights_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    rights_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    original_language_code: Mapped[str | None] = mapped_column(ForeignKey("languages.code"))
    country_code: Mapped[str | None] = mapped_column(ForeignKey("countries.code"))
    allowed_territories: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    franchise_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("franchises.id"))
    metadata_provider: Mapped[str | None] = mapped_column(String(32), index=True)
    external_id: Mapped[str | None] = mapped_column(String(64), index=True)
    poster_url: Mapped[str | None] = mapped_column(String(1000))
    backdrop_url: Mapped[str | None] = mapped_column(String(1000))
    content_format: Mapped[str | None] = mapped_column(String(32), index=True)
    studios: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    genres: Mapped[list[Genre]] = relationship(secondary=movie_genres)
    themes: Mapped[list[Theme]] = relationship(secondary=movie_themes)
    tags: Mapped[list[Tag]] = relationship(secondary=movie_tags)


class Series(Base):
    __tablename__ = "series"
    __table_args__ = (
        CheckConstraint(
            "rights_start_at IS NULL OR rights_end_at IS NULL OR rights_end_at > rights_start_at",
            name="ck_series_rights_window",
        ),
        CheckConstraint(
            "publish_at IS NULL OR unpublish_at IS NULL OR unpublish_at > publish_at",
            name="ck_series_publish_window",
        ),
        CheckConstraint(
            "jsonb_typeof(allowed_territories) = 'array'",
            name="ck_series_allowed_territories_array",
        ),
        Index("ix_series_status_release_date", "status", "release_date"),
        Index("ix_series_allowed_territories", "allowed_territories", postgresql_using="gin"),
        Index(
            "ix_series_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
        Index(
            "ix_series_original_title_trgm",
            "original_title",
            postgresql_using="gin",
            postgresql_ops={"original_title": "gin_trgm_ops"},
        ),
        Index(
            "uq_series_provider_external_id",
            "metadata_provider",
            "external_id",
            unique=True,
            postgresql_where=text("metadata_provider IS NOT NULL AND external_id IS NOT NULL"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(250), index=True)
    slug: Mapped[str] = mapped_column(String(280), unique=True, index=True)
    original_title: Mapped[str | None] = mapped_column(String(250))
    short_description: Mapped[str] = mapped_column(String(500))
    synopsis: Mapped[str] = mapped_column(Text)
    release_date: Mapped[date | None] = mapped_column(Date, index=True)
    maturity_rating: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[CatalogStatus] = mapped_column(
        Enum(CatalogStatus, name="catalog_status", create_type=False),
        default=CatalogStatus.draft,
        index=True,
    )
    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    unpublish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    rights_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    rights_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    original_language_code: Mapped[str | None] = mapped_column(ForeignKey("languages.code"))
    country_code: Mapped[str | None] = mapped_column(ForeignKey("countries.code"))
    allowed_territories: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    franchise_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("franchises.id"))
    metadata_provider: Mapped[str | None] = mapped_column(String(32), index=True)
    external_id: Mapped[str | None] = mapped_column(String(64), index=True)
    poster_url: Mapped[str | None] = mapped_column(String(1000))
    backdrop_url: Mapped[str | None] = mapped_column(String(1000))
    is_ongoing: Mapped[bool | None] = mapped_column(Boolean, index=True)
    content_format: Mapped[str | None] = mapped_column(String(32), index=True)
    studios: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    genres: Mapped[list[Genre]] = relationship(secondary=series_genres)
    seasons: Mapped[list["Season"]] = relationship(
        back_populates="series", cascade="all, delete-orphan", order_by="Season.number"
    )


class Season(Base):
    __tablename__ = "seasons"
    __table_args__ = (UniqueConstraint("series_id", "number", name="uq_seasons_series_number"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    series_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(String(250))
    synopsis: Mapped[str | None] = mapped_column(Text)
    series: Mapped[Series] = relationship(back_populates="seasons")
    episodes: Mapped[list["Episode"]] = relationship(
        back_populates="season", cascade="all, delete-orphan", order_by="Episode.number"
    )


class Episode(Base):
    __tablename__ = "episodes"
    __table_args__ = (
        UniqueConstraint("season_id", "number", name="uq_episodes_season_number"),
        CheckConstraint("runtime_minutes > 0", name="ck_episodes_runtime_positive"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    season_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("seasons.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(250), index=True)
    synopsis: Mapped[str] = mapped_column(Text)
    runtime_minutes: Mapped[int] = mapped_column(Integer)
    release_date: Mapped[date | None] = mapped_column(Date)
    still_url: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[CatalogStatus] = mapped_column(
        Enum(CatalogStatus, name="catalog_status", create_type=False), default=CatalogStatus.draft
    )
    season: Mapped[Season] = relationship(back_populates="episodes")


class Edition(Base):
    __tablename__ = "editions"
    __table_args__ = (
        CheckConstraint(
            "(movie_id IS NOT NULL)::integer + (episode_id IS NOT NULL)::integer = 1",
            name="ck_editions_one_parent",
        ),
        UniqueConstraint("movie_id", "name", name="uq_editions_movie_name"),
        UniqueConstraint("episode_id", "name", name="uq_editions_episode_name"),
        CheckConstraint(
            "rights_start_at IS NULL OR rights_end_at IS NULL OR rights_end_at > rights_start_at",
            name="ck_editions_rights_window",
        ),
        CheckConstraint("frame_rate IS NULL OR frame_rate > 0", name="ck_editions_frame_rate"),
        CheckConstraint(
            "jsonb_typeof(allowed_territories) = 'array'",
            name="ck_editions_allowed_territories_array",
        ),
        Index(
            "ix_editions_allowed_territories",
            "allowed_territories",
            postgresql_using="gin",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    movie_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), index=True
    )
    episode_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    runtime_minutes: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    rights_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    rights_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    allowed_territories: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    intended_presentation: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    aspect_ratio: Mapped[str | None] = mapped_column(String(32))
    frame_rate: Mapped[float | None] = mapped_column(Float)
    presentation_format: Mapped[str | None] = mapped_column(String(120))
    capture_format: Mapped[str | None] = mapped_column(String(120))
    audio_format: Mapped[str | None] = mapped_column(String(120))
    original_language_code: Mapped[str | None] = mapped_column(ForeignKey("languages.code"))
    restoration_info: Mapped[str | None] = mapped_column(Text)
    source_info: Mapped[str | None] = mapped_column(Text)


class EditionDifference(Base):
    __tablename__ = "edition_differences"
    __table_args__ = (
        CheckConstraint(
            "source_edition_id <> target_edition_id", name="ck_edition_differences_distinct"
        ),
        CheckConstraint(
            "reveal_seconds IS NULL OR reveal_seconds >= 0",
            name="ck_edition_differences_reveal",
        ),
        UniqueConstraint(
            "source_edition_id",
            "target_edition_id",
            "kind",
            "description",
            name="uq_edition_differences_fact",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_edition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("editions.id", ondelete="CASCADE"), index=True
    )
    target_edition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("editions.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[EditionDifferenceKind] = mapped_column(
        Enum(EditionDifferenceKind, name="edition_difference_kind")
    )
    description: Mapped[str] = mapped_column(Text)
    reveal_seconds: Mapped[float | None] = mapped_column(Float)
    source_note: Mapped[str] = mapped_column(Text)
    manually_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class TitleRelationship(Base):
    __tablename__ = "title_relationships"
    __table_args__ = (
        CheckConstraint(
            "source_movie_id <> target_movie_id", name="ck_title_relationships_distinct"
        ),
        UniqueConstraint(
            "source_movie_id",
            "target_movie_id",
            "kind",
            name="uq_title_relationships_fact",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_movie_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), index=True
    )
    target_movie_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[TitleRelationshipKind] = mapped_column(
        Enum(TitleRelationshipKind, name="title_relationship_kind"), index=True
    )
    description: Mapped[str | None] = mapped_column(Text)
    source_note: Mapped[str] = mapped_column(Text)
    manually_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class Credit(Base):
    __tablename__ = "credits"
    __table_args__ = (
        CheckConstraint(
            "(movie_id IS NOT NULL)::integer + (series_id IS NOT NULL)::integer + "
            "(episode_id IS NOT NULL)::integer = 1",
            name="ck_credits_one_title",
        ),
        Index("ix_credits_person_role", "person_id", "role"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    movie_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), index=True
    )
    series_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), index=True
    )
    episode_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), index=True
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"), index=True
    )
    character_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL")
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL")
    )
    role: Mapped[str] = mapped_column(String(100))
    billing_order: Mapped[int | None] = mapped_column(Integer)


class Artwork(Base):
    __tablename__ = "artwork"
    __table_args__ = (
        CheckConstraint(
            "(movie_id IS NOT NULL)::integer + (series_id IS NOT NULL)::integer + "
            "(season_id IS NOT NULL)::integer + (episode_id IS NOT NULL)::integer = 1",
            name="ck_artwork_one_title",
        ),
        Index("ix_artwork_movie_kind", "movie_id", "kind"),
        CheckConstraint(
            "timestamp_seconds IS NULL OR timestamp_seconds >= 0",
            name="ck_artwork_timestamp_nonnegative",
        ),
        CheckConstraint(
            "NOT permitted_for_gallery OR "
            "(kind = 'still' AND scene_id IS NOT NULL AND timestamp_seconds IS NOT NULL "
            "AND rights_basis IS NOT NULL)",
            name="ck_artwork_permitted_gallery_metadata",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    movie_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), index=True
    )
    series_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), index=True
    )
    season_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("seasons.id", ondelete="CASCADE"), index=True
    )
    episode_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[ArtworkKind] = mapped_column(Enum(ArtworkKind, name="artwork_kind"))
    scene_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), index=True
    )
    timestamp_seconds: Mapped[float | None] = mapped_column(Float)
    rights_basis: Mapped[str | None] = mapped_column(Text)
    permitted_for_gallery: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    storage_key: Mapped[str] = mapped_column(String(500))
    alt_text: Mapped[str] = mapped_column(String(500))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)


class TrailerClip(Base):
    __tablename__ = "trailer_clips"
    __table_args__ = (
        CheckConstraint(
            "(movie_id IS NOT NULL)::integer + (series_id IS NOT NULL)::integer + "
            "(episode_id IS NOT NULL)::integer = 1",
            name="ck_trailer_clips_one_title",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    movie_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), index=True
    )
    series_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), index=True
    )
    episode_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[PreviewKind] = mapped_column(Enum(PreviewKind, name="preview_kind"))
    title: Mapped[str] = mapped_column(String(250))
    storage_key: Mapped[str | None] = mapped_column(String(500))
    external_url: Mapped[str | None] = mapped_column(String(1000))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
