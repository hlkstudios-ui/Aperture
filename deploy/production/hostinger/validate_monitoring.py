"""Validate the private monitoring contract without contacting public targets."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

import yaml

REQUIRED_SURFACES = {"web", "api", "storage", "cdn", "origin-denial"}
REQUIRED_ALERTS = {
    "ApertureHostAuditFailed", "ApertureHostDiskSpaceLow", "ApertureHostClockUnsynchronized",
    "ApertureProductionBackupStale", "ApertureMediaReplicationStale",
    "ApertureMaintenanceStale", "AperturePublicSurfaceUnavailable",
    "ApertureCertificateExpiring",
}


def validate(prometheus_path: Path, blackbox_path: Path, targets_path: Path, rules_path: Path) -> None:
    prometheus = yaml.safe_load(prometheus_path.read_text())
    blackbox = yaml.safe_load(blackbox_path.read_text())
    targets = json.loads(targets_path.read_text())
    rules = yaml.safe_load(rules_path.read_text())
    jobs = {job.get("job_name"): job for job in prometheus.get("scrape_configs", [])}
    if not {"aperture-api", "aperture-host", "aperture-public-edge"}.issubset(jobs):
        raise ValueError("required private scrape jobs are missing")
    if "credentials" not in jobs["aperture-api"].get("authorization", {}):
        raise ValueError("API metrics scrape is not authenticated")
    modules = set(blackbox.get("modules", {}))
    surfaces: set[str] = set()
    for group in targets:
        labels = group.get("labels", {})
        surface = labels.get("surface")
        module = labels.get("module")
        urls = group.get("targets", [])
        if surface in surfaces or surface not in REQUIRED_SURFACES:
            raise ValueError("public probe surfaces are duplicated or unknown")
        if module not in modules or len(urls) != 1 or urlsplit(urls[0]).scheme != "https":
            raise ValueError("public probe target is unsafe or references an unknown module")
        surfaces.add(surface)
    if surfaces != REQUIRED_SURFACES:
        raise ValueError("public probe surface coverage is incomplete")
    origin_group = next(group for group in targets if group["labels"]["surface"] == "origin-denial")
    if origin_group["labels"]["module"] != "https_origin_denied":
        raise ValueError("direct origin is not bound to the denial probe")
    alert_names = {
        rule.get("alert")
        for group in rules.get("groups", [])
        for rule in group.get("rules", [])
    }
    if not REQUIRED_ALERTS.issubset(alert_names):
        raise ValueError("Hostinger monitoring alerts are incomplete")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prometheus", type=Path, required=True)
    parser.add_argument("--blackbox", type=Path, required=True)
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--rules", type=Path, required=True)
    args = parser.parse_args()
    validate(args.prometheus, args.blackbox, args.targets, args.rules)
    print("Private monitoring contract is structurally valid.")


if __name__ == "__main__":
    main()
