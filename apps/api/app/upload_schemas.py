import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import AssetState


class UploadInitialize(BaseModel):
    original_filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=100)
    size_bytes: int = Field(gt=0)
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("original_filename")
    @classmethod
    def filename_must_be_leaf(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned or "/" in cleaned or "\\" in cleaned or cleaned in {".", ".."}:
            raise ValueError("Filename must not contain a path")
        return cleaned


class MediaAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    media_type: str
    size_bytes: int
    checksum_sha256: str
    storage_key: str
    state: AssetState
    etag: str | None
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    upload_strategy: str
    multipart_part_size: int | None
    malware_scan_status: str
    malware_scan_engine: str | None
    malware_scan_signature: str | None
    malware_scanned_at: datetime | None


class UploadTicket(BaseModel):
    asset: MediaAssetResponse
    upload_url: str
    method: str = "PUT"
    headers: dict[str, str]
    expires_in_seconds: int


class UploadFailure(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class MultipartTicket(BaseModel):
    asset: MediaAssetResponse
    part_size: int
    total_parts: int
    expires_in_seconds: int


class MultipartPartTicket(BaseModel):
    part_number: int
    upload_url: str
    method: str = "PUT"
    expires_in_seconds: int


class MultipartStatus(BaseModel):
    asset: MediaAssetResponse
    uploaded_parts: list[int]
    uploaded_bytes: int
    total_parts: int
