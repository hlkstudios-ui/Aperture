import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.auth import DbSession, require_admin, require_trusted_origin
from app.catalog_models import Character, Episode, Movie
from app.models import Admin, AuditLog, PlaybackSource
from app.scene_models import (
    Chapter,
    EnrichmentJobState,
    IntelligenceVersionState,
    MusicCue,
    ProductionNote,
    Scene,
    SceneCharacter,
    SceneEntity,
    SceneIntelligenceJob,
    SceneIntelligenceVersion,
    SceneRelationship,
    SceneSearchDocument,
    SceneSource,
    SpoilerBoundary,
    TranscriptCue,
)
from app.scene_queue import enqueue_scene_job
from app.scene_schemas import (
    ChapterCreate,
    CharacterCreate,
    EntityCreate,
    JobResponse,
    MusicCueCreate,
    ProductionNoteCreate,
    RelationshipCreate,
    SceneCreate,
    SceneResponse,
    SceneUpdate,
    SourceCreate,
    SourceResponse,
    SpoilerBoundaryCreate,
    VersionCreate,
    VersionDetail,
    VersionResponse,
)

router = APIRouter(
    prefix="/admin/scenes",
    tags=["administrator scene intelligence"],
    dependencies=[Depends(require_trusted_origin), Depends(require_admin)],
)
AdminIdentity = Annotated[Admin, Depends(require_admin)]


def record_dict(record) -> dict:
    return {column.name: getattr(record, column.name) for column in record.__table__.columns}


def version_or_404(db: DbSession, version_id: uuid.UUID) -> SceneIntelligenceVersion:
    version = db.get(SceneIntelligenceVersion, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scene intelligence version was not found")
    return version


def editable(version: SceneIntelligenceVersion) -> None:
    if version.state not in {IntelligenceVersionState.draft, IntelligenceVersionState.review}:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Validated or published versions are immutable"
        )


def source_for_version(db: DbSession, version_id: uuid.UUID, source_id: uuid.UUID) -> SceneSource:
    source = db.scalar(
        select(SceneSource).where(SceneSource.id == source_id, SceneSource.version_id == version_id)
    )
    if source is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Provenance source is not in this version"
        )
    return source


def source_label(db: DbSession, playback: PlaybackSource) -> str:
    if playback.movie_id:
        movie = db.get(Movie, playback.movie_id)
        return movie.title if movie else "Missing movie"
    episode = db.get(Episode, playback.episode_id)
    return episode.title if episode else "Missing episode"


