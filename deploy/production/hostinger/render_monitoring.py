"""Render a mode-0600 private Prometheus config without logging its credential."""

import argparse
import json
import os
import tempfile
from pathlib import Path

from validate_config import load

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "prometheus.template.yml"
DEFAULT_INPUT = ROOT.parents[2] / ".env"
DEFAULT_OUTPUT = ROOT / "prometheus.local.yml"
DEFAULT_TARGETS_OUTPUT = ROOT / "blackbox-targets.local.yml"


def atomic_write(output_path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output_path.stem}-", dir=output_path.parent)
    temporary = Path(temporary_name)
    try:
        os.write(descriptor, content.encode())
        os.close(descriptor)
        descriptor = -1
        os.chmod(temporary, 0o600)
        os.replace(temporary, output_path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def render(input_path: Path, output_path: Path, *, deploy: bool, targets_output: Path | None = None) -> None:
    values = load(input_path)
    token = values.get("METRICS_BEARER_TOKEN", "")
    if not token:
        raise ValueError("METRICS_BEARER_TOKEN is missing")
    if deploy and ("DUMMY" in token.upper() or len(token) < 32):
        raise ValueError("replace METRICS_BEARER_TOKEN before deployment")
    template = TEMPLATE.read_text()
    if template.count("__METRICS_BEARER_TOKEN__") != 1:
        raise RuntimeError("Prometheus template token marker is invalid")
    rendered = template.replace("__METRICS_BEARER_TOKEN__", json.dumps(token))
    atomic_write(output_path, rendered)
    target_path = DEFAULT_TARGETS_OUTPUT if targets_output is None else targets_output
    targets = [
        ("web", "https_security_headers", f'https://{values["WEB_HOSTNAME"]}/'),
        ("api", "https_api_ready", f'https://{values["WEB_HOSTNAME"]}/api/ready'),
        ("storage", "https_2xx", f'https://{values["STORAGE_HOSTNAME"]}/minio/health/ready'),
        ("cdn", "https_reachable", f'https://{values["CDN_HOSTNAME"]}/'),
        ("origin-denial", "https_origin_denied", f'https://{values["ORIGIN_HOSTNAME"]}/'),
    ]
    target_groups = [
        {"targets": [url], "labels": {"surface": surface, "module": module}}
        for surface, module, url in targets
    ]
    atomic_write(target_path, json.dumps(target_groups, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("dummy", "deploy"), required=True)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--targets-output", type=Path, default=DEFAULT_TARGETS_OUTPUT)
    args = parser.parse_args()
    render(args.input, args.output, deploy=args.mode == "deploy", targets_output=args.targets_output)
    print("Private Prometheus configuration rendered.")


if __name__ == "__main__":
    main()
