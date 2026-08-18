import hashlib
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.auth import hash_password
from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.malware_scanner import ScannerUnavailable
from app.models import Admin, AuditLog, MediaAsset
from app.object_storage import s3_client


def test_admin_direct_upload_integrity_and_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    suffix = uuid.uuid4().hex
    email = f"upload-{suffix}@example.com"
    password = "AdministratorPass123"
    content = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + b"Aperture fixture" * 32
    checksum = hashlib.sha256(content).hexdigest()
    with SessionLocal() as db:
        admin = Admin(email=email, password_hash=hash_password(password))
        db.add(admin)
        db.commit()
        admin_id = admin.id

    created_assets: list[tuple[str, str]] = []
    try:
        with TestClient(app) as client:
            assert client.get("/admin/uploads").status_code == 401
            assert (
                client.post(
                    "/admin/auth/login", json={"email": email, "password": password}
                ).status_code
                == 200
            )
            invalid = client.post(
                "/admin/uploads/initialize",
                json={
                    "original_filename": "../unsafe.mp4",
                    "media_type": "video/mp4",
                    "size_bytes": len(content),
                    "checksum_sha256": checksum,
                },
            )
            assert invalid.status_code == 422
            unsupported = client.post(
                "/admin/uploads/initialize",
                json={
                    "original_filename": "payload.exe",
                    "media_type": "application/octet-stream",
                    "size_bytes": len(content),
                    "checksum_sha256": checksum,
                },
            )
            assert unsupported.status_code == 422

            initialized = client.post(
                "/admin/uploads/initialize",
                json={
                    "original_filename": "development-fixture.mp4",
                    "media_type": "video/mp4",
                    "size_bytes": len(content),
                    "checksum_sha256": checksum,
                },
            )
            assert initialized.status_code == 201, initialized.text
            ticket = initialized.json()
            asset_id = ticket["asset"]["id"]
            storage_key = ticket["asset"]["storage_key"]
            created_assets.append((asset_id, storage_key))
            assert "development-fixture" not in storage_key
            transfer = httpx.put(ticket["upload_url"], content=content, headers=ticket["headers"])
            assert transfer.status_code == 200, transfer.text
            completed = client.post(f"/admin/uploads/{asset_id}/complete")
            assert completed.status_code == 200, completed.text
            assert completed.json()["state"] == "completed"
            assert completed.json()["malware_scan_status"] == "clean"
            assert completed.json()["malware_scan_engine"] == "eicar_test_scanner"
            assert completed.json()["malware_scanned_at"] is not None
            head = s3_client().head_object(Bucket=get_settings().s3_bucket, Key=storage_key)
            assert head["ContentLength"] == len(content)
            assert head["Metadata"]["sha256"] == checksum

            invalid_content = b"not an actual mp4 container"
            invalid_checksum = hashlib.sha256(invalid_content).hexdigest()
            invalid_object = client.post(
                "/admin/uploads/initialize",
                json={
                    "original_filename": "invalid-signature.mp4",
                    "media_type": "video/mp4",
                    "size_bytes": len(invalid_content),
                    "checksum_sha256": invalid_checksum,
                },
            ).json()
            invalid_id = invalid_object["asset"]["id"]
            invalid_key = invalid_object["asset"]["storage_key"]
            created_assets.append((invalid_id, invalid_key))
            assert (
                httpx.put(
                    invalid_object["upload_url"],
                    content=invalid_content,
                    headers=invalid_object["headers"],
                ).status_code
                == 200
            )
            assert client.post(f"/admin/uploads/{invalid_id}/complete").status_code == 409
            assert client.post(f"/admin/uploads/{invalid_id}/retry").status_code == 200
            cancelled = client.delete(f"/admin/uploads/{invalid_id}")
            assert cancelled.status_code == 200
            assert cancelled.json()["state"] == "cancelled"

            infected_content = content + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"
            infected_checksum = hashlib.sha256(infected_content).hexdigest()
            infected = client.post(
                "/admin/uploads/initialize",
                json={
                    "original_filename": "scanner-fixture.mp4",
                    "media_type": "video/mp4",
                    "size_bytes": len(infected_content),
                    "checksum_sha256": infected_checksum,
                },
            ).json()
            infected_id = infected["asset"]["id"]
            infected_key = infected["asset"]["storage_key"]
            created_assets.append((infected_id, infected_key))
            assert httpx.put(
                infected["upload_url"], content=infected_content, headers=infected["headers"]
            ).status_code == 200
            rejected = client.post(f"/admin/uploads/{infected_id}/complete")
            assert rejected.status_code == 409
            rejected_asset = next(
                item for item in client.get("/admin/uploads").json() if item["id"] == infected_id
            )
            assert rejected_asset["state"] == "failed"
            assert rejected_asset["malware_scan_status"] == "infected"
            assert rejected_asset["malware_scan_signature"] == "EICAR-Test-Signature"

            unavailable = client.post(
                "/admin/uploads/initialize",
                json={
                    "original_filename": "scanner-retry.mp4",
                    "media_type": "video/mp4",
                    "size_bytes": len(content),
                    "checksum_sha256": checksum,
                },
            ).json()
            unavailable_id = unavailable["asset"]["id"]
            unavailable_key = unavailable["asset"]["storage_key"]
            created_assets.append((unavailable_id, unavailable_key))
            assert httpx.put(
                unavailable["upload_url"], content=content, headers=unavailable["headers"]
            ).status_code == 200

            def scanner_down(_asset):
                raise ScannerUnavailable("test outage")

            monkeypatch.setattr("app.routes.admin_uploads.scan_asset", scanner_down)
            quarantined = client.post(f"/admin/uploads/{unavailable_id}/complete")
            assert quarantined.status_code == 503
            quarantined_asset = next(
                item
                for item in client.get("/admin/uploads").json()
                if item["id"] == unavailable_id
            )
            assert quarantined_asset["state"] == "uploading"
            assert quarantined_asset["malware_scan_status"] == "error"
            monkeypatch.undo()
            retried_scan = client.post(f"/admin/uploads/{unavailable_id}/complete")
            assert retried_scan.status_code == 200
            assert retried_scan.json()["malware_scan_status"] == "clean"
    finally:
        for _, storage_key in created_assets:
            s3_client().delete_object(Bucket=get_settings().s3_bucket, Key=storage_key)
        with SessionLocal() as db:
            for asset_id, _ in created_assets:
                db.execute(delete(MediaAsset).where(MediaAsset.id == uuid.UUID(asset_id)))
            db.execute(delete(AuditLog).where(AuditLog.actor_id == admin_id))
            db.execute(delete(Admin).where(Admin.id == admin_id))
            db.commit()


