import contextlib
import copy
import io
import json
import unittest
from urllib.error import URLError

import cloudflare_saas_preflight as preflight


ZONE_ID = "a" * 32
ACCOUNT_ID = "b" * 32
NAMESPACE_ID = "c" * 32
PREFLIGHT_TOKEN = "read-only-cloudflare-topology-token"
RUNTIME_TOKEN = "custom-hostnames-runtime-token"
TURNSTILE_TOKEN = "turnstile-widget-runtime-token"
TURNSTILE_SITE_KEY = "0x4AAAA-aperture-widget-key"
TURNSTILE_WIDGET_SECRET = "turnstile-widget-secret-must-never-leak"


def values() -> dict[str, str]:
    return {
        "CLOUDFLARE_CUSTOM_DOMAIN_PREFLIGHT_API_TOKEN": PREFLIGHT_TOKEN,
        "CLOUDFLARE_CUSTOM_HOSTNAMES_API_TOKEN": RUNTIME_TOKEN,
        "CLOUDFLARE_TURNSTILE_API_TOKEN": TURNSTILE_TOKEN,
        "CLOUDFLARE_ZONE_ID": ZONE_ID,
        "CLOUDFLARE_ACCOUNT_ID": ACCOUNT_ID,
        "CLOUDFLARE_SITE_DOMAINS_KV_NAMESPACE_ID": NAMESPACE_ID,
        "CUSTOM_DOMAIN_CNAME_TARGET": "customers.apertures.online",
        "CUSTOM_DOMAIN_FALLBACK_ORIGIN": "origin.apertures.online",
        "CUSTOM_DOMAIN_MAX_PER_SITE": "9",
        "ORIGIN_HOSTNAME": "origin.apertures.online",
        "STORAGE_HOSTNAME": "storage.apertures.online",
        "CDN_HOSTNAME": "media.apertures.online",
        "WEB_HOSTNAME": "apertures.online",
        "CAPTCHA_REQUIRED": "true",
        "NEXT_PUBLIC_TURNSTILE_SITE_KEY": TURNSTILE_SITE_KEY,
        "TURNSTILE_HOSTNAME_LIMIT": "10",
        "CLOUDFLARE_GEO_EDGE_SCRIPT_NAME": "aperture-production-geo-edge",
        "CLOUDFLARE_CDN_SCRIPT_NAME": "aperture-protected-media",
        "CLOUDFLARE_API_TIMEOUT_SECONDS": "8",
    }


def worker_settings(*, geo: bool) -> dict:
    bindings = [
        {
            "name": "CUSTOM_DOMAINS_ENABLED",
            "text": "true",
            "type": "plain_text",
        },
        {
            "name": "SITE_DOMAINS",
            "namespace_id": NAMESPACE_ID,
            "type": "kv_namespace",
        },
    ]
    if geo:
        bindings.extend(
            {"name": name, "type": "secret_text"}
            for name in preflight.REQUIRED_GEO_SECRETS
        )
    return {"bindings": bindings}


def topology_results() -> dict[tuple[str, tuple[tuple[str, str], ...]], object]:
    return {
        (
            f"/zones/{ZONE_ID}/custom_hostnames/fallback_origin",
            (),
        ): {"origin": "origin.apertures.online", "status": "active"},
        (
            f"/zones/{ZONE_ID}/dns_records",
            (
                ("match", "all"),
                ("name", "customers.apertures.online"),
                ("per_page", "100"),
                ("type", "CNAME"),
            ),
        ): [
            {
                "content": "origin.apertures.online",
                "name": "customers.apertures.online",
                "proxied": True,
                "type": "CNAME",
            }
        ],
        (f"/zones/{ZONE_ID}/workers/routes", ()): [
            {"id": "origin-exclusion", "pattern": "origin.apertures.online/*"},
            {
                "id": "storage-exclusion",
                "pattern": "storage.apertures.online/*",
                "script": None,
            },
            {"id": "cdn-exclusion", "pattern": "media.apertures.online/*"},
            {
                "id": "wildcard",
                "pattern": "*/*",
                "script": "aperture-production-geo-edge",
            },
        ],
        (
            f"/accounts/{ACCOUNT_ID}/workers/scripts/aperture-production-geo-edge/settings",
            (),
        ): worker_settings(geo=True),
        (
            f"/accounts/{ACCOUNT_ID}/workers/scripts/aperture-protected-media/settings",
            (),
        ): worker_settings(geo=False),
        (
            f"/accounts/{ACCOUNT_ID}/workers/domains",
            (
                ("hostname", "media.apertures.online"),
                ("service", "aperture-protected-media"),
                ("zone_id", ZONE_ID),
            ),
        ): [
            {
                "hostname": "media.apertures.online",
                "service": "aperture-protected-media",
                "zone_id": ZONE_ID,
            }
        ],
    }


