"""Read-only Hostinger VPS audit with stable, secret-free JSON output."""

import argparse
import json
import os
import subprocess
from pathlib import Path

CHECKS = (
    "ubuntu_24_04", "hostname", "memory_capacity", "disk_capacity", "disk_free",
    "time_sync", "automatic_updates", "fail2ban", "docker", "ssh_root_disabled",
    "ssh_password_disabled", "ssh_keys_enabled", "firewall_active",
    "firewall_default_deny", "firewall_public_ports", "firewall_ssh_restricted",
    "docker_live_restore", "docker_no_new_privileges", "docker_log_rotation",
    "encrypted_volume_evidence",
)


def run(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def collect() -> dict:
    os_release = {}
    for raw in Path("/etc/os-release").read_text().splitlines():
        if "=" in raw:
            key, value = raw.split("=", 1)
            os_release[key] = value.strip('"')
    ssh = {}
    for raw in run(["sshd", "-T"]).splitlines():
        if " " in raw:
            key, value = raw.split(" ", 1)
            ssh[key] = value
    ufw = run(["ufw", "status", "verbose"]).lower()
    daemon = {}
    daemon_path = Path("/etc/docker/daemon.json")
    if daemon_path.exists():
        try:
            daemon = json.loads(daemon_path.read_text())
        except (OSError, json.JSONDecodeError):
            daemon = {}
    root = run(["df", "-BG", "--output=size,avail", "/"]).splitlines()
    disk = [int(item.removesuffix("G")) for item in root[-1].split()] if len(root) > 1 else [0, 0]
    memory_kib = int(run(["awk", "/MemTotal/ {print $2}", "/proc/meminfo"]) or 0)
    return {
        "os_id": os_release.get("ID", ""), "os_version": os_release.get("VERSION_ID", ""),
        "hostname": run(["hostname", "-f"]), "memory_gb": memory_kib // 1024 // 1024,
        "disk_gb": disk[0], "disk_free_gb": disk[1],
        "time_synced": run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"]).lower() == "yes",
        "services": {name: run(["systemctl", "is-enabled", name]) == "enabled" for name in ("unattended-upgrades", "fail2ban", "docker")},
        "ssh": ssh, "ufw": ufw, "docker_daemon": daemon,
        "encrypted_volume": bool(run(["lsblk", "-n", "-o", "TYPE"]).split().count("crypt")),
    }


def evaluate(evidence: dict, config: dict[str, str]) -> dict[str, bool]:
    ufw = evidence.get("ufw", "")
    daemon = evidence.get("docker_daemon", {})
    log_opts = daemon.get("log-opts", {}) if isinstance(daemon, dict) else {}
    ssh = evidence.get("ssh", {})
    services = evidence.get("services", {})
    allowed = config["SSH_ALLOWED_CIDR"].lower()
    return {
        "ubuntu_24_04": evidence.get("os_id") == "ubuntu" and evidence.get("os_version") == "24.04",
        "hostname": evidence.get("hostname") == config["EXPECTED_HOSTNAME"],
        "memory_capacity": evidence.get("memory_gb", 0) >= int(config["HOST_MIN_MEMORY_GB"]),
        "disk_capacity": evidence.get("disk_gb", 0) >= int(config["HOST_MIN_DISK_GB"]),
        "disk_free": evidence.get("disk_free_gb", 0) >= int(config["HOST_MIN_FREE_DISK_GB"]),
        "time_sync": evidence.get("time_synced") is True,
        "automatic_updates": services.get("unattended-upgrades") is True,
        "fail2ban": services.get("fail2ban") is True,
        "docker": services.get("docker") is True,
        "ssh_root_disabled": ssh.get("permitrootlogin") == "no",
        "ssh_password_disabled": ssh.get("passwordauthentication") == "no",
        "ssh_keys_enabled": ssh.get("pubkeyauthentication") == "yes",
        "firewall_active": "status: active" in ufw,
        "firewall_default_deny": "default: deny (incoming)" in ufw,
        "firewall_public_ports": "80/tcp" in ufw and "443/tcp" in ufw and "443/udp" in ufw,
        "firewall_ssh_restricted": "22/tcp" in ufw and allowed in ufw and "22/tcp                   allow       anywhere" not in ufw,
        "docker_live_restore": daemon.get("live-restore") is True,
        "docker_no_new_privileges": daemon.get("no-new-privileges") is True,
        "docker_log_rotation": daemon.get("log-driver") == "json-file" and log_opts.get("max-size") == "10m" and log_opts.get("max-file") == "5",
        "encrypted_volume_evidence": evidence.get("encrypted_volume") is True,
    }


def write_prometheus(path: Path, checks: dict[str, bool], status: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# TYPE aperture_host_audit_check gauge"]
    lines.extend(
        f'aperture_host_audit_check{{check="{key}"}} {1 if value else 0}'
        for key, value in sorted(checks.items())
    )
    lines.extend(
        ("# TYPE aperture_host_audit_pass gauge", f"aperture_host_audit_pass {1 if status == 'pass' else 0}")
    )
    temporary = path.with_name(f".{path.name}.{os.getpid()}")
    temporary.write_text("\n".join(lines) + "\n")
    os.chmod(temporary, 0o644)
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--prometheus-output", type=Path)
    args = parser.parse_args()
    try:
        from validate_host_hardening import load, validate
        config = load(args.config)
        validate(config, apply=False)
        evidence = json.loads(args.fixture.read_text()) if args.fixture else collect()
        checks = evaluate(evidence, config)
        result = {"event": "host.audit", "status": "pass" if all(checks.values()) else "fail", "checks": checks}
    except Exception:
        result = {"event": "host.audit", "status": "error", "checks": {key: False for key in CHECKS}}
    if args.prometheus_output:
        write_prometheus(args.prometheus_output, result["checks"], result["status"])
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
