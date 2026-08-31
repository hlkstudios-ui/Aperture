"""Acquire or release the Redis DB14 owner fence used by the E2E wrapper."""

import argparse
import os
import sys

from e2e_guard import require_e2e_test_environment

from app.e2e_redis_fence import (
    E2ERedisFenceError,
    acquire_owner,
    release_owner,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("action", choices=("acquire", "release"))
    result.add_argument(
        "--reclaim-dead-local",
        action="store_true",
        help="reclaim only when the recorded owner is local and its PID is proven dead",
    )
    return result


def main() -> int:
    arguments = parser().parse_args()
    settings = require_e2e_test_environment(verify_redis_ownership=False)
    run_id = os.environ.get("E2E_RUN_ID", "")
    token = os.environ.get("E2E_OWNER_TOKEN", "")
    try:
        if arguments.action == "acquire":
            owner_pid = int(os.environ.get("E2E_OWNER_PID", ""))
            acquire_owner(
                settings.redis_url,
                run_id,
                token,
                owner_pid,
                reclaim_dead_local=arguments.reclaim_dead_local,
            )
        else:
            if arguments.reclaim_dead_local:
                parser().error("--reclaim-dead-local is valid only with acquire")
            release_owner(settings.redis_url, run_id, token)
    except (E2ERedisFenceError, ValueError) as exc:
        print(f"E2E Redis owner {arguments.action} refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
