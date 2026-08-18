import boto3
from botocore.config import Config

from app.config import get_settings


def s3_client(*, public: bool = False):
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=str(
            settings.s3_public_endpoint
            if public and settings.s3_public_endpoint
            else settings.s3_endpoint
        ),
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=Config(s3={"addressing_style": "path"}, signature_version="s3v4"),
    )


def create_upload_url(storage_key: str, media_type: str, checksum: str) -> str:
    settings = get_settings()
    return s3_client(public=True).generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.s3_bucket,
            "Key": storage_key,
            "ContentType": media_type,
            "Metadata": {"sha256": checksum},
        },
        ExpiresIn=settings.upload_url_ttl_seconds,
    )
