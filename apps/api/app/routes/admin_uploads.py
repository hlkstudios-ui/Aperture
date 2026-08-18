import hashlib
import math
import uuid
from datetime import UTC, datetime
from typing import Annotated

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from app.auth import DbSession, require_admin, require_trusted_origin
from app.config import get_settings
from app.malware_scanner import ScannerUnavailable, scan_asset
from app.models import Admin, AssetState, AuditLog, MediaAsset
from app.object_storage import create_upload_url, s3_client
from app.upload_schemas import (
    MediaAssetResponse,
    MultipartPartTicket,
    MultipartStatus,
    MultipartTicket,
    UploadFailure,
    UploadInitialize,
    UploadTicket,
)

router = APIRouter(
    prefix="/admin/uploads",
    tags=["administrator uploads"],
    dependencies=[Depends(require_trusted_origin), Depends(require_admin)],
)
AdminIdentity = Annotated[Admin, Depends(require_admin)]
ALLOWED_MEDIA_TYPES = {"video/mp4", "video/webm", "video/quicktime"}
MULTIPART_PART_SIZE = 16 * 1024 * 1024
MAX_MULTIPART_PARTS = 10_000


def validate_object(asset: MediaAsset) -> tuple[str | None, str | None]:
    response = s3_client().get_object(Bucket=get_settings().s3_bucket, Key=asset.storage_key)
    digest = hashlib.sha256()
    prefix = b""
    try:
        for chunk in response["Body"].iter_chunks(chunk_size=4 * 1024 * 1024):
            if not prefix:
                prefix = chunk[:32]
            digest.update(chunk)
    finally:
        response["Body"].close()
    if digest.hexdigest() != asset.checksum_sha256:
        return None, "Stored object SHA-256 did not match the declared checksum"
    valid_signature = (
        asset.media_type in {"video/mp4", "video/quicktime"} and prefix[4:8] == b"ftyp"
    ) or (asset.media_type == "video/webm" and prefix.startswith(b"\x1aE\xdf\xa3"))
    if not valid_signature:
        return None, "File signature does not match the declared video media type"
    return digest.hexdigest(), None


def audit(db: DbSession, request: Request, admin: Admin, action: str, asset: MediaAsset) -> None:
    db.add(
        AuditLog(
            actor_type="admin",
            actor_id=admin.id,
            action=action,
            outcome="succeeded",
            ip_address=request.client.host if request.client else None,
            detail={"asset_id": str(asset.id), "state": asset.state.value},
        )
    )


def get_asset(db: DbSession, asset_id: uuid.UUID) -> MediaAsset:
    asset = db.get(MediaAsset, asset_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media asset not found")
    return asset


def ticket(asset: MediaAsset) -> UploadTicket:
    settings = get_settings()
    return UploadTicket(
        asset=asset,
        upload_url=create_upload_url(asset.storage_key, asset.media_type, asset.checksum_sha256),
        headers={"Content-Type": asset.media_type, "x-amz-meta-sha256": asset.checksum_sha256},
        expires_in_seconds=settings.upload_url_ttl_seconds,
    )


def list_multipart_parts(asset: MediaAsset) -> list[dict]:
    client = s3_client()
    parts: list[dict] = []
    marker = 0
    while True:
        page = client.list_parts(
            Bucket=get_settings().s3_bucket,
            Key=asset.storage_key,
            UploadId=asset.multipart_upload_id,
            PartNumberMarker=marker,
        )
        parts.extend(page.get("Parts", []))
        if not page.get("IsTruncated"):
            return parts
        marker = page["NextPartNumberMarker"]


@router.get("", response_model=list[MediaAssetResponse])
def list_uploads(db: DbSession) -> list[MediaAsset]:
    return list(db.scalars(select(MediaAsset).order_by(MediaAsset.created_at.desc())))


@router.post("/initialize", response_model=UploadTicket, status_code=status.HTTP_201_CREATED)
def initialize_upload(
    payload: UploadInitialize, request: Request, db: DbSession, admin: AdminIdentity
) -> UploadTicket:
    settings = get_settings()
    if payload.media_type not in ALLOWED_MEDIA_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unsupported video media type")
    if payload.size_bytes > settings.upload_max_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "File exceeds upload size limit")
    asset_id = uuid.uuid4()
    suffix = {"video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov"}[
        payload.media_type
    ]
    asset = MediaAsset(
        id=asset_id,
        created_by_admin_id=admin.id,
        original_filename=payload.original_filename,
        media_type=payload.media_type,
        size_bytes=payload.size_bytes,
        checksum_sha256=payload.checksum_sha256,
        storage_key=f"source/{asset_id}/{asset_id}{suffix}",
        state=AssetState.uploading,
    )
    db.add(asset)
    audit(db, request, admin, "upload.initialized", asset)
    db.commit()
    return ticket(asset)


