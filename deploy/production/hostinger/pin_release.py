"""Atomically pin a verified three-image digest set into Hostinger credentials."""

import argparse
import os
import stat
import tempfile
from pathlib import Path

from validate_config import image_reference

ROOT = Path(__file__).resolve().parent
DEFAULT_CREDENTIALS = ROOT.parents[2] / ".env"
LABELS = {"api": "API_IMAGE", "web": "WEB_IMAGE", "backup": "BACKUP_IMAGE"}


def pin(path: Path, images: dict[str, str]) -> None:
    if set(images) != set(LABELS):
        raise ValueError("release must contain exactly api, web, and backup images")
    for component, value in images.items():
        image_reference(value, f"{component} image")
        if "dummy" in value.lower() or value.endswith("0" * 64):
            raise ValueError(f"{component} image is not a deployable digest")
    original = path.read_text()
    updated = original
    for component, label in LABELS.items():
        lines = [line for line in updated.splitlines() if line.startswith(f"{label}=")]
        if len(lines) != 1:
            raise RuntimeError(f"credentials must contain exactly one {label}")
        updated = updated.replace(lines[0], f"{label}={images[component]}", 1)
    mode = stat.S_IMODE(path.stat().st_mode)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".release-pin-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.write(descriptor, (updated + ("" if updated.endswith("\n") else "\n")).encode())
        os.close(descriptor)
        descriptor = -1
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials", type=Path, default=DEFAULT_CREDENTIALS)
    parser.add_argument("--api", required=True)
    parser.add_argument("--web", required=True)
    parser.add_argument("--backup", required=True)
    args = parser.parse_args()
    pin(args.credentials, {"api": args.api, "web": args.web, "backup": args.backup})
    print("Hostinger release images pinned by digest.")


if __name__ == "__main__":
    main()