def validation_errors(db: DbSession, version: SceneIntelligenceVersion) -> list[str]:
    errors: list[str] = []
    duration = version_duration(db, version)
    scenes = list(
        db.scalars(select(Scene).where(Scene.version_id == version.id).order_by(Scene.ordinal))
    )
    sources = {
        item.id
        for item in db.scalars(select(SceneSource).where(SceneSource.version_id == version.id))
    }
    if not sources:
        errors.append("At least one provenance source is required.")
    if not scenes:
        errors.append("At least one scene is required.")
    if [scene.ordinal for scene in scenes] != list(range(1, len(scenes) + 1)):
        errors.append("Scene ordinals must be contiguous from 1.")
    for index, scene in enumerate(scenes):
        if scene.source_id not in sources:
            errors.append(f"Scene {scene.ordinal} references foreign provenance.")
        if scene.end_seconds > duration:
            errors.append(f"Scene {scene.ordinal} exceeds the playback duration.")
        if index and scene.start_seconds < scenes[index - 1].end_seconds:
            errors.append(f"Scene {scene.ordinal} overlaps the previous scene.")
    chapters = list(
        db.scalars(
            select(Chapter).where(Chapter.version_id == version.id).order_by(Chapter.ordinal)
        )
    )
    if chapters and [chapter.ordinal for chapter in chapters] != list(range(1, len(chapters) + 1)):
        errors.append("Chapter ordinals must be contiguous from 1.")
    for index, chapter in enumerate(chapters):
        if chapter.source_id not in sources:
            errors.append(f"Chapter {chapter.ordinal} references foreign provenance.")
        if chapter.end_seconds > duration:
            errors.append(f"Chapter {chapter.ordinal} exceeds the playback duration.")
        if index and chapter.start_seconds < chapters[index - 1].end_seconds:
            errors.append(f"Chapter {chapter.ordinal} overlaps the previous chapter.")
    timed_models = (SceneCharacter, SceneEntity, SceneRelationship, ProductionNote)
    for model in timed_models:
        for record in db.scalars(
            select(model)
            .join(Scene, model.scene_id == Scene.id)
            .where(Scene.version_id == version.id)
        ):
            if record.reveal_seconds > duration:
                errors.append(f"{model.__name__} reveal exceeds playback duration.")
            if record.source_id not in sources:
                errors.append(f"{model.__name__} references foreign provenance.")
    for cue in db.scalars(
        select(MusicCue)
        .join(Scene, MusicCue.scene_id == Scene.id)
        .where(Scene.version_id == version.id)
    ):
        if cue.end_seconds > duration:
            errors.append("MusicCue exceeds playback duration.")
        if cue.source_id not in sources:
            errors.append("MusicCue references foreign provenance.")
    for boundary in db.scalars(
        select(SpoilerBoundary).where(SpoilerBoundary.version_id == version.id)
    ):
        if boundary.reveal_seconds > duration:
            errors.append("SpoilerBoundary exceeds playback duration.")
        if boundary.source_id not in sources:
            errors.append("SpoilerBoundary references foreign provenance.")
    for cue in db.scalars(select(TranscriptCue).where(TranscriptCue.version_id == version.id)):
        if cue.end_seconds > duration:
            errors.append("TranscriptCue exceeds playback duration.")
        if cue.source_id not in sources:
            errors.append("TranscriptCue references foreign provenance.")
    return list(dict.fromkeys(errors))


def version_duration(db: DbSession, version: SceneIntelligenceVersion) -> float:
    playback = db.get(PlaybackSource, version.playback_source_id)
    return float(playback.processing_job.duration_seconds or 0)


def audit(db: DbSession, admin: Admin, request: Request, action: str, detail: dict) -> None:
    db.add(
        AuditLog(
            actor_type="admin",
            actor_id=admin.id,
            action=action,
            outcome="succeeded",
            ip_address=request.client.host if request.client else None,
            detail=detail,
        )
    )


@router.get("", response_model=list[VersionDetail])
def list_versions(db: DbSession) -> list[VersionDetail]:
    return [
        detail(version.id, db)
        for version in db.scalars(
            select(SceneIntelligenceVersion).order_by(SceneIntelligenceVersion.created_at.desc())
        )
    ]


@router.get("/playback-sources")
def playback_sources(db: DbSession) -> list[dict]:
    records = list(db.scalars(select(PlaybackSource).order_by(PlaybackSource.created_at.desc())))
    return [
        {
            "id": item.id,
            "label": source_label(db, item),
            "duration_seconds": float(item.processing_job.duration_seconds or 0),
        }
        for item in records
    ]


@router.get("/search")
def search_scenes(db: DbSession, q: str = Query(min_length=2, max_length=100)) -> list[dict]:
    query = func.websearch_to_tsquery("simple", q)
    rows = db.execute(
        select(Scene, SceneIntelligenceVersion, SceneSearchDocument)
        .join(SceneSearchDocument, SceneSearchDocument.scene_id == Scene.id)
        .join(SceneIntelligenceVersion, SceneIntelligenceVersion.id == Scene.version_id)
        .where(SceneSearchDocument.search_vector.op("@@")(query))
        .order_by(func.ts_rank(SceneSearchDocument.search_vector, query).desc())
        .limit(50)
    ).all()
    return [
        {
            "scene": record_dict(scene),
            "version_id": version.id,
            "version_state": version.state,
            "playback_label": source_label(db, db.get(PlaybackSource, version.playback_source_id)),
        }
        for scene, version, _document in rows
    ]