@router.post("/initialize-multipart", response_model=MultipartTicket, status_code=201)
def initialize_multipart_upload(
    payload: UploadInitialize, request: Request, db: DbSession, admin: AdminIdentity
) -> MultipartTicket:
    settings = get_settings()
    if payload.media_type not in ALLOWED_MEDIA_TYPES:
        raise HTTPException(422, "Unsupported video media type")
    if payload.size_bytes > settings.upload_max_bytes:
        raise HTTPException(413, "File exceeds upload size limit")
    total_parts = math.ceil(payload.size_bytes / MULTIPART_PART_SIZE)
    if total_parts > MAX_MULTIPART_PARTS:
        raise HTTPException(413, "File requires too many multipart chunks")
    asset_id = uuid.uuid4()
    suffix = {"video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov"}[
        payload.media_type
    ]
    key = f"source/{asset_id}/{asset_id}{suffix}"
    created = s3_client().create_multipart_upload(
        Bucket=settings.s3_bucket,
        Key=key,
        ContentType=payload.media_type,
        Metadata={"sha256": payload.checksum_sha256},
    )
    asset = MediaAsset(
        id=asset_id,
        created_by_admin_id=admin.id,
        original_filename=payload.original_filename,
        media_type=payload.media_type,
        size_bytes=payload.size_bytes,
        checksum_sha256=payload.checksum_sha256,
        storage_key=key,
        state=AssetState.uploading,
        upload_strategy="multipart",
        multipart_upload_id=created["UploadId"],
        multipart_part_size=MULTIPART_PART_SIZE,
    )
    db.add(asset)
    audit(db, request, admin, "upload.multipart_initialized", asset)
    db.commit()
    return MultipartTicket(
        asset=asset,
        part_size=MULTIPART_PART_SIZE,
        total_parts=total_parts,
        expires_in_seconds=settings.upload_url_ttl_seconds,
    )


@router.post("/{asset_id}/multipart/parts/{part_number}", response_model=MultipartPartTicket)
def sign_multipart_part(
    asset_id: uuid.UUID, part_number: int, db: DbSession
) -> MultipartPartTicket:
    asset = get_asset(db, asset_id)
    total_parts = math.ceil(asset.size_bytes / (asset.multipart_part_size or 1))
    if asset.state is not AssetState.uploading or asset.upload_strategy != "multipart":
        raise HTTPException(409, "Multipart upload is not active")
    if not 1 <= part_number <= total_parts:
        raise HTTPException(422, "Part number is outside the upload range")
    settings = get_settings()
    url = s3_client(public=True).generate_presigned_url(
        "upload_part",
        Params={
            "Bucket": settings.s3_bucket,
            "Key": asset.storage_key,
            "UploadId": asset.multipart_upload_id,
            "PartNumber": part_number,
        },
        ExpiresIn=settings.upload_url_ttl_seconds,
    )
    return MultipartPartTicket(
        part_number=part_number, upload_url=url, expires_in_seconds=settings.upload_url_ttl_seconds
    )


@router.get("/{asset_id}/multipart", response_model=MultipartStatus)
def multipart_status(asset_id: uuid.UUID, db: DbSession) -> MultipartStatus:
    asset = get_asset(db, asset_id)
    if asset.upload_strategy != "multipart" or not asset.multipart_upload_id:
        raise HTTPException(409, "Asset is not a multipart upload")
    parts = list_multipart_parts(asset)
    return MultipartStatus(
        asset=asset,
        uploaded_parts=[part["PartNumber"] for part in parts],
        uploaded_bytes=sum(part["Size"] for part in parts),
        total_parts=math.ceil(asset.size_bytes / (asset.multipart_part_size or 1)),
    )


@router.post("/{asset_id}/multipart/complete", response_model=MediaAssetResponse)
def complete_multipart_upload(
    asset_id: uuid.UUID, request: Request, db: DbSession, admin: AdminIdentity
) -> MediaAsset:
    asset = get_asset(db, asset_id)
    if asset.state is AssetState.completed and asset.upload_strategy == "multipart":
        return asset
    if asset.malware_scan_status in {"scanning", "error"}:
        return complete_upload(asset_id, request, db, admin)
    if asset.state is not AssetState.uploading or asset.upload_strategy != "multipart":
        raise HTTPException(409, "Multipart upload is not active")
    parts = list_multipart_parts(asset)
    expected = math.ceil(asset.size_bytes / (asset.multipart_part_size or 1))
    if [part["PartNumber"] for part in parts] != list(range(1, expected + 1)):
        raise HTTPException(409, "Multipart upload is incomplete")
    s3_client().complete_multipart_upload(
        Bucket=get_settings().s3_bucket,
        Key=asset.storage_key,
        UploadId=asset.multipart_upload_id,
        MultipartUpload={
            "Parts": [
                {"PartNumber": part["PartNumber"], "ETag": part["ETag"]} for part in parts
            ]
        },
    )
    return complete_upload(asset_id, request, db, admin)


