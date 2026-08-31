"""Render the private Studio gateway environment without enrollment secrets."""

import argparse
import os
from pathlib import Path
import tempfile

from validate_config import DEFAULT_INPUT, load, validate


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "runtime.local.env"
RUNTIME_LABELS = (
    "CADDY_IMAGE",
    "ORIGIN_EDGE_SECRET",
    "PUBLIC_APP_HOST",
    "PUBLIC_APP_ORIGIN",
    "STUDIO_EDGE_SECRET",
)


def atomic_write(path: Path, content: str) -> None:
    if not path.parent.is_dir():
        raise ValueError("output parent directory does not exist")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            descriptor = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def render(input_path: Path, output_path: Path) -> None:
    if input_path.resolve() == output_path.resolve():
        raise ValueError("render output must differ from the owner credential file")
    values = load(input_path)
    validate(values, deploy=True)
    content = "".join(f"{label}={values[label]}\n" for label in RUNTIME_LABELS)
    atomic_write(output_path, content)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    render(args.input, args.output)
    print("Sanitized private Studio runtime environment rendered.")


if __name__ == "__main__":
    main()
