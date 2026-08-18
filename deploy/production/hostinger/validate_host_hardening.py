"""Validate host-hardening inputs without changing the host."""

import argparse
import ipaddress
from pathlib import Path

REQUIRED = {
    "EXPECTED_HOSTNAME", "SSH_ALLOWED_CIDR", "HOST_MIN_MEMORY_GB",
    "HOST_MIN_DISK_GB", "HOST_MIN_FREE_DISK_GB", "HOST_HARDENING_CONFIRMATION",
}
CONFIRMATION = "HARDEN_HOSTINGER_VPS_WITH_RESTRICTED_SSH"


def load(path: Path) -> dict[str, str]:
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


def validate(values: dict[str, str], *, apply: bool) -> None:
    dummy = sorted(key for key, value in values.items() if "DUMMY" in value.upper())
    if dummy:
        raise ValueError("replace dummy labels before host audit/apply: " + ", ".join(dummy))
    network = ipaddress.ip_network(values["SSH_ALLOWED_CIDR"], strict=False)
    if network.prefixlen < (24 if network.version == 4 else 64):
        raise ValueError("SSH_ALLOWED_CIDR is too broad; require IPv4 /24+ or IPv6 /64+")
    if values["EXPECTED_HOSTNAME"] in {"localhost", "localhost.localdomain"}:
        raise ValueError("EXPECTED_HOSTNAME must identify the production VPS")
    memory = int(values["HOST_MIN_MEMORY_GB"])
    disk = int(values["HOST_MIN_DISK_GB"])
    free = int(values["HOST_MIN_FREE_DISK_GB"])
    if memory < 24 or disk < 100 or free < 50 or free >= disk:
        raise ValueError("host capacity floors are unsafe for the production profile")
    if apply and values["HOST_HARDENING_CONFIRMATION"] != CONFIRMATION:
        raise ValueError("host hardening confirmation is invalid")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--mode", choices=("audit", "apply"), required=True)
    args = parser.parse_args()
    validate(load(args.input), apply=args.mode == "apply")
    print("Host-hardening inputs are valid.")


if __name__ == "__main__":
    main()
