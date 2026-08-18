import mimetypes
import uuid
from typing import Annotated

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.after_credits_schemas import AfterCreditsResponse
from app.after_credits_service import after_credits_room
from app.auth import DbSession, require_customer_session, require_trusted_origin
from app.catalog_models import Artwork
from app.cinephile_schemas import CinephileToolkitResponse
from app.cinephile_service import cinephile_toolkit
from app.config import get_settings
from app.geo import OptionalViewerCountry
from app.models import DeviceSession
from app.object_storage import s3_client
from app.routes.playback import active_profile_id, playable_source

router = APIRouter(
    prefix="/cinephile",
    tags=["cinephile toolkit"],
    dependencies=[Depends(require_trusted_origin), Depends(require_customer_session)],
)
ViewerSession = Annotated[DeviceSession, Depends(require_customer_session)]


@router.get("/sources/{source_id}", response_model=CinephileToolkitResponse)
def toolkit(
    source_id: uuid.UUID,
    db: DbSession,
    session: ViewerSession,
    country: OptionalViewerCountry,
    timestamp: float = Query(ge=0),
) -> CinephileToolkitResponse:
    return cinephile_toolkit(
        db,
        playback_source=playable_source(db, source_id, country),
        profile_id=active_profile_id(session),
        timestamp=timestamp,
    )


@router.get("/sources/{source_id}/after-credits", response_model=AfterCreditsResponse)
def after_credits(
    source_id: uuid.UUID,
    db: DbSession,
    session: ViewerSession,
    country: OptionalViewerCountry,
) -> AfterCreditsResponse:
    return after_credits_room(
        db,
        playable_source(db, source_id, country),
        active_profile_id(session),
        country,
    )


@router.get("/sources/{source_id}/stills/{artwork_id}")
def still(
    source_id: uuid.UUID,
    artwork_id: uuid.UUID,
    db: DbSession,
    session: ViewerSession,
    country: OptionalViewerCountry,
    timestamp: float = Query(ge=0),
) -> StreamingResponse:
    source = playable_source(db, source_id, country)
    context = cinephile_toolkit(
        db,
        playback_source=source,
        profile_id=active_profile_id(session),
        timestamp=timestamp,
    )
    if not any(item.id == artwork_id for item in context.stills):
        raise HTTPException(404, "Permitted still was not found")
    artwork = db.get(Artwork, artwork_id)
    if artwork is None:
        raise HTTPException(404, "Permitted still was not found")
    try:
        response = s3_client().get_object(Bucket=get_settings().s3_bucket, Key=artwork.storage_key)
    except ClientError as exc:
        raise HTTPException(404, "Permitted still was not found") from exc
    return StreamingResponse(
        response["Body"].iter_chunks(chunk_size=256 * 1024),
        media_type=mimetypes.guess_type(artwork.storage_key)[0] or "application/octet-stream",
        headers={"Cache-Control": "private, max-age=30", "X-Content-Type-Options": "nosniff"},
    )
