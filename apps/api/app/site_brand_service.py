import hashlib
import json
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO

from fastapi import HTTPException, status
from PIL import Image, ImageFile
from pydantic import ValidationError
from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Admin, SiteBrandAsset, SiteBrandConfiguration
from app.site_brand_schemas import (
    SiteBrandAdminConfig,
    SiteBrandAdminResponse,
    SiteBrandEditableConfig,
    SiteBrandPatchRequest,
    SiteBrandPublicResponse,
)

MAX_LOGO_BYTES = 2 * 1024 * 1024
MIN_LOGO_DIMENSION = 64
MAX_LOGO_DIMENSION = 4096
MAX_LOGO_PIXELS = MAX_LOGO_DIMENSION * MAX_LOGO_DIMENSION
ALLOWED_LOGO_TYPES = {"image/jpeg", "image/png", "image/webp"}
LOGO_FORMATS = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
SITE_BRAND_SNAPSHOT_VERSION = 1

# Never honor a process-level opt-in that permits partial image decoding.
ImageFile.LOAD_TRUNCATED_IMAGES = False


@dataclass(frozen=True)
class ValidatedImage:
    content_type: str
    content: bytes
    sha256: str
    width: int
    height: int


def default_config() -> SiteBrandEditableConfig:
    return SiteBrandEditableConfig()


def _snapshot_payload(config: SiteBrandEditableConfig) -> dict[str, object]:
    return {
        "schema_version": SITE_BRAND_SNAPSHOT_VERSION,
        **config.model_dump(mode="json"),
    }


def _parse_snapshot(payload: object) -> SiteBrandEditableConfig:
    if not isinstance(payload, dict):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Stored brand configuration is unavailable",
        )
    # Rows created before snapshot versioning are the original v1 shape.
    version = payload.get("schema_version", SITE_BRAND_SNAPSHOT_VERSION)
    if version != SITE_BRAND_SNAPSHOT_VERSION:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Stored brand configuration version is not supported",
        )
    raw_config = {key: value for key, value in payload.items() if key != "schema_version"}
    try:
        return SiteBrandEditableConfig.model_validate(raw_config)
    except ValidationError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Stored brand configuration is invalid",
        ) from error


def _owner_forbidden() -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, "Only the site owner can manage brand setup")


def get_or_claim_configuration(
    db: Session, admin: Admin
) -> tuple[SiteBrandConfiguration, bool]:
    configuration = db.get(SiteBrandConfiguration, 1)
    if configuration is not None:
        if configuration.owner_admin_id != admin.id:
            raise _owner_forbidden()
        return configuration, False

    # Freeze administrator membership while checking the sole-owner invariant. PostgreSQL
    # INSERT/UPDATE operations take ROW EXCLUSIVE and therefore wait for this transaction.
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("LOCK TABLE admins IN SHARE MODE"))
    active_admin_count = db.scalar(
        select(func.count(Admin.id)).where(Admin.is_active.is_(True))
    )
    if not admin.is_active or active_admin_count != 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Brand ownership requires exactly one active provisioned administrator",
        )

    configuration = SiteBrandConfiguration(
        id=1,
        owner_admin_id=admin.id,
        draft_config=_snapshot_payload(default_config()),
        revision=0,
        current_step=1,
        completed_steps=[],
    )
    db.add(configuration)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        configuration = db.get(SiteBrandConfiguration, 1)
        if configuration is None or configuration.owner_admin_id != admin.id:
            raise _owner_forbidden() from None
        return configuration, False
    return configuration, True


def _admin_logo_url(asset: SiteBrandAsset | None) -> str | None:
    return f"/admin/site/brand/logo?revision={asset.revision}" if asset else None


def _public_logo_url(asset: SiteBrandAsset | None) -> str | None:
    return f"/site/brand/logo?revision={asset.revision}" if asset else None


def admin_response(db: Session, configuration: SiteBrandConfiguration) -> SiteBrandAdminResponse:
    editable = _parse_snapshot(configuration.draft_config)
    logo = (
        db.get(SiteBrandAsset, configuration.draft_logo_asset_id)
        if configuration.draft_logo_asset_id
        else None
    )
    config = SiteBrandAdminConfig(
        **editable.model_dump(),
        logo_url=_admin_logo_url(logo),
        logo_revision=logo.revision if logo else 0,
    )
    return SiteBrandAdminResponse(
        revision=configuration.revision,
        status=(
            "published"
            if configuration.published_revision == configuration.revision
            and configuration.published_snapshot is not None
            else "draft"
        ),
        current_step=configuration.current_step,
        completed_steps=configuration.completed_steps,
        config=config,
        updated_at=configuration.updated_at,
        published_at=configuration.published_at,
    )


def public_response(db: Session) -> SiteBrandPublicResponse:
    configuration = db.get(SiteBrandConfiguration, 1)
    if configuration is None or configuration.published_snapshot is None:
        editable = default_config()
        return SiteBrandPublicResponse(
            revision=0,
            **editable.model_dump(),
            logo_url=None,
            logo_revision=0,
            published_at=None,
        )

    editable = _parse_snapshot(configuration.published_snapshot)
    logo = (
        db.get(SiteBrandAsset, configuration.published_logo_asset_id)
        if configuration.published_logo_asset_id
        else None
    )
    return SiteBrandPublicResponse(
        revision=configuration.published_revision or 0,
        **editable.model_dump(),
        logo_url=_public_logo_url(logo),
        logo_revision=logo.revision if logo else 0,
        published_at=configuration.published_at,
    )