def test_multipart_upload_resumes_from_authoritative_parts() -> None:
    token = uuid.uuid4().hex
    email = f"multipart-{token}@example.com"
    password = "AdministratorPass123"
    content = b"\x00\x00\x00\x18ftypisom" + b"x" * (17 * 1024 * 1024)
    checksum = hashlib.sha256(content).hexdigest()
    with SessionLocal() as db:
        admin = Admin(email=email, password_hash=hash_password(password))
        db.add(admin)
        db.commit()
        admin_id = admin.id
    asset_id = storage_key = None
    try:
        with TestClient(app) as client:
            assert client.post(
                "/admin/auth/login", json={"email": email, "password": password}
            ).status_code == 200
            initialized = client.post(
                "/admin/uploads/initialize-multipart",
                json={
                    "original_filename": "resumable.mp4",
                    "media_type": "video/mp4",
                    "size_bytes": len(content),
                    "checksum_sha256": checksum,
                },
            )
            assert initialized.status_code == 201, initialized.text
            ticket = initialized.json()
            asset_id = ticket["asset"]["id"]
            storage_key = ticket["asset"]["storage_key"]
            part_size = ticket["part_size"]
            for number, start in enumerate(range(0, len(content), part_size), 1):
                signed = client.post(
                    f"/admin/uploads/{asset_id}/multipart/parts/{number}"
                ).json()
                public_endpoint = get_settings().s3_public_endpoint
                if public_endpoint is not None:
                    assert signed["upload_url"].startswith(str(public_endpoint).rstrip("/"))
                assert httpx.put(
                    signed["upload_url"], content=content[start : start + part_size]
                ).status_code == 200
                resumed = client.get(f"/admin/uploads/{asset_id}/multipart")
                assert resumed.status_code == 200
                assert resumed.json()["uploaded_parts"] == list(range(1, number + 1))
            completed = client.post(f"/admin/uploads/{asset_id}/multipart/complete")
            assert completed.status_code == 200, completed.text
            assert completed.json()["state"] == "completed"
            assert completed.json()["upload_strategy"] == "multipart"
            repeated = client.post(f"/admin/uploads/{asset_id}/multipart/complete")
            assert repeated.status_code == 200
            assert repeated.json()["id"] == asset_id
    finally:
        if storage_key:
            s3_client().delete_object(Bucket=get_settings().s3_bucket, Key=storage_key)
        with SessionLocal() as db:
            if asset_id:
                db.execute(delete(MediaAsset).where(MediaAsset.id == uuid.UUID(asset_id)))
            db.execute(delete(AuditLog).where(AuditLog.actor_id == admin_id))
            db.execute(delete(Admin).where(Admin.id == admin_id))
            db.commit()