@router.get("/{version_id}", response_model=VersionDetail)
def detail(version_id: uuid.UUID, db: DbSession) -> VersionDetail:
    version = version_or_404(db, version_id)
    playback = db.get(PlaybackSource, version.playback_source_id)
    manifest_prefix = (playback.processing_job.manifest_key or "").rsplit("/", 1)[0]
    scenes = list(
        db.scalars(select(Scene).where(Scene.version_id == version.id).order_by(Scene.ordinal))
    )
    scene_ids = [scene.id for scene in scenes]

    def scene_records(model):
        return (
            list(db.scalars(select(model).where(model.scene_id.in_(scene_ids))))
            if scene_ids
            else []
        )

    return VersionDetail(
        version=version,
        playback_label=source_label(db, playback),
        duration_seconds=version_duration(db, version),
        available_evidence=[
            {
                "kind": "subtitle",
                "label": f"Extracted subtitle track {index + 1}",
                "source_uri": f"storage://{manifest_prefix}/{track['key']}",
                "language": track.get("language"),
            }
            for index, track in enumerate(playback.processing_job.subtitle_tracks)
            if track.get("state") == "ready" and track.get("key")
        ],
        sources=list(db.scalars(select(SceneSource).where(SceneSource.version_id == version.id))),
        scenes=scenes,
        chapters=[
            record_dict(item)
            for item in db.scalars(
                select(Chapter).where(Chapter.version_id == version.id).order_by(Chapter.ordinal)
            )
        ],
        entities=[record_dict(item) for item in scene_records(SceneEntity)],
        characters=[record_dict(item) for item in scene_records(SceneCharacter)],
        relationships=[record_dict(item) for item in scene_records(SceneRelationship)],
        music_cues=[record_dict(item) for item in scene_records(MusicCue)],
        production_notes=[record_dict(item) for item in scene_records(ProductionNote)],
        spoiler_boundaries=[
            record_dict(item)
            for item in db.scalars(
                select(SpoilerBoundary).where(SpoilerBoundary.version_id == version.id)
            )
        ],
        transcript_cues=[
            record_dict(item)
            for item in db.scalars(
                select(TranscriptCue)
                .where(TranscriptCue.version_id == version.id)
                .order_by(TranscriptCue.start_seconds)
            )
        ],
        jobs=list(
            db.scalars(
                select(SceneIntelligenceJob)
                .where(SceneIntelligenceJob.version_id == version.id)
                .order_by(SceneIntelligenceJob.created_at.desc())
            )
        ),
        validation_errors=validation_errors(db, version),
    )


@router.post("", response_model=VersionResponse, status_code=status.HTTP_201_CREATED)
def create_version(payload: VersionCreate, request: Request, db: DbSession, admin: AdminIdentity):
    if db.get(PlaybackSource, payload.playback_source_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Playback source was not found")
    number = (
        db.scalar(
            select(func.max(SceneIntelligenceVersion.number)).where(
                SceneIntelligenceVersion.playback_source_id == payload.playback_source_id
            )
        )
        or 0
    ) + 1
    version = SceneIntelligenceVersion(
        **payload.model_dump(),
        number=number,
        state=IntelligenceVersionState.draft,
        created_by_admin_id=admin.id,
    )
    db.add(version)
    db.flush()
    audit(db, admin, request, "scene.version.created", {"version_id": str(version.id)})
    db.commit()
    return version


@router.post(
    "/{version_id}/sources", response_model=SourceResponse, status_code=status.HTTP_201_CREATED
)
def create_source(
    version_id: uuid.UUID,
    payload: SourceCreate,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
):
    version = version_or_404(db, version_id)
    editable(version)
    source = SceneSource(
        version_id=version.id, created_by_admin_id=admin.id, **payload.model_dump()
    )
    db.add(source)
    db.flush()
    audit(db, admin, request, "scene.source.created", {"source_id": str(source.id)})
    db.commit()
    return source


@router.post(
    "/{version_id}/scenes", response_model=SceneResponse, status_code=status.HTTP_201_CREATED
)
def create_scene(
    version_id: uuid.UUID,
    payload: SceneCreate,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
):
    version = version_or_404(db, version_id)
    editable(version)
    source_for_version(db, version.id, payload.source_id)
    if payload.end_seconds > version_duration(db, version):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Scene exceeds playback duration"
        )
    scene = Scene(version_id=version.id, **payload.model_dump())
    db.add(scene)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Scene ordinal already exists") from exc
    audit(db, admin, request, "scene.created", {"scene_id": str(scene.id)})
    db.commit()
    return scene