def response_etag(payload: SiteBrandPublicResponse) -> str:
    encoded = json.dumps(
        payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    return f'"{hashlib.sha256(encoded).hexdigest()}"'


def _merge_patch(
    current: SiteBrandEditableConfig, payload: SiteBrandPatchRequest
) -> SiteBrandEditableConfig:
    merged = current.model_dump(mode="json")
    if payload.config is None:
        return current
    patch = payload.config.model_dump(mode="json", exclude_unset=True)
    for nested in ("palette", "locale"):
        nested_patch = patch.pop(nested, None)
        if nested_patch is not None:
            merged[nested].update(nested_patch)
    merged.update(patch)
    try:
        return SiteBrandEditableConfig.model_validate(merged)
    except ValidationError as error:
        messages = [item["msg"] for item in error.errors(include_url=False)]
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"message": "Brand configuration is invalid", "errors": messages},
        ) from error


def patch_configuration(
    db: Session,
    configuration: SiteBrandConfiguration,
    payload: SiteBrandPatchRequest,
) -> tuple[SiteBrandConfiguration, list[str]]:
    if configuration.revision != payload.revision:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Brand setup changed; reload revision {configuration.revision}",
        )
    current = _parse_snapshot(configuration.draft_config)
    merged = _merge_patch(current, payload)
    generated_mark_selected = (
        payload.config is not None
        and "logo_mark" in payload.config.model_fields_set
        and payload.config.logo_mark is not None
    )
    old_draft_logo_id = configuration.draft_logo_asset_id
    clears_draft_logo = generated_mark_selected and old_draft_logo_id is not None
    next_step = payload.current_step or configuration.current_step
    next_completed = (
        payload.completed_steps
        if payload.completed_steps is not None
        else configuration.completed_steps
    )
    changed_fields: list[str] = []
    if merged != current:
        changed_fields.extend(payload.config.model_fields_set if payload.config else [])
    if clears_draft_logo and "logo_mark" not in changed_fields:
        changed_fields.append("logo_mark")
    if next_step != configuration.current_step:
        changed_fields.append("current_step")
    if next_completed != configuration.completed_steps:
        changed_fields.append("completed_steps")
    if not changed_fields:
        return configuration, []

    update_values: dict[str, object] = {
        "draft_config": _snapshot_payload(merged),
        "current_step": next_step,
        "completed_steps": next_completed,
        "revision": payload.revision + 1,
        "updated_at": datetime.now(UTC),
    }
    if generated_mark_selected:
        # Selecting a generated mark and retiring an uploaded draft are one
        # optimistic-lock write. The published asset remains live until publish.
        update_values["draft_logo_asset_id"] = None

    result = db.execute(
        update(SiteBrandConfiguration)
        .where(
            SiteBrandConfiguration.id == configuration.id,
            SiteBrandConfiguration.owner_admin_id == configuration.owner_admin_id,
            SiteBrandConfiguration.revision == payload.revision,
        )
        .values(**update_values)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Brand setup changed; reload and try again")
    if clears_draft_logo:
        is_still_referenced = db.scalar(
            select(func.count(SiteBrandConfiguration.id)).where(
                or_(
                    SiteBrandConfiguration.draft_logo_asset_id == old_draft_logo_id,
                    SiteBrandConfiguration.published_logo_asset_id == old_draft_logo_id,
                )
            )
        )
        if not is_still_referenced:
            db.execute(delete(SiteBrandAsset).where(SiteBrandAsset.id == old_draft_logo_id))
    db.flush()
    db.expire_all()
    return db.get_one(SiteBrandConfiguration, configuration.id), sorted(set(changed_fields))


def publish_configuration(
    db: Session, configuration: SiteBrandConfiguration, expected_revision: int
) -> SiteBrandConfiguration:
    if configuration.revision != expected_revision:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Brand setup changed; reload revision {configuration.revision}",
        )
    if configuration.completed_steps != [1, 2, 3, 4, 5]:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Complete all five brand setup stages before publishing",
        )
    snapshot = _parse_snapshot(configuration.draft_config)
    now = datetime.now(UTC)
    old_published_logo_id = configuration.published_logo_asset_id
    result = db.execute(
        update(SiteBrandConfiguration)
        .where(
            SiteBrandConfiguration.id == configuration.id,
            SiteBrandConfiguration.owner_admin_id == configuration.owner_admin_id,
            SiteBrandConfiguration.revision == expected_revision,
        )
        .values(
            published_snapshot=_snapshot_payload(snapshot),
            revision=expected_revision + 1,
            published_revision=expected_revision + 1,
            published_logo_asset_id=configuration.draft_logo_asset_id,
            published_at=now,
            updated_at=now,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Brand setup changed; reload and try again")
    if (
        old_published_logo_id is not None
        and old_published_logo_id != configuration.draft_logo_asset_id
    ):
        db.execute(delete(SiteBrandAsset).where(SiteBrandAsset.id == old_published_logo_id))
    db.flush()
    db.expire_all()
    return db.get_one(SiteBrandConfiguration, configuration.id)


def validate_logo(content: bytes, supplied_content_type: str) -> ValidatedImage:
    content_type = supplied_content_type.split(";", maxsplit=1)[0].strip().lower()
    if content_type not in ALLOWED_LOGO_TYPES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Logo must be a PNG, JPEG, or WebP image",
        )
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Logo image is empty")
    if len(content) > MAX_LOGO_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Logo image exceeds 2 MiB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                if image.format != LOGO_FORMATS[content_type]:
                    raise ValueError("Image format does not match Content-Type")
                width, height = image.size
                if not (
                    MIN_LOGO_DIMENSION <= width <= MAX_LOGO_DIMENSION
                    and MIN_LOGO_DIMENSION <= height <= MAX_LOGO_DIMENSION
                ):
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_CONTENT,
                        "Logo dimensions must be between 64 and 4096 pixels",
                    )
                if width * height > MAX_LOGO_PIXELS:
                    raise ValueError("Image exceeds the decoded pixel limit")
                if max(width / height, height / width) > 16:
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_CONTENT,
                        "Logo aspect ratio cannot exceed 16:1",
                    )
                if getattr(image, "n_frames", 1) != 1:
                    raise ValueError("Animated or multi-frame logos are not supported")
                image.verify()
            # verify() checks container integrity but deliberately does not decode pixels.
            # Reopening and loading forces the complete raster through the maintained decoder.
            with Image.open(BytesIO(content)) as decoded:
                decoded.load()
                if decoded.size != (width, height):
                    raise ValueError("Decoded dimensions changed")
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        ValueError,
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Logo bytes do not contain a valid image matching Content-Type",
        ) from None
    return ValidatedImage(
        content_type=content_type,
        content=content,
        sha256=hashlib.sha256(content).hexdigest(),
        width=width,
        height=height,
    )