@router.post("/{asset_id}/complete", response_model=MediaAssetResponse)
def complete_upload(
    asset_id: uuid.UUID, request: Request, db: DbSession, admin: AdminIdentity
) -> MediaAsset:
    asset = get_asset(db, asset_id)
    if asset.state is AssetState.completed and asset.malware_scan_status == "clean":
        return asset
    if asset.malware_scan_status in {"scanning", "error"}:
        return finalize_malware_scan(asset, request, db, admin)
    if asset.state is not AssetState.uploading:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only an active upload can be completed")
    try:
        head = s3_client().head_object(Bucket=get_settings().s3_bucket, Key=asset.storage_key)
    except ClientError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Uploaded object was not found") from exc
    if head["ContentLength"] != asset.size_bytes:
        asset.state = AssetState.failed
        asset.failure_reason = "Object size did not match initialization metadata"
        audit(db, request, admin, "upload.integrity_failed", asset)
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, asset.failure_reason)
    if head.get("Metadata", {}).get("sha256") != asset.checksum_sha256:
        asset.state = AssetState.failed
        asset.failure_reason = "Object checksum metadata did not match initialization metadata"
        audit(db, request, admin, "upload.integrity_failed", asset)
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, asset.failure_reason)
    _, integrity_error = validate_object(asset)
    if integrity_error:
        asset.state = AssetState.failed
        asset.failure_reason = integrity_error
        audit(db, request, admin, "upload.integrity_failed", asset)
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, asset.failure_reason)
    asset.etag = str(head.get("ETag", "")).strip('"') or None
    asset.failure_reason = None
    asset.malware_scan_status = "scanning"
    audit(db, request, admin, "upload.malware_scan_started", asset)
    db.commit()
    return finalize_malware_scan(asset, request, db, admin)


def finalize_malware_scan(
    asset: MediaAsset, request: Request, db: DbSession, admin: Admin
) -> MediaAsset:
    try:
        result = scan_asset(asset)
    except ScannerUnavailable as error:
        asset.malware_scan_status = "error"
        asset.failure_reason = "Malware scan is temporarily unavailable; asset is quarantined"
        audit(db, request, admin, "upload.malware_scan_unavailable", asset)
        db.commit()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, asset.failure_reason) from error
    asset.malware_scan_engine = result.engine
    asset.malware_scan_signature = result.signature
    asset.malware_scanned_at = datetime.now(UTC)
    if not result.clean:
        asset.malware_scan_status = "infected"
        asset.state = AssetState.failed
        asset.failure_reason = "Malware scan rejected the uploaded object"
        audit(db, request, admin, "upload.malware_detected", asset)
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, asset.failure_reason)
    asset.malware_scan_status = "clean"
    asset.state = AssetState.completed
    asset.failure_reason = None
    asset.completed_at = datetime.now(UTC)
    audit(db, request, admin, "upload.completed", asset)
    db.commit()
    return asset


@router.post("/{asset_id}/retry", response_model=UploadTicket)
def retry_upload(
    asset_id: uuid.UUID, request: Request, db: DbSession, admin: AdminIdentity
) -> UploadTicket:
    asset = get_asset(db, asset_id)
    if asset.state not in {AssetState.failed, AssetState.cancelled, AssetState.uploading}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Completed uploads cannot be retried")
    if asset.upload_strategy == "multipart":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Resume multipart uploads through part status"
        )
    asset.state = AssetState.uploading
    asset.failure_reason = None
    asset.malware_scan_status = "pending"
    asset.malware_scan_engine = None
    asset.malware_scan_signature = None
    asset.malware_scanned_at = None
    audit(db, request, admin, "upload.retried", asset)
    db.commit()
    return ticket(asset)


@router.post("/{asset_id}/fail", response_model=MediaAssetResponse)
def fail_upload(
    asset_id: uuid.UUID,
    payload: UploadFailure,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
) -> MediaAsset:
    asset = get_asset(db, asset_id)
    if asset.state is AssetState.completed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Completed uploads cannot be failed")
    asset.state = AssetState.failed
    asset.failure_reason = payload.reason
    audit(db, request, admin, "upload.failed", asset)
    db.commit()
    return asset


@router.delete("/{asset_id}", response_model=MediaAssetResponse)
def cancel_upload(
    asset_id: uuid.UUID, request: Request, db: DbSession, admin: AdminIdentity
) -> MediaAsset:
    asset = get_asset(db, asset_id)
    if asset.state is AssetState.completed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Completed uploads cannot be cancelled")
    client = s3_client()
    if asset.upload_strategy == "multipart" and asset.multipart_upload_id:
        try:
            client.abort_multipart_upload(
                Bucket=get_settings().s3_bucket,
                Key=asset.storage_key,
                UploadId=asset.multipart_upload_id,
            )
        except ClientError:
            pass
    client.delete_object(Bucket=get_settings().s3_bucket, Key=asset.storage_key)
    asset.state = AssetState.cancelled
    asset.failure_reason = "Cancelled by administrator"
    audit(db, request, admin, "upload.cancelled", asset)
    db.commit()
    return asset
