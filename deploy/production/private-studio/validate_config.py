"""Validate private Studio gateway inputs without printing their values."""

import argparse
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT.parents[2] / ".env"
REQUIRED = {
    "CADDY_IMAGE",
    "PUBLIC_APP_ORIGIN",
    "PUBLIC_APP_HOST",
    "ORIGIN_EDGE_SECRET",
    "STUDIO_EDGE_SECRET",
    "TAILSCALE_AUTH_KEY",
    "TAILSCALE_OWNER_EMAIL",
}


def image_reference(value: str) -> str:
    if "@sha256:" not in value or any(character.isspace() for character in value):
        raise ValueError("CADDY_IMAGE must be an immutable registry digest reference")
    repository, digest = value.rsplit("@sha256:", 1)
    if "/" not in repository or repository.lower() != repository:
        raise ValueError("CADDY_IMAGE must include a lowercase registry/repository")
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ValueError("CADDY_IMAGE must include a sha256 digest")
    return value


def load(path: Path = DEFAULT_INPUT) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"invalid line {number}")
        key, value = line.split("=", 1)
        if key in REQUIRED:
            values[key] = value
    missing = sorted(REQUIRED - values.keys())
    if missing:
        raise ValueError("missing labels: " + ", ".join(missing))
    return values


def validate(values: dict[str, str], *, deploy: bool) -> None:
    image_reference(values["CADDY_IMAGE"])
    parsed = urlsplit(values["PUBLIC_APP_ORIGIN"])
    if parsed.scheme != "https" or not parsed.hostname or parsed.path not in {"", "/"}:
        raise ValueError("PUBLIC_APP_ORIGIN must be an HTTPS origin without a path")
    if values["PUBLIC_APP_HOST"].lower() != parsed.hostname.lower():
        raise ValueError("PUBLIC_APP_HOST must match PUBLIC_APP_ORIGIN")
    if "@" not in values["TAILSCALE_OWNER_EMAIL"]:
        raise ValueError("TAILSCALE_OWNER_EMAIL must be an email address")
    if deploy:
        dummy = sorted(key for key, value in values.items() if "DUMMY" in value.upper())
        if dummy:
            raise ValueError("replace dummy labels before deploy: " + ", ".join(dummy))
        if len(values["STUDIO_EDGE_SECRET"]) < 48:
            raise ValueError("STUDIO_EDGE_SECRET must contain at least 48 characters")
        if len(values["ORIGIN_EDGE_SECRET"]) < 48:
            raise ValueError("ORIGIN_EDGE_SECRET must contain at least 48 characters")
        if values["ORIGIN_EDGE_SECRET"] == values["STUDIO_EDGE_SECRET"]:
            raise ValueError("origin and Studio edge secrets must be independent")
        if values["TAILSCALE_AUTH_KEY"] and not values["TAILSCALE_AUTH_KEY"].startswith(
            "tskey-"
        ):
            raise ValueError("TAILSCALE_AUTH_KEY is not a Tailscale enrollment key")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("dummy", "deploy"), required=True)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()
    validate(load(args.input), deploy=args.mode == "deploy")
    print("Private Studio gateway configuration is structurally valid.")


if __name__ == "__main__":
    main()
