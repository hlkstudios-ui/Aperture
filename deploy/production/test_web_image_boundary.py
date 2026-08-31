import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "apps" / "web" / "Dockerfile"


def test_web_builder_copies_only_required_root_e2e_sources() -> None:
    dockerfile = DOCKERFILE.read_text()

    assert (
        "COPY tests/e2e/global-setup.ts tests/e2e/safety.ts ./tests/e2e/"
        in dockerfile
    )
    assert "COPY tests ./tests" not in dockerfile
    assert "COPY . ." not in dockerfile


def test_web_runtime_receives_only_standalone_build_outputs() -> None:
    dockerfile = DOCKERFILE.read_text()
    assert re.search(
        r"FROM gcr\.io/distroless/nodejs24-debian13:nonroot@sha256:[0-9a-f]{64} AS runtime",
        dockerfile,
    )
    runtime = dockerfile.split(
        "FROM gcr.io/distroless/nodejs24-debian13:nonroot@sha256:", maxsplit=1
    )[1]

    assert "COPY tests/" not in runtime
    assert "COPY --from=builder" in runtime
    assert "USER nonroot" in runtime
    assert 'CMD ["apps/web/server.js"]' in runtime
    assert "apt-get" not in runtime
    assert "npm " not in runtime
