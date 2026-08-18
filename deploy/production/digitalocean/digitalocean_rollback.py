"""Inspect or initiate an explicit DigitalOcean App Platform rollback."""

import argparse
import json
import os
import sys
import urllib.request
import uuid

API_ROOT = "https://api.digitalocean.com/v2/apps"
CONFIRMATION = "ROLLBACK_APPLICATION_TRAFFIC"


def identifier(label: str, value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except ValueError as error:
        raise ValueError(f"{label} must be a UUID") from error


def configuration(mode: str) -> dict[str, str]:
    if mode == "dummy":
        return {
            "app_id": "11111111-1111-4111-8111-111111111111",
            "deployment_id": "22222222-2222-4222-8222-222222222222",
            "token": "DUMMY_NOT_USED",
        }
    values = {
        "app_id": os.environ.get("DIGITALOCEAN_APP_ID", ""),
        "deployment_id": os.environ.get("DIGITALOCEAN_ROLLBACK_DEPLOYMENT_ID", ""),
        "token": os.environ.get("DIGITALOCEAN_TOKEN", ""),
    }
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise RuntimeError("missing rollback configuration labels: " + ", ".join(missing))
    if mode == "execute" and os.environ.get("ROLLBACK_CONFIRMATION") != CONFIRMATION:
        raise RuntimeError("ROLLBACK_CONFIRMATION does not authorize traffic rollback")
    return values


def api_request(path: str, token: str, payload: dict[str, str] | None = None) -> dict:
    body = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        f"{API_ROOT}/{path}",
        data=body,
        method="GET" if body is None else "POST",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise RuntimeError("provider response is invalid")
    return value


def inspect_target(app_id: str, deployment_id: str, token: str) -> dict[str, str]:
    value = api_request(f"{app_id}/deployments/{deployment_id}", token)
    deployment = value.get("deployment")
    if not isinstance(deployment, dict) or deployment.get("id") != deployment_id:
        raise RuntimeError("provider did not return the requested deployment")
    phase = deployment.get("phase")
    if phase != "ACTIVE":
        raise RuntimeError("rollback target is not a successfully completed deployment")
    return {
        "deployment_id": deployment_id,
        "phase": phase,
        "created_at": str(deployment.get("created_at", "unknown")),
    }


def run(mode: str) -> dict[str, str]:
    values = configuration(mode)
    app_id = identifier("DIGITALOCEAN_APP_ID", values["app_id"])
    deployment_id = identifier(
        "DIGITALOCEAN_ROLLBACK_DEPLOYMENT_ID", values["deployment_id"]
    )
    if mode == "dummy":
        return {"event": "rollback.dummy_validated", "status": "pass"}
    target = inspect_target(app_id, deployment_id, values["token"])
    if mode == "inspect":
        return {"event": "rollback.target_inspected", "status": "pass", **target}
    response = api_request(
        f"{app_id}/rollback", values["token"], {"deployment_id": deployment_id}
    )
    deployment = response.get("deployment")
    if not isinstance(deployment, dict) or not deployment.get("id"):
        raise RuntimeError("provider did not return a rollback deployment")
    return {
        "event": "rollback.initiated",
        "status": "pending",
        "rollback_deployment_id": str(deployment["id"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("dummy", "inspect", "execute"), required=True)
    args = parser.parse_args()
    try:
        result = run(args.mode)
    except Exception:
        print(json.dumps({"event": "rollback.failed", "status": "fail"}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
