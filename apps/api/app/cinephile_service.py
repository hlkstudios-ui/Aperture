import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog_models import (
    Artwork,
    ArtworkKind,
    Character,
    Company,
    Credit,
    Edition,
    EditionDifference,
    Episode,
    Movie,
    Person,
)
from app.cinephile_schemas import (
    CinephileToolkitResponse,
    EditionComparisonEntry,
    EditionEntry,
    ExplorerCredit,
    FilmmakingEntry,
    GalleryStill,
    MusicTimelineEntry,
    RewatchIntelligence,
)
from app.models import (
    PlaybackSource,
    ProcessingState,
    ProfilePreference,
    SceneBookmark,
    SceneNote,
    ViewingActivity,
)
from app.scene_models import Scene
from app.spoiler_service import spoiler_context


def artwork_parent_clause(source: PlaybackSource):
    return (
        Artwork.movie_id == source.movie_id
        if source.movie_id
        else Artwork.episode_id == source.episode_id
    )


def title_source_clause(source: PlaybackSource):
    return (
        PlaybackSource.movie_id == source.movie_id
        if source.movie_id
        else PlaybackSource.episode_id == source.episode_id
    )


def cinephile_toolkit(
    db: Session,
    *,
    playback_source: PlaybackSource,
    profile_id: uuid.UUID,
    timestamp: float,
) -> CinephileToolkitResponse:
    context = spoiler_context(
        db,
        playback_source=playback_source,
        profile_id=profile_id,
        timestamp=timestamp,
        mode="protected",
    )
    title = (
        db.get(Movie, playback_source.movie_id)
        if playback_source.movie_id
        else db.get(Episode, playback_source.episode_id)
    )
    artwork = list(
        db.scalars(
            select(Artwork)
            .join(Scene, Artwork.scene_id == Scene.id)
            .where(
                artwork_parent_clause(playback_source),
                Artwork.kind == ArtworkKind.still,
                Artwork.permitted_for_gallery.is_(True),
                Artwork.timestamp_seconds <= context.effective_cutoff,
                Scene.version_id == context.version_id,
            )
            .order_by(Artwork.timestamp_seconds, Artwork.id)
        )
    )
    credit_records = list(
        db.scalars(
            select(Credit)
            .where(
                Credit.movie_id == playback_source.movie_id
                if playback_source.movie_id
                else Credit.episode_id == playback_source.episode_id
            )
            .order_by(Credit.billing_order.asc().nullslast(), Credit.id)
        )
    )
    credits = []
    for credit in credit_records:
        person = db.get(Person, credit.person_id)
        if person is None:
            continue
        character = db.get(Character, credit.character_id) if credit.character_id else None
        company = db.get(Company, credit.company_id) if credit.company_id else None
        credits.append(
            ExplorerCredit(
                person_id=person.id,
                person_name=person.name,
                person_slug=person.slug,
                role=credit.role,
                character_name=character.name if character else None,
                company_name=company.name if company else None,
                billing_order=credit.billing_order,
            )
        )
    editions = list(
        db.scalars(
            select(Edition)
            .where(
                Edition.movie_id == playback_source.movie_id
                if playback_source.movie_id
                else Edition.episode_id == playback_source.episode_id
            )
            .order_by(Edition.is_default.desc(), Edition.name)
        )
    )
    title_sources = list(
        db.scalars(select(PlaybackSource).where(title_source_clause(playback_source)))
    )
    source_by_edition = {source.edition_id: source for source in title_sources if source.edition_id}
    activities = list(
        db.scalars(
            select(ViewingActivity)
            .where(
                ViewingActivity.profile_id == profile_id,
                ViewingActivity.playback_source_id == playback_source.id,
            )
            .order_by(ViewingActivity.activity_number)
        )
    )
    title_completed = (
        db.scalar(
            select(ViewingActivity.id)
            .join(PlaybackSource, ViewingActivity.playback_source_id == PlaybackSource.id)
            .where(
                ViewingActivity.profile_id == profile_id,
                ViewingActivity.completed.is_(True),
                title_source_clause(playback_source),
            )
            .limit(1)
        )
        is not None
    )
    edition_ids = [edition.id for edition in editions]
    comparisons = (
        list(
            db.scalars(
                select(EditionDifference)
                .where(
                    EditionDifference.source_edition_id.in_(edition_ids),
                    EditionDifference.target_edition_id.in_(edition_ids),
                    EditionDifference.manually_verified.is_(True),
                )
                .order_by(EditionDifference.kind, EditionDifference.id)
            )
        )
        if title_completed and edition_ids
        else []
    )
    music = [
        MusicTimelineEntry(
            title=str(fact.payload["title"]),
            composer=str(fact.payload["composer"]) if fact.payload.get("composer") else None,
            performer=str(fact.payload["performer"]) if fact.payload.get("performer") else None,
            start_seconds=fact.reveal_seconds,
            end_seconds=float(fact.payload["end_seconds"]),
        )
        for fact in context.facts
        if fact.kind == "music_cue" and fact.reveal_seconds <= context.effective_cutoff
    ]
    filmmaking = [
        FilmmakingEntry(
            category=str(fact.payload["category"]),
            note=str(fact.payload["note"]),
            reveal_seconds=fact.reveal_seconds,
        )
        for fact in context.facts
        if fact.kind == "production_note" and fact.reveal_seconds <= context.effective_cutoff
    ]
    completed = [activity for activity in activities if activity.completed]
    preference = db.get(ProfilePreference, profile_id)
    rewatch_enabled = preference is None or preference.rewatch_intelligence_enabled
    rewatch_active = rewatch_enabled and any(activity.is_rewatch for activity in activities)
    sibling_source_ids = [item.id for item in title_sources]
    saved_scenes = (
        list(
            db.scalars(
                select(SceneBookmark)
                .where(
                    SceneBookmark.profile_id == profile_id,
                    SceneBookmark.playback_source_id.in_(sibling_source_ids),
                )
                .order_by(SceneBookmark.created_at.desc())
            )
        )
        if rewatch_active
        else []
    )
    personal_notes = (
        list(
            db.scalars(
                select(SceneNote)
                .where(
                    SceneNote.profile_id == profile_id,
                    SceneNote.playback_source_id.in_(sibling_source_ids),
                )
                .order_by(SceneNote.updated_at.desc())
            )
        )
        if rewatch_active
        else []
    )
    return CinephileToolkitResponse(
        playback_source_id=playback_source.id,
        title=title.title,
        effective_cutoff=context.effective_cutoff,
        stills=[
            GalleryStill(
                id=item.id,
                alt_text=item.alt_text,
                width=item.width,
                height=item.height,
                timestamp_seconds=float(item.timestamp_seconds),
                image_url=(
                    f"/cinephile/sources/{playback_source.id}/stills/{item.id}"
                    f"?timestamp={context.effective_cutoff}"
                ),
            )
            for item in artwork
        ],
        music_timeline=music,
        filmmaking=filmmaking,
        credits=credits,
        editions=[
            EditionEntry(
                id=item.id,
                name=item.name,
                runtime_minutes=item.runtime_minutes,
                notes=item.notes,
                is_default=item.is_default,
                available=(
                    (item.rights_start_at is None or item.rights_start_at <= datetime.now(UTC))
                    and (item.rights_end_at is None or item.rights_end_at > datetime.now(UTC))
                    and item.id in source_by_edition
                    and source_by_edition[item.id].processing_job.state == ProcessingState.ready
                ),
                playback_source_id=source_by_edition[item.id].id
                if item.id in source_by_edition
                else None,
                intended_presentation=item.intended_presentation,
                aspect_ratio=item.aspect_ratio,
                frame_rate=item.frame_rate,
                presentation_format=item.presentation_format,
                capture_format=item.capture_format,
                audio_format=item.audio_format,
                original_language_code=item.original_language_code,
                restoration_info=item.restoration_info,
                source_info=item.source_info,
                audio_tracks=source_by_edition[item.id].processing_job.audio_tracks
                if item.id in source_by_edition
                else [],
                subtitle_tracks=source_by_edition[item.id].processing_job.subtitle_tracks
                if item.id in source_by_edition
                else [],
            )
            for item in editions
        ],
        edition_comparison_unlocked=title_completed,
        edition_comparisons=[
            EditionComparisonEntry(
                id=item.id,
                source_edition_id=item.source_edition_id,
                target_edition_id=item.target_edition_id,
                kind=item.kind,
                description=item.description,
                reveal_seconds=item.reveal_seconds,
            )
            for item in comparisons
        ],
        rewatch=RewatchIntelligence(
            viewings_started=len(activities),
            completed_viewings=len(completed),
            rewatches_started=sum(activity.is_rewatch for activity in activities),
            latest_completed_at=max(
                (activity.completed_at for activity in completed if activity.completed_at),
                default=None,
            ).isoformat()
            if any(activity.completed_at for activity in completed)
            else None,
            enabled=rewatch_enabled,
            active=rewatch_active,
            saved_scenes=[
                {
                    "id": str(item.id),
                    "title": item.title,
                    "timestamp_seconds": item.timestamp_seconds,
                }
                for item in saved_scenes
            ],
            personal_notes=[
                {
                    "id": str(item.id),
                    "body": item.body,
                    "timestamp_seconds": item.timestamp_seconds,
                }
                for item in personal_notes
            ],
            spoiler_aware_insights_available=rewatch_active and bool(title_completed),
        ),
        safety_state=context.safety_state,
    )