def runtime_results() -> dict[tuple[str, tuple[tuple[str, str], ...]], object]:
    return {
        (
            f"/zones/{ZONE_ID}/custom_hostnames",
            (("page", "1"), ("per_page", "5")),
        ): [],
        (
            f"/accounts/{ACCOUNT_ID}/storage/kv/namespaces/{NAMESPACE_ID}/keys",
            (("limit", "10"),),
        ): [],
    }


def turnstile_results() -> dict[tuple[str, tuple[tuple[str, str], ...]], object]:
    return {
        (
            f"/accounts/{ACCOUNT_ID}/challenges/widgets/{TURNSTILE_SITE_KEY}",
            (),
        ): {
            "domains": ["apertures.online", "existing.customer.example"],
            "secret": TURNSTILE_WIDGET_SECRET,
            "sitekey": TURNSTILE_SITE_KEY,
        }
    }


class FakeClient:
    def __init__(self, results: dict) -> None:
        self.results = results
        self.calls: list[tuple[str, tuple[tuple[str, str], ...]]] = []

    def get(self, path: str, query: dict[str, str] | None = None):
        key = (path, tuple(sorted((query or {}).items())))
        self.calls.append(key)
        result = self.results[key]
        if isinstance(result, Exception):
            raise result
        return result


class FakeResponse:
    def __init__(self, value: bytes) -> None:
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int) -> bytes:
        return self.value


def run_with(
    topology: dict | None = None,
    runtime: dict | None = None,
    turnstile: dict | None = None,
) -> dict[str, object]:
    return preflight.run_preflight(
        preflight.validate_preflight_values(values()),
        FakeClient(topology if topology is not None else topology_results()),
        FakeClient(runtime if runtime is not None else runtime_results()),
        FakeClient(
            turnstile if turnstile is not None else turnstile_results()
        ),
    )