@router.patch("/{version_id}/scenes/{scene_id}", response_model=SceneResponse)
def update_scene(
    version_id: uuid.UUID,
    scene_id: uuid.UUID,
    payload: SceneUpdate,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
):
    version = version_or_404(db, version_id)
    editable(version)
    scene = db.scalar(select(Scene).where(Scene.id == scene_id, Scene.version_id == version.id))
    if scene is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scene was not found")
    values = payload.model_dump(exclude_unset=True)
    if "source_id" in values:
        source_for_version(db, version.id, values["source_id"])
    for key, value in values.items():
        setattr(scene, key, value)
    if scene.end_seconds <= scene.start_seconds or scene.end_seconds > version_duration(
        db, version
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Scene time range is invalid")
    audit(db, admin, request, "scene.updated", {"scene_id": str(scene.id)})
    db.commit()
    return scene


@router.delete("/{version_id}/scenes/{scene_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scene(version_id: uuid.UUID, scene_id: uuid.UUID, response: Response, db: DbSession):
    version = version_or_404(db, version_id)
    editable(version)
    scene = db.scalar(select(Scene).where(Scene.id == scene_id, Scene.version_id == version.id))
    if scene is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scene was not found")
    db.delete(scene)
    db.commit()


@router.post("/{version_id}/chapters", status_code=status.HTTP_201_CREATED)
def create_chapter(version_id: uuid.UUID, payload: ChapterCreate, db: DbSession):
    version = version_or_404(db, version_id)
    editable(version)
    source_for_version(db, version.id, payload.source_id)
    chapter = Chapter(version_id=version.id, **payload.model_dump())
    db.add(chapter)
    db.commit()
    db.refresh(chapter)
    return record_dict(chapter)


@router.post("/{version_id}/scenes/{scene_id}/entities", status_code=status.HTTP_201_CREATED)
def create_entity(version_id: uuid.UUID, scene_id: uuid.UUID, payload: EntityCreate, db: DbSession):
    scene = owned_scene(db, version_id, scene_id)
    source_for_version(db, version_id, payload.source_id)
    entity = SceneEntity(scene_id=scene.id, **payload.model_dump())
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return record_dict(entity)


def owned_scene(db: DbSession, version_id: uuid.UUID, scene_id: uuid.UUID) -> Scene:
    version = version_or_404(db, version_id)
    editable(version)
    scene = db.scalar(select(Scene).where(Scene.id == scene_id, Scene.version_id == version.id))
    if scene is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scene was not found")
    return scene


@router.post("/{version_id}/scenes/{scene_id}/characters", status_code=status.HTTP_201_CREATED)
def create_character(
    version_id: uuid.UUID, scene_id: uuid.UUID, payload: CharacterCreate, db: DbSession
):
    scene = owned_scene(db, version_id, scene_id)
    source_for_version(db, version_id, payload.source_id)
    if db.get(Character, payload.character_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Character was not found")
    record = SceneCharacter(scene_id=scene.id, **payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record_dict(record)


@router.post("/{version_id}/scenes/{scene_id}/relationships", status_code=status.HTTP_201_CREATED)
def create_relationship(
    version_id: uuid.UUID, scene_id: uuid.UUID, payload: RelationshipCreate, db: DbSession
):
    scene = owned_scene(db, version_id, scene_id)
    source_for_version(db, version_id, payload.source_id)
    entities = set(
        db.scalars(
            select(SceneEntity.id).where(
                SceneEntity.scene_id == scene.id,
                SceneEntity.id.in_([payload.subject_entity_id, payload.object_entity_id]),
            )
        )
    )
    if entities != {payload.subject_entity_id, payload.object_entity_id}:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Relationship entities must belong to this scene"
        )
    record = SceneRelationship(scene_id=scene.id, **payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record_dict(record)


@router.post("/{version_id}/scenes/{scene_id}/music-cues", status_code=status.HTTP_201_CREATED)
def create_music_cue(
    version_id: uuid.UUID, scene_id: uuid.UUID, payload: MusicCueCreate, db: DbSession
):
    scene = owned_scene(db, version_id, scene_id)
    source_for_version(db, version_id, payload.source_id)
    record = MusicCue(scene_id=scene.id, **payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record_dict(record)


@router.post(
    "/{version_id}/scenes/{scene_id}/production-notes", status_code=status.HTTP_201_CREATED
)
def create_production_note(
    version_id: uuid.UUID, scene_id: uuid.UUID, payload: ProductionNoteCreate, db: DbSession
):
    scene = owned_scene(db, version_id, scene_id)
    source_for_version(db, version_id, payload.source_id)
    record = ProductionNote(scene_id=scene.id, **payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record_dict(record)


@router.post("/{version_id}/spoiler-boundaries", status_code=status.HTTP_201_CREATED)
def create_boundary(version_id: uuid.UUID, payload: SpoilerBoundaryCreate, db: DbSession):
    version = version_or_404(db, version_id)
    editable(version)
    source_for_version(db, version.id, payload.source_id)
    record = SpoilerBoundary(version_id=version.id, **payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record_dict(record)


@router.post("/{version_id}/jobs", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def queue_job(version_id: uuid.UUID, request: Request, db: DbSession, admin: AdminIdentity):
    version = version_or_404(db, version_id)
    editable(version)
    active = db.scalar(
        select(SceneIntelligenceJob).where(
            SceneIntelligenceJob.version_id == version.id,
            SceneIntelligenceJob.state.in_([EnrichmentJobState.queued, EnrichmentJobState.running]),
        )
    )
    if active:
        raise HTTPException(status.HTTP_409_CONFLICT, "An enrichment job is already active")
    job = SceneIntelligenceJob(
        version_id=version.id,
        state=EnrichmentJobState.queued,
        stage="queued",
        progress_percent=0,
        attempts=0,
        created_by_admin_id=admin.id,
    )
    db.add(job)
    db.flush()
    audit(db, admin, request, "scene.job.queued", {"job_id": str(job.id)})
    db.commit()
    enqueue_scene_job(str(job.id))
    return job


@router.post("/{version_id}/validate", response_model=VersionResponse)
def validate_version(version_id: uuid.UUID, request: Request, db: DbSession, admin: AdminIdentity):
    version = version_or_404(db, version_id)
    editable(version)
    errors = validation_errors(db, version)
    if errors:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"message": "Scene version failed validation", "errors": errors},
        )
    version.state = IntelligenceVersionState.validated
    version.validated_by_admin_id = admin.id
    version.validated_at = datetime.now(UTC)
    audit(db, admin, request, "scene.version.validated", {"version_id": str(version.id)})
    db.commit()
    return version


@router.post("/{version_id}/publish", response_model=VersionResponse)
def publish_version(version_id: uuid.UUID, request: Request, db: DbSession, admin: AdminIdentity):
    version = version_or_404(db, version_id)
    if version.state is not IntelligenceVersionState.validated:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only validated versions can be published")
    for other in db.scalars(
        select(SceneIntelligenceVersion).where(
            SceneIntelligenceVersion.playback_source_id == version.playback_source_id,
            SceneIntelligenceVersion.state == IntelligenceVersionState.published,
        )
    ):
        other.state = IntelligenceVersionState.validated
        other.published_at = None
    version.state = IntelligenceVersionState.published
    version.published_at = datetime.now(UTC)
    audit(db, admin, request, "scene.version.published", {"version_id": str(version.id)})
    db.commit()
    return version
