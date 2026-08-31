from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
OPENAI_KEY = "OPENAI_API_KEY"


def _environment_keys(component: dict) -> set[str]:
    environment = component.get("environment", {})
    return set(environment) if isinstance(environment, dict) else set()


def test_hostinger_openai_key_is_injected_only_into_api() -> None:
    document = yaml.safe_load(
        (ROOT / "deploy/production/hostinger/compose.yml").read_text()
    )
    services = document["services"]
    assert OPENAI_KEY in _environment_keys(services["api"])
    for name, component in services.items():
        if name != "api":
            assert OPENAI_KEY not in _environment_keys(component), name


def test_digitalocean_openai_key_is_in_api_only_anchor() -> None:
    document = yaml.safe_load(
        (ROOT / "deploy/production/digitalocean/app.template.yaml").read_text()
    )
    private_api_keys = {item["key"] for item in document["x-api-auth-envs"]}
    shared_api_keys = {item["key"] for item in document["x-api-envs"]}
    web = next(item for item in document["services"] if item["name"] == "web")
    web_keys = {item["key"] for item in web["envs"]}
    assert OPENAI_KEY in private_api_keys
    assert OPENAI_KEY not in shared_api_keys
    assert OPENAI_KEY not in web_keys


def test_free_tier_openai_key_is_api_only() -> None:
    document = yaml.safe_load(
        (ROOT / "deploy/staging/free-tier/render.yaml").read_text()
    )
    api = next(item for item in document["services"] if item["name"].endswith("-api"))
    web = next(item for item in document["services"] if item["name"].endswith("-web"))
    assert OPENAI_KEY in {item["key"] for item in api["envVars"]}
    assert OPENAI_KEY not in {item["key"] for item in web["envVars"]}
