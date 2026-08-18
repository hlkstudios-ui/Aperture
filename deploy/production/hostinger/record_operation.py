"""Atomically record only successful bounded production operations."""

import argparse
import os
import tempfile
import time
from pathlib import Path

OPERATIONS = {"backup", "maintenance", "preflight", "restore", "media_replication"}


def record(directory: Path, operation: str, *, timestamp: int | None = None) -> Path:
    if operation not in OPERATIONS:
        raise ValueError("operation is not allowlisted")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{operation}.prom"
    descriptor, temporary_name = tempfile.mkstemp(prefix=".operation-", dir=directory)
    temporary = Path(temporary_name)
    try:
        value = int(time.time()) if timestamp is None else timestamp
        content = (
            "# TYPE aperture_operation_last_success_unixtime gauge\n"
            f'aperture_operation_last_success_unixtime{{operation="{operation}"}} {value}\n'
        )
        os.write(descriptor, content.encode())
        os.close(descriptor)
        descriptor = -1
        os.chmod(temporary, 0o644)
        os.replace(temporary, target)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
    return target


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--operation", choices=sorted(OPERATIONS), required=True)
    args = parser.parse_args()
    record(args.directory, args.operation)
    print("Operation success evidence recorded.")


if __name__ == "__main__":
    main()
