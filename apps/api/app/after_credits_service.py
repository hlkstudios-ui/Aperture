import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.after_credits_schemas import (
    AfterCreditsModule,
    AfterCreditsPerson,
    AfterCreditsRecommendation,
    AfterCreditsResponse,
)
from app.catalog_models import Credit, Episode, Movie, Person, Season, Series
from app.models import PlaybackSource, ViewingActivity
from app.scene_models import (
    IntelligenceVersionState,
    ProductionNote,
    Scene,
    SceneIntelligenceVersion,
    SceneSource,
)
from app.scheduling import availability_clause

MODULE_KINDS = {
    "ending_analysis": "Ending analysis",
    "easter_egg": "Easter egg",
    "production_story": "Production story",
    "behind_the_scenes": "Behind the scenes",
    "deleted_scene": "Deleted scene",
    "commentary": "Commentary",
    "critical_essay": "Critical essay",
}


def title_source_clause(source: PlaybackSource):
    return (
        PlaybackSource.movie_id == source.movie_id
        if source.movie_id
        else PlaybackSource.episode_id == source.episode_id
    )


def after_credits_room(
    db: Session,
    source: PlaybackSource,
    profile_id: uuid.UUID,
    country: str | None = None,
) -> AfterCreditsResponse:
    title = (
        db.get(Movie, source.movie_id) if source.movie_id else db.get(Episode, source.episode_id)
    )
    completion = db.scalar(
        select(ViewingActivity)
        .join(PlaybackSource, ViewingActivity.playback_source_id == PlaybackSource.id)
        .where(
            ViewingActivity.profile_id == profile_id,
            ViewingActivity.completed.is_(True),
            title_source_clause(source),
        )
        .order_by(ViewingActivity.completed_at.desc().nullslast())
        .limit(1)
    )
    if completion is None:
        return AfterCreditsResponse(
            playback_source_id=source.id,
            title=title.title,
            unlocked=False,
            completed_at=None,
            modules=[],
            people=[],
            recommended_next=[],
            safety_state="locked_until_profile_completion",
        )

    notes = db.execute(
        select(ProductionNote, SceneSource)
        .join(Scene, ProductionNote.scene_id == Scene.id)
        .join(SceneIntelligenceVersion, Scene.version_id == SceneIntelligenceVersion.id)
        .join(SceneSource, ProductionNote.source_id == SceneSource.id)
        .where(
            SceneIntelligenceVersion.playback_source_id == source.id,
            SceneIntelligenceVersion.state == IntelligenceVersionState.published,
            ProductionNote.category.in_(MODULE_KINDS),
        )
        .order_by(ProductionNote.reveal_seconds, ProductionNote.id)
    ).all()
    modules = [
        AfterCreditsModule(
            id=note.id,
            kind=note.category,
            title=MODULE_KINDS[note.category],
            body=note.note,
            source_label=evidence.label,
        )
        for note, evidence in notes
    ]
    credit_clause = (
        Credit.movie_id == source.movie_id
        if source.movie_id
        else Credit.episode_id == source.episode_id
    )
    people = []
    for credit in db.scalars(
        select(Credit).where(credit_clause).order_by(Credit.billing_order.asc().nullslast())
    ):
        person = db.get(Person, credit.person_id)
        if person:
            people.append(AfterCreditsPerson(name=person.name, slug=person.slug, role=credit.role))

    recommendations: list[AfterCreditsRecommendation] = []
    if source.movie_id:
        movie = db.get(Movie, source.movie_id)
        if movie.franchise_id:
            related = db.scalars(
                select(Movie)
                .where(
                    Movie.franchise_id == movie.franchise_id,
                    Movie.id != movie.id,
                    availability_clause(Movie, country=country),
                )
                .order_by(Movie.release_date.asc().nullslast())
                .limit(4)
            )
            recommendations = [
                AfterCreditsRecommendation(
                    kind="movie",
                    title=item.title,
                    href=f"/movies/{item.slug}",
                    reason="More from this franchise",
                )
                for item in related
            ]
    else:
        episode = db.get(Episode, source.episode_id)
        season = db.get(Season, episode.season_id)
        series = db.get(Series, season.series_id)
        next_episode = db.scalar(
            select(Episode)
            .join(Season, Episode.season_id == Season.id)
            .where(
                Season.series_id == series.id,
                (Season.number > season.number)
                | ((Season.number == season.number) & (Episode.number > episode.number)),
            )
            .order_by(Season.number, Episode.number)
            .limit(1)
        )
        if next_episode:
            recommendations.append(
                AfterCreditsRecommendation(
                    kind="episode",
                    title=next_episode.title,
                    href=f"/series/{series.slug}",
                    reason="Continue the series",
                )
            )
    return AfterCreditsResponse(
        playback_source_id=source.id,
        title=title.title,
        unlocked=True,
        completed_at=completion.completed_at.isoformat() if completion.completed_at else None,
        modules=modules,
        people=people,
        recommended_next=recommendations,
        safety_state="completion_verified_sourced_modules_only",
    )
