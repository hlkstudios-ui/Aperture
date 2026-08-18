"""Supervise the free-tier staging API and workers in one disposable service."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time


def terminate(processes: list[subprocess.Popen[bytes]]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + 10
    for process in processes:
        if process.poll() is None:
            try:
                process.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                process.kill()


def main() -> int:
    subprocess.run(["alembic", "upgrade", "head"], check=True)
    port = os.environ.get("PORT", "10000")
    commands = [
        [
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            port,
            "--proxy-headers",
            "--forwarded-allow-ips=*",
        ],
        [sys.executable, "-m", "app.media_worker"],
        [sys.executable, "-m", "app.scene_worker"],
    ]
    processes = [subprocess.Popen(command) for command in commands]

    def stop(_signum: int, _frame: object) -> None:
        terminate(processes)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while True:
            for process in processes:
                result = process.poll()
                if result is not None:
                    terminate(processes)
                    return result or 1
            time.sleep(1)
    finally:
        terminate(processes)


if __name__ == "__main__":
    raise SystemExit(main())