def put_logo(
    db: Session,
    configuration: SiteBrandConfiguration,
    expected_revision: int,
    image: ValidatedImage,
) -> tuple[SiteBrandConfiguration, bool]:
    if configuration.revision != expected_revision:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Brand setup changed; reload revision {configuration.revision}",
        )
    current = (
        db.get(SiteBrandAsset, configuration.draft_logo_asset_id)
        if configuration.draft_logo_asset_id
        else None
    )
    draft_config = _parse_snapshot(configuration.draft_config)
    if current is not None and current.sha256 == image.sha256 and draft_config.logo_mark is None:
        return configuration, False
    asset = db.scalar(select(SiteBrandAsset).where(SiteBrandAsset.sha256 == image.sha256))
    if asset is None:
        asset = SiteBrandAsset(
            content_type=image.content_type,
            content=image.content,
            sha256=image.sha256,
            byte_size=len(image.content),
            width=image.width,
            height=image.height,
            revision=expected_revision + 1,
        )
        db.add(asset)
        db.flush()
    result = db.execute(
        update(SiteBrandConfiguration)
        .where(
            SiteBrandConfiguration.id == configuration.id,
            SiteBrandConfiguration.owner_admin_id == configuration.owner_admin_id,
            SiteBrandConfiguration.revision == expected_revision,
        )
        .values(
            draft_config=_snapshot_payload(
                draft_config.model_copy(update={"logo_mark": None})
            ),
            draft_logo_asset_id=asset.id,
            revision=expected_revision + 1,
            updated_at=datetime.now(UTC),
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Brand setup changed; reload and try again")
    if (
        current is not None
        and current.id != asset.id
        and current.id != configuration.published_logo_asset_id
    ):
        db.execute(delete(SiteBrandAsset).where(SiteBrandAsset.id == current.id))
    db.flush()
    db.expire_all()
    return db.get_one(SiteBrandConfiguration, configuration.id), True


def delete_logo(
    db: Session, configuration: SiteBrandConfiguration, expected_revision: int
) -> tuple[SiteBrandConfiguration, bool]:
    if configuration.revision != expected_revision:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Brand setup changed; reload revision {configuration.revision}",
        )
    if configuration.draft_logo_asset_id is None:
        return configuration, False
    old_id = configuration.draft_logo_asset_id
    result = db.execute(
        update(SiteBrandConfiguration)
        .where(
            SiteBrandConfiguration.id == configuration.id,
            SiteBrandConfiguration.owner_admin_id == configuration.owner_admin_id,
            SiteBrandConfiguration.revision == expected_revision,
        )
        .values(
            draft_logo_asset_id=None,
            revision=expected_revision + 1,
            updated_at=datetime.now(UTC),
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Brand setup changed; reload and try again")
    if old_id != configuration.published_logo_asset_id:
        db.execute(delete(SiteBrandAsset).where(SiteBrandAsset.id == old_id))
    db.flush()
    db.expire_all()
    return db.get_one(SiteBrandConfiguration, configuration.id), True