class CloudflareSaasPreflightTests(unittest.TestCase):
    def test_ready_infrastructure_uses_only_the_nine_expected_gets(self):
        topology_client = FakeClient(topology_results())
        runtime_client = FakeClient(runtime_results())
        turnstile_client = FakeClient(turnstile_results())
        result = preflight.run_preflight(
            preflight.validate_preflight_values(values()),
            topology_client,
            runtime_client,
            turnstile_client,
        )

        self.assertTrue(result["ready"])
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual(set(result["checks"]), set(preflight.CHECK_NAMES))
        self.assertEqual(len(topology_client.calls), 6)
        self.assertEqual(len(runtime_client.calls), 2)
        self.assertEqual(len(turnstile_client.calls), 1)
        self.assertNotIn(PREFLIGHT_TOKEN, json.dumps(result))
        self.assertNotIn(RUNTIME_TOKEN, json.dumps(result))
        self.assertNotIn(TURNSTILE_TOKEN, json.dumps(result))
        self.assertNotIn(TURNSTILE_WIDGET_SECRET, json.dumps(result))

    def test_each_infrastructure_boundary_fails_closed(self):
        routes_key = (f"/zones/{ZONE_ID}/workers/routes", ())
        geo_settings_key = (
            f"/accounts/{ACCOUNT_ID}/workers/scripts/aperture-production-geo-edge/settings",
            (),
        )
        cdn_settings_key = (
            f"/accounts/{ACCOUNT_ID}/workers/scripts/aperture-protected-media/settings",
            (),
        )
        cdn_domains_key = (
            f"/accounts/{ACCOUNT_ID}/workers/domains",
            (
                ("hostname", "media.apertures.online"),
                ("service", "aperture-protected-media"),
                ("zone_id", ZONE_ID),
            ),
        )
        custom_hostnames_key = (
            f"/zones/{ZONE_ID}/custom_hostnames",
            (("page", "1"), ("per_page", "5")),
        )
        kv_keys_key = (
            f"/accounts/{ACCOUNT_ID}/storage/kv/namespaces/{NAMESPACE_ID}/keys",
            (("limit", "10"),),
        )
        mutations = {
            "fallback_origin_active": lambda top, _runtime: top.__setitem__(
                (f"/zones/{ZONE_ID}/custom_hostnames/fallback_origin", ()),
                {"origin": "origin.apertures.online", "status": "pending_deployment"},
            ),
            "cname_target_proxied": lambda top, _runtime: top[
                (
                    f"/zones/{ZONE_ID}/dns_records",
                    (
                        ("match", "all"),
                        ("name", "customers.apertures.online"),
                        ("per_page", "100"),
                        ("type", "CNAME"),
                    ),
                )
            ][0].__setitem__("proxied", False),
            "wildcard_geo_route": lambda top, _runtime: top[routes_key][3].__setitem__(
                "script", "other-worker"
            ),
            "origin_route_excluded": lambda top, _runtime: top[routes_key][0].__setitem__(
                "script", "aperture-production-geo-edge"
            ),
            "storage_route_excluded": lambda top, _runtime: top[routes_key][1].__setitem__(
                "script", "aperture-production-geo-edge"
            ),
            "cdn_route_excluded": lambda top, _runtime: top[routes_key][2].__setitem__(
                "script", "aperture-production-geo-edge"
            ),
            "geo_site_domains_binding": lambda top, _runtime: top[
                geo_settings_key
            ]["bindings"][1].__setitem__("namespace_id", "d" * 32),
            "cdn_site_domains_binding": lambda top, _runtime: top[
                cdn_settings_key
            ]["bindings"][1].__setitem__("namespace_id", "d" * 32),
            "geo_custom_domains_enabled": lambda top, _runtime: top[
                geo_settings_key
            ]["bindings"][0].__setitem__("text", "false"),
            "cdn_custom_domains_enabled": lambda top, _runtime: top[
                cdn_settings_key
            ]["bindings"][0].__setitem__("text", "false"),
            "geo_required_secrets": lambda top, _runtime: top[geo_settings_key][
                "bindings"
            ].pop(),
            "cdn_custom_domain_mapping": lambda top, _runtime: top[
                cdn_domains_key
            ][0].__setitem__("service", "other-worker"),
            "runtime_custom_hostnames_readable": lambda _top, runtime: runtime.__setitem__(
                custom_hostnames_key, {}
            ),
            "runtime_site_domains_kv_readable": lambda _top, runtime: runtime.__setitem__(
                kv_keys_key, {}
            ),
        }
        for expected_check, mutate in mutations.items():
            with self.subTest(check=expected_check):
                topology = copy.deepcopy(topology_results())
                runtime = copy.deepcopy(runtime_results())
                mutate(topology, runtime)
                result = run_with(topology, runtime)
                self.assertFalse(result["ready"])
                self.assertFalse(result["checks"][expected_check])
                self.assertEqual(result["error"], "infrastructure_not_ready")

    def test_turnstile_widget_and_capacity_fail_closed_independently(self):
        canonical_missing = turnstile_results()
        canonical_missing[
            (
                f"/accounts/{ACCOUNT_ID}/challenges/widgets/{TURNSTILE_SITE_KEY}",
                (),
            )
        ]["domains"] = ["other.example"]
        result = run_with(turnstile=canonical_missing)
        self.assertFalse(result["checks"]["turnstile_widget_canonical_host"])
        self.assertTrue(result["checks"]["turnstile_hostname_capacity"])

        duplicate_domains = turnstile_results()
        duplicate_domains[
            (
                f"/accounts/{ACCOUNT_ID}/challenges/widgets/{TURNSTILE_SITE_KEY}",
                (),
            )
        ]["domains"] = ["apertures.online", "APERTURES.ONLINE"]
        result = run_with(turnstile=duplicate_domains)
        self.assertFalse(result["checks"]["turnstile_hostname_capacity"])
        self.assertTrue(result["checks"]["turnstile_widget_canonical_host"])

    def test_duplicate_wildcard_or_exclusion_route_is_not_accepted(self):
        for duplicate in (
            {
                "id": "duplicate-wildcard",
                "pattern": "*/*",
                "script": "aperture-production-geo-edge",
            },
            {"id": "duplicate-exclusion", "pattern": "origin.apertures.online/*"},
        ):
            with self.subTest(pattern=duplicate["pattern"]):
                topology = topology_results()
                topology[(f"/zones/{ZONE_ID}/workers/routes", ())].append(duplicate)
                result = run_with(topology)
                expected = (
                    "wildcard_geo_route"
                    if duplicate["pattern"] == "*/*"
                    else "origin_route_excluded"
                )
                self.assertFalse(result["checks"][expected])

    def test_preflight_does_not_require_the_feature_to_be_enabled_locally(self):
        inputs = values() | {
            "CUSTOM_DOMAINS_ENABLED": "false",
            "CUSTOM_DOMAIN_INFRASTRUCTURE_READY": "false",
        }

        def factory(token, _timeout):
            if token == PREFLIGHT_TOKEN:
                return FakeClient(topology_results())
            if token == RUNTIME_TOKEN:
                return FakeClient(runtime_results())
            return FakeClient(turnstile_results())

        status, result = preflight.execute(inputs, client_factory=factory)
        self.assertEqual(status, 0)
        self.assertTrue(result["ready"])

    def test_invalid_inputs_return_stable_secret_free_failure(self):
        cases = (
            ("CLOUDFLARE_CUSTOM_DOMAIN_PREFLIGHT_API_TOKEN", "DUMMY_TOKEN"),
            ("CLOUDFLARE_CUSTOM_HOSTNAMES_API_TOKEN", "DUMMY_TOKEN"),
            ("CLOUDFLARE_TURNSTILE_API_TOKEN", "DUMMY_TOKEN"),
            ("CLOUDFLARE_ZONE_ID", "invalid"),
            ("CUSTOM_DOMAIN_FALLBACK_ORIGIN", "other.apertures.online"),
            ("STORAGE_HOSTNAME", "origin.apertures.online"),
            ("CLOUDFLARE_GEO_EDGE_SCRIPT_NAME", "Invalid Script"),
            ("TURNSTILE_HOSTNAME_LIMIT", "11"),
            ("CUSTOM_DOMAIN_MAX_PER_SITE", "10"),
        )
        for label, replacement in cases:
            with self.subTest(label=label):
                inputs = values()
                inputs[label] = replacement
                status, result = preflight.execute(inputs)
                self.assertEqual(status, 1)
                self.assertFalse(result["ready"])
                self.assertTrue(result["error"])
                self.assertNotIn(PREFLIGHT_TOKEN, json.dumps(result))
                self.assertNotIn(RUNTIME_TOKEN, json.dumps(result))
                self.assertNotIn(TURNSTILE_TOKEN, json.dumps(result))

        inputs = values()
        inputs["CLOUDFLARE_CUSTOM_HOSTNAMES_API_TOKEN"] = PREFLIGHT_TOKEN
        status, result = preflight.execute(inputs)
        self.assertEqual(status, 1)
        self.assertEqual(result["error"], "credential_separation_invalid")

        inputs = values()
        inputs["CLOUDFLARE_TURNSTILE_API_TOKEN"] = RUNTIME_TOKEN
        status, result = preflight.execute(inputs)
        self.assertEqual(status, 1)
        self.assertEqual(result["error"], "credential_separation_invalid")

        inputs = values() | {"CLOUDFLARE_API_TOKEN": PREFLIGHT_TOKEN}
        status, result = preflight.execute(inputs)
        self.assertEqual(status, 1)
        self.assertEqual(result["error"], "credential_separation_invalid")

    def test_any_api_token_failure_returns_stable_secret_free_failure(self):
        topology_failure = topology_results()
        topology_failure[
            (f"/zones/{ZONE_ID}/custom_hostnames/fallback_origin", ())
        ] = preflight.CloudflareApiError("cloudflare_api_unauthorized")
        runtime_failure = runtime_results()
        runtime_failure[
            (
                f"/zones/{ZONE_ID}/custom_hostnames",
                (("page", "1"), ("per_page", "5")),
            )
        ] = preflight.CloudflareApiError("cloudflare_api_unauthorized")
        turnstile_failure = turnstile_results()
        turnstile_failure[
            (
                f"/accounts/{ACCOUNT_ID}/challenges/widgets/{TURNSTILE_SITE_KEY}",
                (),
            )
        ] = preflight.CloudflareApiError("cloudflare_api_unauthorized")

        for failing_token in (PREFLIGHT_TOKEN, RUNTIME_TOKEN, TURNSTILE_TOKEN):
            with self.subTest(token=failing_token):

                def factory(token, _timeout):
                    if token == PREFLIGHT_TOKEN:
                        return FakeClient(
                            topology_failure
                            if failing_token == PREFLIGHT_TOKEN
                            else topology_results()
                        )
                    if token == RUNTIME_TOKEN:
                        return FakeClient(
                            runtime_failure
                            if failing_token == RUNTIME_TOKEN
                            else runtime_results()
                        )
                    return FakeClient(
                        turnstile_failure
                        if failing_token == TURNSTILE_TOKEN
                        else turnstile_results()
                    )

                status, result = preflight.execute(values(), client_factory=factory)
                self.assertEqual(status, 1)
                self.assertEqual(result["error"], "cloudflare_api_unauthorized")
                self.assertFalse(result["ready"])
                self.assertNotIn(failing_token, json.dumps(result))

    def test_captcha_disabled_does_not_require_or_call_turnstile(self):
        inputs = values() | {
            "CAPTCHA_REQUIRED": "false",
            "CLOUDFLARE_TURNSTILE_API_TOKEN": "",
            "NEXT_PUBLIC_TURNSTILE_SITE_KEY": "",
            "TURNSTILE_HOSTNAME_LIMIT": "",
        }
        seen_tokens = []

        def factory(token, _timeout):
            seen_tokens.append(token)
            return FakeClient(
                topology_results() if token == PREFLIGHT_TOKEN else runtime_results()
            )

        status, result = preflight.execute(inputs, client_factory=factory)
        self.assertEqual(status, 0)
        self.assertTrue(result["ready"])
        self.assertEqual(seen_tokens, [PREFLIGHT_TOKEN, RUNTIME_TOKEN])

    def test_http_client_is_get_only_and_validates_the_cloudflare_envelope(self):
        captured = {}

        def opener(request, *, timeout):
            captured["method"] = request.get_method()
            captured["authorization"] = request.get_header("Authorization")
            captured["timeout"] = timeout
            return FakeResponse(json.dumps({"success": True, "result": []}).encode())

        client = preflight.CloudflareReadClient(PREFLIGHT_TOKEN, 8, opener=opener)
        self.assertEqual(client.get(f"/zones/{ZONE_ID}/workers/routes"), [])
        self.assertEqual(captured["method"], "GET")
        self.assertEqual(captured["authorization"], f"Bearer {PREFLIGHT_TOKEN}")
        self.assertEqual(captured["timeout"], 8)

        unavailable = preflight.CloudflareReadClient(
            PREFLIGHT_TOKEN,
            8,
            opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline")),
        )
        with self.assertRaisesRegex(preflight.CloudflareApiError, "Cloudflare read failed"):
            unavailable.get(f"/zones/{ZONE_ID}/workers/routes")

    def test_main_prints_one_stable_json_record_without_exception_details(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = preflight.main(["--input", "missing-owner-env"])
        self.assertEqual(status, 1)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["error"], "configuration_invalid")
        self.assertEqual(set(payload["checks"]), set(preflight.CHECK_NAMES))


if __name__ == "__main__":
    unittest.main()
