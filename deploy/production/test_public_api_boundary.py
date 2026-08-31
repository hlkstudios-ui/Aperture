import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parents[1]


class PublicApiBoundaryTests(unittest.TestCase):
    def test_hostinger_has_an_explicit_api_allowlist(self):
        caddy = (ROOT / "hostinger" / "Caddyfile").read_text()
        self.assertNotIn("handle_path /api/*", caddy)
        self.assertIn("path /api/ready /api/billing/stripe/webhook", caddy)
        self.assertIn("handle /api/edge-media/*", caddy)
        self.assertIn("{$CDN_ORIGIN_SECRET}", caddy)
        self.assertRegex(caddy, r"handle /api/\* \{\s+respond 404\s+\}")
        self.assertIn("handle /api/gateway/*", caddy)
        self.assertIn("handle /api/catalog/*", caddy)
        self.assertIn("handle /api/site/*", caddy)

        compose = (ROOT / "hostinger" / "compose.yml").read_text()
        self.assertIn("CDN_ORIGIN_SECRET: ${CDN_ORIGIN_SECRET}", compose)
        self.assertNotIn("SESSION_COOKIE_DOMAIN", compose)

    def test_digitalocean_routes_only_external_api_exceptions_to_fastapi(self):
        template = (ROOT / "digitalocean" / "app.template.yaml").read_text()
        self.assertNotIn("SESSION_COOKIE_DOMAIN", template)
        document = yaml.safe_load(template)
        rules = document["ingress"]["rules"]

        api_rules = [rule for rule in rules if rule["component"]["name"] == "api"]
        self.assertEqual(
            {
                (next(iter(rule["match"]["path"])), next(iter(rule["match"]["path"].values())))
                for rule in api_rules
            },
            {
                ("exact", "/api/billing/stripe/webhook"),
                ("prefix", "/api/edge-media"),
                ("exact", "/api/ready"),
            },
        )
        self.assertEqual(
            {rule["component"]["rewrite"] for rule in api_rules},
            {"/billing/stripe/webhook", "/edge-media", "/ready"},
        )
        self.assertFalse(
            any(rule["match"]["path"].get("prefix") == "/api" for rule in api_rules),
            "a public FastAPI catch-all bypasses the same-origin gateway",
        )

        web = next(service for service in document["services"] if service["name"] == "web")
        self.assertIn(
            {
                "key": "API_ORIGIN",
                "value": "http://api:8000",
                "scope": "RUN_AND_BUILD_TIME",
            },
            web["envs"],
        )

    def test_private_studio_and_smoke_use_the_gateway_boundary(self):
        private_caddy = (ROOT / "private-studio" / "Caddyfile").read_text()
        self.assertIn("/api/gateway/admin/*", private_caddy)
        self.assertNotIn(" /api/admin ", private_caddy)

        smoke = (ROOT / "public_edge_smoke.py").read_text()
        example = (ROOT / "public-edge.example.env").read_text()
        self.assertNotIn("SMOKE_API_ORIGIN", smoke)
        self.assertNotIn("SMOKE_API_ORIGIN", example)
        self.assertIn('"/api/gateway/auth/oauth/providers"', smoke)
        self.assertIn('"/api/account"', smoke)
        self.assertIn('("billing", "edge-media", "metrics", "ready")', smoke)

        next_config = (PROJECT_ROOT / "apps" / "web" / "next.config.ts").read_text()
        gateway = (
            PROJECT_ROOT
            / "apps"
            / "web"
            / "app"
            / "api"
            / "gateway"
            / "[[...path]]"
            / "route.ts"
        ).read_text()
        policy = (
            PROJECT_ROOT / "apps" / "web" / "app" / "lib" / "api-gateway-policy.ts"
        ).read_text()

        self.assertNotIn('source: "/api/gateway/:path*"', next_config)
        self.assertNotIn("NEXT_PUBLIC_API_ORIGIN", next_config)
        self.assertIn("isBrowserApiPrefix(path[0])", gateway)
        self.assertIn('name === "x-aperture-studio-edge"', gateway)
        self.assertIn('redirect: "manual"', gateway)
        self.assertIn('"private, no-store, max-age=0, must-revalidate"', gateway)
        self.assertIn('[...vary, "Cookie"]', gateway)
        for prefix in ("account", "admin", "auth", "playback", "scene-intelligence"):
            self.assertIn(f'  "{prefix}",', policy)
        for prefix in ("billing", "edge-media", "health", "metrics", "operations", "ready"):
            self.assertNotIn(f'  "{prefix}",', policy)


if __name__ == "__main__":
    unittest.main()
