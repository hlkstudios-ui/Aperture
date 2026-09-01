import unittest
from pathlib import Path

from validate_config import EXAMPLE_INPUT, load, require_hostinger_api_token, validate

COMPACT_MEMORY_LIMITS = {
    "POSTGRES_MEMORY_LIMIT": "1280m",
    "REDIS_MEMORY_LIMIT": "256m",
    "MINIO_MEMORY_LIMIT": "1280m",
    "CLAMAV_MEMORY_LIMIT": "1280m",
    "API_MEMORY_LIMIT": "768m",
    "MEDIA_WORKER_MEMORY_LIMIT": "2g",
    "SCENE_WORKER_MEMORY_LIMIT": "1g",
    "WEB_MEMORY_LIMIT": "768m",
    "CADDY_MEMORY_LIMIT": "256m",
}


def compact_values(values: dict[str, str]) -> dict[str, str]:
    values["HOSTINGER_VPS_PROFILE"] = "compact"
    values["HOSTINGER_VPS_MEMORY_GB"] = "16"
    values["HOSTINGER_VPS_VCPU"] = "4"
    values.update(COMPACT_MEMORY_LIMITS)
    return values


def enable_custom_domains(values: dict[str, str]) -> dict[str, str]:
    values.update(
        {
            "CUSTOM_DOMAINS_ENABLED": "true",
            "CUSTOM_DOMAIN_INFRASTRUCTURE_READY": "true",
            "CUSTOM_DOMAIN_PROVIDER": "cloudflare",
            "CUSTOM_DOMAIN_CNAME_TARGET": "customers.apertures.online",
            "CUSTOM_DOMAIN_MAX_PER_SITE": "9",
            "ORIGIN_HOSTNAME": "origin.apertures.online",
            "CUSTOM_DOMAIN_FALLBACK_ORIGIN": "origin.apertures.online",
            "CLOUDFLARE_CUSTOM_HOSTNAMES_API_TOKEN": (
                "cloudflare-custom-hostnames-runtime-token"
            ),
            "CLOUDFLARE_TURNSTILE_API_TOKEN": (
                "cloudflare-turnstile-runtime-token"
            ),
            "NEXT_PUBLIC_TURNSTILE_SITE_KEY": "0x4AAAA-aperture-widget-key",
            "TURNSTILE_HOSTNAME_LIMIT": "10",
            "CLOUDFLARE_ZONE_ID": "a" * 32,
            "CLOUDFLARE_ACCOUNT_ID": "b" * 32,
            "CLOUDFLARE_SITE_DOMAINS_KV_NAMESPACE_ID": "c" * 32,
        }
    )
    return values


def deployable_values() -> dict[str, str]:
    values = {
        key: value.replace("DUMMY", "production").replace("dummy", "production")
        for key, value in load(EXAMPLE_INPUT).items()
    }
    values["API_IMAGE"] = "registry.example/aperture-api@sha256:" + "1" * 64
    values["MEDIA_WORKER_IMAGE"] = (
        "registry.example/aperture-media-worker@sha256:" + "4" * 64
    )
    values["WEB_IMAGE"] = "registry.example/aperture-web@sha256:" + "2" * 64
    values["BACKUP_IMAGE"] = "registry.example/aperture-backup@sha256:" + "3" * 64
    values["CADDY_IMAGE"] = "registry.example/aperture-caddy@sha256:" + "5" * 64
    values["STORAGE_IMAGE"] = (
        "registry.example/aperture-storage@sha256:" + "6" * 64
    )
    values["NODE_EXPORTER_IMAGE"] = (
        "registry.example/aperture-node-exporter@sha256:" + "7" * 64
    )
    values["BLACKBOX_IMAGE"] = (
        "registry.example/aperture-blackbox@sha256:" + "8" * 64
    )
    values["HOSTINGER_VPS_IP"] = "8.8.8.8"
    values["HOSTINGER_VPS_IPV6"] = "2606:4700:4700::1111"
    values["POLICY_REQUIRE_APPROVED"] = "true"
    return values


class HostingerConfigTests(unittest.TestCase):
    def test_dummy_file_is_structurally_valid(self):
        validate(load(EXAMPLE_INPUT), deploy=False)

    def test_dummy_file_cannot_deploy(self):
        with self.assertRaisesRegex(ValueError, "replace dummy labels"):
            validate(load(EXAMPLE_INPUT), deploy=True)

    def test_public_hosts_must_be_distinct(self):
        values = load(EXAMPLE_INPUT)
        values["STORAGE_HOSTNAME"] = values["WEB_HOSTNAME"]
        with self.assertRaisesRegex(ValueError, "distinct"):
            validate(values, deploy=False)

    def test_public_bind_addresses_require_the_right_ip_families(self):
        invalid = (
            ("HOSTINGER_VPS_IP", "2606:4700:4700::1111", "IPv4"),
            ("HOSTINGER_VPS_IPV6", "8.8.8.8", "IPv6"),
            ("HOSTINGER_VPS_IP", "8.8.8.8/32", "IPv4"),
            ("HOSTINGER_VPS_IPV6", "[2606:4700:4700::1111]", "IPv6"),
        )
        for label, value, family in invalid:
            with self.subTest(label=label, value=value):
                values = load(EXAMPLE_INPUT)
                values[label] = value
                with self.assertRaisesRegex(ValueError, family):
                    validate(values, deploy=False)

    def test_deploy_requires_globally_routable_public_bind_addresses(self):
        for label, value in (
            ("HOSTINGER_VPS_IP", "127.0.0.1"),
            ("HOSTINGER_VPS_IP", "203.0.113.10"),
            ("HOSTINGER_VPS_IPV6", "::1"),
            ("HOSTINGER_VPS_IPV6", "2001:db8::10"),
        ):
            with self.subTest(label=label):
                values = deployable_values()
                values[label] = value
                with self.assertRaisesRegex(ValueError, f"{label} must be a public"):
                    validate(values, deploy=True)

    def test_caddy_binds_only_the_configured_public_addresses(self):
        compose = (Path(__file__).resolve().parent / "compose.yml").read_text()
        caddy = compose.split("  caddy:", 1)[1].split("  maintenance:", 1)[0]
        self.assertEqual(caddy.count("host_ip: ${HOSTINGER_VPS_IP}\n"), 3)
        self.assertEqual(caddy.count("host_ip: ${HOSTINGER_VPS_IPV6}\n"), 3)
        self.assertNotIn('ports: ["80:8080"', caddy)

    def test_backup_and_replica_endpoints_must_be_https_origins(self):
        invalid_endpoints = (
            "http://s3.example.com",
            "https:///missing-host",
            "https://s3.example.com/bucket",
            "https://s3.example.com?bucket=value",
            "https://s3.example.com#fragment",
            "https://access:secret@s3.example.com",
            "https://s3.example.com:not-a-port",
        )
        for label in ("BACKUP_S3_ENDPOINT", "REPLICA_S3_ENDPOINT"):
            for endpoint in invalid_endpoints:
                with self.subTest(label=label, endpoint=endpoint):
                    values = load(EXAMPLE_INPUT)
                    values[label] = endpoint
                    with self.assertRaisesRegex(ValueError, f"{label}.*HTTPS origin"):
                        validate(values, deploy=False)

        values = load(EXAMPLE_INPUT)
        values["BACKUP_S3_ENDPOINT"] = "https://s3.us-east-2.amazonaws.com"
        values["REPLICA_S3_ENDPOINT"] = "https://s3.us-east-2.amazonaws.com/"
        validate(values, deploy=False)

    def test_memory_profile_reserves_host_headroom(self):
        values = load(EXAMPLE_INPUT)
        values["MEDIA_WORKER_MEMORY_LIMIT"] = "16g"
        with self.assertRaisesRegex(ValueError, "20% host headroom"):
            validate(values, deploy=False)

    def test_selected_boston_2_region_is_required(self):
        values = load(EXAMPLE_INPUT)
        values["HOSTINGER_VPS_REGION"] = "New_York"
        with self.assertRaisesRegex(ValueError, "Boston_2"):
            validate(values, deploy=False)

    def test_full_profile_capacity_floor_is_required(self):
        values = load(EXAMPLE_INPUT)
        values["HOSTINGER_VPS_MEMORY_GB"] = "31"
        with self.assertRaisesRegex(ValueError, "full profile floor"):
            validate(values, deploy=False)

        values = load(EXAMPLE_INPUT)
        values["HOSTINGER_VPS_VCPU"] = "7"
        with self.assertRaisesRegex(ValueError, "full profile floor"):
            validate(values, deploy=False)

    def test_compact_profile_is_a_valid_deploy_configuration(self):
        validate(compact_values(deployable_values()), deploy=True)

    def test_production_compose_explicitly_disables_payments(self):
        compose = (Path(__file__).resolve().parent / "compose.yml").read_text()
        shared_environment = compose.split("x-api-environment:", 1)[1].split(
            "x-api-service:", 1
        )[0]
        self.assertIn("BILLING_PROVIDER: disabled", shared_environment)
        self.assertNotIn("BILLING_PROVIDER: stripe", shared_environment)
        self.assertIn('STRIPE_SECRET_KEY: ""', shared_environment)
        self.assertIn('STRIPE_WEBHOOK_SECRET: ""', shared_environment)
        self.assertNotIn("${STRIPE_SECRET_KEY}", shared_environment)
        self.assertNotIn("${STRIPE_WEBHOOK_SECRET}", shared_environment)

        values = deployable_values()
        values["STRIPE_SECRET_KEY"] = ""
        values["STRIPE_WEBHOOK_SECRET"] = ""
        validate(values, deploy=True)

    def test_caddy_keeps_only_its_required_file_capability(self):
        compose = (Path(__file__).resolve().parent / "compose.yml").read_text()
        caddy = compose.split("  caddy:", 1)[1].split("  maintenance:", 1)[0]
        self.assertIn("cap_drop: [ALL]", caddy)
        self.assertNotIn("cap_add:", caddy)

    def test_caddy_never_terminates_customer_domain_tls(self):
        caddyfile = (Path(__file__).resolve().parent / "Caddyfile").read_text()
        self.assertIn("{$WEB_HOSTNAME}, {$ORIGIN_HOSTNAME} {", caddyfile)
        self.assertIn("{$STORAGE_HOSTNAME} {", caddyfile)
        self.assertNotIn("CUSTOM_DOMAIN", caddyfile)
        self.assertNotRegex(caddyfile, r"(?m)^\s*\*\.")

    def test_custom_domain_edge_secret_reaches_web_and_api_but_not_caddy(self):
        compose = (Path(__file__).resolve().parent / "compose.yml").read_text()
        shared_api = compose.split("x-api-environment:", 1)[1].split(
            "x-api-service:", 1
        )[0]
        api = compose.split("  api:", 1)[1].split("  media-worker:", 1)[0]
        web = compose.split("  web:", 1)[1].split("  caddy:", 1)[0]
        caddy = compose.split("  caddy:", 1)[1].split("  maintenance:", 1)[0]
        reference = "CUSTOM_DOMAIN_EDGE_SECRET: ${CUSTOM_DOMAIN_EDGE_SECRET}"
        self.assertNotIn(reference, shared_api)
        self.assertIn(reference, api)
        self.assertIn(reference, web)
        self.assertNotIn(reference, caddy)

    def test_custom_domain_edge_secret_must_be_high_entropy_for_deploy(self):
        values = deployable_values()
        values["CUSTOM_DOMAIN_EDGE_SECRET"] = "too-short"
        with self.assertRaisesRegex(ValueError, "CUSTOM_DOMAIN_EDGE_SECRET"):
            validate(values, deploy=True)

    def test_custom_domains_remain_optional_and_disabled_by_default(self):
        values = deployable_values()
        self.assertEqual(values["CUSTOM_DOMAINS_ENABLED"], "false")
        self.assertEqual(values["CUSTOM_DOMAIN_INFRASTRUCTURE_READY"], "false")
        self.assertEqual(values["CUSTOM_DOMAIN_PROVIDER"], "disabled")
        validate(values, deploy=True)

    def test_enabled_custom_domains_require_complete_cloudflare_configuration(self):
        values = deployable_values()
        values["CUSTOM_DOMAINS_ENABLED"] = "true"
        with self.assertRaisesRegex(ValueError, "requires CUSTOM_DOMAIN_PROVIDER"):
            validate(values, deploy=True)

        values["CUSTOM_DOMAIN_PROVIDER"] = "cloudflare"
        with self.assertRaisesRegex(ValueError, "INFRASTRUCTURE_READY=true"):
            validate(values, deploy=True)

        values["CUSTOM_DOMAIN_INFRASTRUCTURE_READY"] = "true"
        values["CLOUDFLARE_TURNSTILE_API_TOKEN"] = (
            "cloudflare-turnstile-runtime-token"
        )
        values["NEXT_PUBLIC_TURNSTILE_SITE_KEY"] = (
            "0x4AAAA-aperture-widget-key"
        )
        with self.assertRaisesRegex(ValueError, "Cloudflare custom domains require"):
            validate(values, deploy=True)

        validate(enable_custom_domains(values), deploy=True)

    def test_custom_domain_cloudflare_identifiers_and_target_are_validated(self):
        for label in (
            "CLOUDFLARE_ZONE_ID",
            "CLOUDFLARE_ACCOUNT_ID",
            "CLOUDFLARE_SITE_DOMAINS_KV_NAMESPACE_ID",
        ):
            with self.subTest(label=label):
                values = enable_custom_domains(deployable_values())
                values[label] = "not-an-identifier"
                with self.assertRaisesRegex(ValueError, label):
                    validate(values, deploy=True)

        values = enable_custom_domains(deployable_values())
        values["CUSTOM_DOMAIN_CNAME_TARGET"] = "https://customers.apertures.online"
        with self.assertRaisesRegex(ValueError, "CNAME_TARGET"):
            validate(values, deploy=True)

        values = enable_custom_domains(deployable_values())
        values["CUSTOM_DOMAIN_FALLBACK_ORIGIN"] = "other.apertures.online"
        with self.assertRaisesRegex(ValueError, "FALLBACK_ORIGIN"):
            validate(values, deploy=True)

        values = enable_custom_domains(deployable_values())
        values["CLOUDFLARE_CDN_SCRIPT_NAME"] = values[
            "CLOUDFLARE_GEO_EDGE_SCRIPT_NAME"
        ]
        with self.assertRaisesRegex(ValueError, "script names"):
            validate(values, deploy=True)

    def test_enabled_custom_domains_require_readiness_attestation(self):
        values = enable_custom_domains(deployable_values())
        values["CUSTOM_DOMAIN_INFRASTRUCTURE_READY"] = "false"
        with self.assertRaisesRegex(ValueError, "INFRASTRUCTURE_READY=true"):
            validate(values, deploy=True)

        values = enable_custom_domains(deployable_values())
        values["CUSTOM_DOMAIN_INFRASTRUCTURE_READY"] = "invalid"
        with self.assertRaisesRegex(ValueError, "must be true or false"):
            validate(values, deploy=True)

    def test_turnstile_lifecycle_is_required_only_for_captcha_custom_domains(self):
        values = enable_custom_domains(deployable_values())
        values["CLOUDFLARE_TURNSTILE_API_TOKEN"] = ""
        with self.assertRaisesRegex(ValueError, "TURNSTILE_API_TOKEN"):
            validate(values, deploy=True)

        values = enable_custom_domains(deployable_values())
        values["NEXT_PUBLIC_TURNSTILE_SITE_KEY"] = "invalid site key"
        with self.assertRaisesRegex(ValueError, "SITE_KEY is malformed"):
            validate(values, deploy=True)

        values = enable_custom_domains(deployable_values())
        values["CLOUDFLARE_TURNSTILE_API_TOKEN"] = values[
            "CLOUDFLARE_CUSTOM_HOSTNAMES_API_TOKEN"
        ]
        with self.assertRaisesRegex(ValueError, "distinct tokens"):
            validate(values, deploy=True)

        for limit in ("1", "11", "not-a-number"):
            with self.subTest(limit=limit):
                values = enable_custom_domains(deployable_values())
                values["TURNSTILE_HOSTNAME_LIMIT"] = limit
                with self.assertRaisesRegex(ValueError, "between 2 and 10"):
                    validate(values, deploy=True)

        values = enable_custom_domains(deployable_values())
        values["CUSTOM_DOMAIN_MAX_PER_SITE"] = "10"
        with self.assertRaisesRegex(ValueError, "reserve one Turnstile"):
            validate(values, deploy=True)

        values = enable_custom_domains(deployable_values())
        values["CAPTCHA_REQUIRED"] = "false"
        values["CLOUDFLARE_TURNSTILE_API_TOKEN"] = "DUMMY_UNUSED_TOKEN"
        values["TURNSTILE_HOSTNAME_LIMIT"] = ""
        validate(values, deploy=True)

    def test_cloudflare_provider_credentials_are_api_only(self):
        compose = (Path(__file__).resolve().parent / "compose.yml").read_text()
        api = compose.split("  api:", 1)[1].split("  media-worker:", 1)[0]
        web = compose.split("  web:", 1)[1].split("  caddy:", 1)[0]
        shared = compose.split("x-api-environment:", 1)[1].split(
            "x-api-service:", 1
        )[0]
        caddy = compose.split("  caddy:", 1)[1].split("  maintenance:", 1)[0]
        for label in (
            "CLOUDFLARE_CUSTOM_HOSTNAMES_API_TOKEN",
            "CLOUDFLARE_ZONE_ID",
            "CLOUDFLARE_ACCOUNT_ID",
            "CLOUDFLARE_SITE_DOMAINS_KV_NAMESPACE_ID",
            "CUSTOM_DOMAIN_INFRASTRUCTURE_READY",
        ):
            self.assertIn(label, api)
            self.assertNotIn(label, web)
            self.assertNotIn(label, shared)
            self.assertNotIn(label, caddy)
        self.assertNotIn("CLOUDFLARE_API_TOKEN:", compose)
        self.assertNotIn("CLOUDFLARE_CUSTOM_DOMAIN_PREFLIGHT_API_TOKEN", compose)

    def test_inactive_stripe_placeholders_do_not_block_non_commercial_launch(self):
        values = deployable_values()
        values["STRIPE_SECRET_KEY"] = "sk_test_DUMMY_NO_NETWORK_CALLS"
        values["STRIPE_WEBHOOK_SECRET"] = "whsec_DUMMY_UNUSED"
        validate(values, deploy=True)

    def test_post_provision_deploy_does_not_require_an_active_hostinger_token(self):
        for token in ("", "DUMMY_REVOKED_HOSTINGER_API_TOKEN", "revoked-token-value"):
            with self.subTest(token=token):
                values = deployable_values()
                values["HOSTINGER_API_TOKEN"] = token
                validate(values, deploy=True)

    def test_hostinger_api_operations_require_a_local_non_placeholder_token(self):
        for token in ("", "DUMMY_SHORT_LIVED_HOSTINGER_API_TOKEN", "   "):
            with self.subTest(token=token):
                values = deployable_values()
                values["HOSTINGER_API_TOKEN"] = token
                with self.assertRaisesRegex(
                    ValueError, "required for Hostinger API operations"
                ):
                    require_hostinger_api_token(values)

        values = deployable_values()
        values["HOSTINGER_API_TOKEN"] = "short-lived-local-token"
        require_hostinger_api_token(values)

    def test_explicit_hostinger_api_validation_is_fail_closed(self):
        values = deployable_values()
        values["HOSTINGER_API_TOKEN"] = ""
        with self.assertRaisesRegex(
            ValueError, "required for Hostinger API operations"
        ):
            validate(values, deploy=True, require_hostinger_token=True)

    def test_compact_profile_keeps_capacity_and_headroom_guards(self):
        values = compact_values(load(EXAMPLE_INPUT))
        values["HOSTINGER_VPS_MEMORY_GB"] = "15"
        with self.assertRaisesRegex(ValueError, "compact profile floor"):
            validate(values, deploy=False)

        values = compact_values(load(EXAMPLE_INPUT))
        values["HOSTINGER_VPS_VCPU"] = "3"
        with self.assertRaisesRegex(ValueError, "compact profile floor"):
            validate(values, deploy=False)

        values = compact_values(load(EXAMPLE_INPUT))
        values["MEDIA_WORKER_MEMORY_LIMIT"] = "8g"
        with self.assertRaisesRegex(ValueError, "35% host headroom"):
            validate(values, deploy=False)

    def test_unknown_capacity_profile_is_rejected(self):
        values = load(EXAMPLE_INPUT)
        values["HOSTINGER_VPS_PROFILE"] = "custom"
        with self.assertRaisesRegex(ValueError, "compact or full"):
            validate(values, deploy=False)

    def test_mutable_image_tag_is_rejected(self):
        values = load(EXAMPLE_INPUT)
        values["API_IMAGE"] = "registry.example/aperture-api:latest"
        with self.assertRaisesRegex(ValueError, "immutable registry digest"):
            validate(values, deploy=False)

    def test_media_worker_image_is_immutable_and_distinct_from_api(self):
        values = load(EXAMPLE_INPUT)
        values["MEDIA_WORKER_IMAGE"] = "registry.example/aperture-media-worker:release"
        with self.assertRaisesRegex(ValueError, "immutable registry digest"):
            validate(values, deploy=False)

        values = load(EXAMPLE_INPUT)
        values["MEDIA_WORKER_IMAGE"] = (
            "another.registry.example/aperture-media-worker@sha256:" + "0" * 64
        )
        with self.assertRaisesRegex(ValueError, "image digests must be distinct"):
            validate(values, deploy=False)

    def test_caddy_and_storage_images_are_immutable_and_distinct(self):
        values = load(EXAMPLE_INPUT)
        values["CADDY_IMAGE"] = "registry.example/aperture-caddy:release"
        with self.assertRaisesRegex(ValueError, "immutable registry digest"):
            validate(values, deploy=False)

        values = load(EXAMPLE_INPUT)
        values["STORAGE_IMAGE"] = values["CADDY_IMAGE"]
        with self.assertRaisesRegex(ValueError, "image digests must be distinct"):
            validate(values, deploy=False)

    def test_exporter_images_are_immutable_and_distinct(self):
        values = load(EXAMPLE_INPUT)
        values["BLACKBOX_IMAGE"] = "registry.example/aperture-blackbox:release"
        with self.assertRaisesRegex(ValueError, "immutable registry digest"):
            validate(values, deploy=False)

        values = load(EXAMPLE_INPUT)
        values["NODE_EXPORTER_IMAGE"] = values["STORAGE_IMAGE"]
        with self.assertRaisesRegex(ValueError, "image digests must be distinct"):
            validate(values, deploy=False)

    def test_ffmpeg_is_isolated_to_the_audited_media_worker_image(self):
        project_root = Path(__file__).resolve().parents[3]
        api_dockerfile = (project_root / "apps/api/Dockerfile").read_text()
        media_dockerfile = (
            project_root / "apps/api/Dockerfile.media-worker"
        ).read_text()

        for dockerfile in (api_dockerfile, media_dockerfile):
            self.assertTrue(
                dockerfile.startswith("FROM python:3.12.14-alpine3.24 AS runtime\n")
            )
            self.assertLess(
                dockerfile.index("apk upgrade --no-cache"), dockerfile.index("apk add")
            )
            self.assertIn("USER aperture", dockerfile)
        self.assertNotIn("ffmpeg", api_dockerfile.lower())
        self.assertNotIn("ffprobe", api_dockerfile.lower())
        self.assertIn("apk add --no-cache ca-certificates ffmpeg", media_dockerfile)
        self.assertIn('["python", "-m", "app.media_worker"]', media_dockerfile)

    def test_compose_uses_worker_image_only_for_media_processing(self):
        compose = (Path(__file__).resolve().parent / "compose.yml").read_text()
        media_worker = compose.split("  media-worker:", 1)[1].split(
            "  scene-worker:", 1
        )[0]
        self.assertIn("image: ${MEDIA_WORKER_IMAGE}", media_worker)
        self.assertNotIn("MEDIA_WORKER_IMAGE", compose.split("  media-worker:", 1)[0])
        self.assertNotIn("MEDIA_WORKER_IMAGE", compose.split("  scene-worker:", 1)[1])

    def test_captcha_requires_both_public_and_private_turnstile_keys(self):
        values = load(EXAMPLE_INPUT)
        values["NEXT_PUBLIC_TURNSTILE_SITE_KEY"] = ""
        with self.assertRaisesRegex(ValueError, "requires both"):
            validate(values, deploy=False)

        values["CAPTCHA_REQUIRED"] = "false"
        values["TURNSTILE_SECRET_KEY"] = ""
        validate(values, deploy=False)

    def test_release_build_reads_turnstile_key_only_when_captcha_is_required(self):
        script = (Path(__file__).resolve().parent / "build_release.sh").read_text()
        before_captcha_case, captcha_case = script.split(
            'case "$CAPTCHA_REQUIRED" in', 1
        )
        enabled_branch, _disabled_branch = captcha_case.split("  false)", 1)

        self.assertIn("TURNSTILE_SITE_KEY=", before_captcha_case)
        self.assertNotIn("NEXT_PUBLIC_TURNSTILE_SITE_KEY", before_captcha_case)
        self.assertIn(
            'TURNSTILE_SITE_KEY=$(value "$CREDENTIALS" NEXT_PUBLIC_TURNSTILE_SITE_KEY)',
            enabled_branch,
        )

    def test_release_build_does_not_read_the_hostinger_api_token(self):
        script = (Path(__file__).resolve().parent / "build_release.sh").read_text()
        self.assertNotIn("HOSTINGER_API_TOKEN", script)

    def test_release_build_pushes_and_pins_all_eight_artifacts(self):
        script = (Path(__file__).resolve().parent / "build_release.sh").read_text()
        # Four application images are always rebuilt. The fifth build command is
        # the guarded infrastructure fallback; routine CI carbon-copies four
        # previously accepted digest-pinned platform images instead.
        self.assertEqual(script.count("docker buildx build --platform"), 5)
        self.assertIn("docker buildx imagetools create --tag", script)
        for label in (
            "APERTURE_REUSE_CADDY_IMAGE",
            "APERTURE_REUSE_STORAGE_IMAGE",
            "APERTURE_REUSE_NODE_EXPORTER_IMAGE",
            "APERTURE_REUSE_BLACKBOX_IMAGE",
        ):
            self.assertIn(label, script)
        self.assertIn("apps/api/Dockerfile.media-worker", script)
        self.assertIn('"$BASE_DIR/caddy.Dockerfile"', script)
        self.assertIn('"$BASE_DIR/storage.Dockerfile"', script)
        self.assertIn('"$BASE_DIR/node-exporter.Dockerfile"', script)
        self.assertIn('"$BASE_DIR/blackbox-exporter.Dockerfile"', script)
        self.assertIn(
            'media_worker_tag="$REGISTRY_REPOSITORY/media-worker:$RELEASE_ID"', script
        )
        self.assertIn('caddy_tag="$REGISTRY_REPOSITORY/caddy:$RELEASE_ID"', script)
        self.assertIn(
            'storage_tag="$REGISTRY_REPOSITORY/storage:$RELEASE_ID"', script
        )
        self.assertIn(
            'node_exporter_tag="$REGISTRY_REPOSITORY/node-exporter:$RELEASE_ID"',
            script,
        )
        self.assertIn(
            'blackbox_tag="$REGISTRY_REPOSITORY/blackbox:$RELEASE_ID"', script
        )
        self.assertIn(
            'media_worker_ref="$media_worker_tag@$(digest "$media_worker_tag")"',
            script,
        )
        self.assertIn('caddy_ref="$caddy_tag@$(digest "$caddy_tag")"', script)
        self.assertIn('storage_ref="$storage_tag@$(digest "$storage_tag")"', script)
        self.assertIn(
            'node_exporter_ref="$node_exporter_tag@$(digest "$node_exporter_tag")"',
            script,
        )
        self.assertIn(
            'blackbox_ref="$blackbox_tag@$(digest "$blackbox_tag")"', script
        )
        # Four application builds plus the platform fallback produce fresh
        # provenance/SBOM attestations. Routine platform copies retain the
        # already accepted manifest and registry referrers.
        self.assertEqual(script.count("--provenance=mode=max --sbom=true"), 5)
        self.assertIn('--media-worker "$media_worker_ref"', script)

    def test_compose_uses_release_images_for_edge_storage_and_exporters(self):
        compose = (Path(__file__).resolve().parent / "compose.yml").read_text()
        minio = compose.split("  minio:", 1)[1].split("  minio-init:", 1)[0]
        caddy = compose.split("  caddy:", 1)[1].split("  maintenance:", 1)[0]
        node_exporter = compose.split("  node-exporter:", 1)[1].split(
            "  prometheus:", 1
        )[0]
        blackbox = compose.split("  blackbox:", 1)[1].split("\nnetworks:", 1)[0]

        self.assertIn("image: ${STORAGE_IMAGE}", minio)
        self.assertIn("image: ${CADDY_IMAGE}", caddy)
        self.assertNotIn("minio/minio:", minio)
        self.assertNotIn("image: caddy:", caddy)
        self.assertIn("image: ${NODE_EXPORTER_IMAGE}", node_exporter)
        self.assertIn("image: ${BLACKBOX_IMAGE}", blackbox)
        self.assertNotIn("prom/node-exporter:", node_exporter)
        self.assertNotIn("prom/blackbox-exporter:", blackbox)

    def test_oauth_provider_credentials_are_optional_but_atomic(self):
        values = load(EXAMPLE_INPUT)
        values["OAUTH_GOOGLE_CLIENT_ID"] = "google-client"
        with self.assertRaisesRegex(ValueError, "must be configured together"):
            validate(values, deploy=False)
        values["OAUTH_GOOGLE_CLIENT_SECRET"] = "google-secret"
        validate(values, deploy=False)

    def test_copy_assistant_requires_an_api_key_when_enabled(self):
        values = load(EXAMPLE_INPUT)
        values["BRAND_AI_PROVIDER"] = "openai"
        with self.assertRaisesRegex(ValueError, "requires OPENAI_API_KEY"):
            validate(values, deploy=False)

    def test_unrelated_control_plane_dummy_values_do_not_block_deploy(self):
        values = deployable_values()
        values["HOSTINGER_ROLLBACK_API_IMAGE"] = "DUMMY_ROLLBACK_VALUE"
        values["TAILSCALE_AUTH_KEY"] = "DUMMY_ENROLLMENT_VALUE"
        values["CLOUDFLARE_API_TOKEN"] = "DUMMY_LOCAL_CONTROL_TOKEN"
        validate(values, deploy=True)

    def test_inactive_optional_dummy_credentials_do_not_block_deploy(self):
        values = deployable_values()
        values["CAPTCHA_REQUIRED"] = "false"
        values["NEXT_PUBLIC_TURNSTILE_SITE_KEY"] = "DUMMY_UNUSED_SITE_KEY"
        values["TURNSTILE_SECRET_KEY"] = "DUMMY_UNUSED_SECRET_KEY"
        values["BRAND_AI_PROVIDER"] = "disabled"
        values["OPENAI_API_KEY"] = "DUMMY_UNUSED_OPENAI_KEY"
        validate(values, deploy=True)

    def test_active_optional_dummy_credentials_block_deploy(self):
        values = deployable_values()
        values["CAPTCHA_REQUIRED"] = "true"
        values["NEXT_PUBLIC_TURNSTILE_SITE_KEY"] = "DUMMY_ACTIVE_SITE_KEY"
        values["TURNSTILE_SECRET_KEY"] = "DUMMY_ACTIVE_SECRET_KEY"
        with self.assertRaisesRegex(ValueError, "replace dummy labels"):
            validate(values, deploy=True)

        values = deployable_values()
        values["BRAND_AI_PROVIDER"] = "openai"
        values["OPENAI_API_KEY"] = "DUMMY_ACTIVE_OPENAI_KEY"
        with self.assertRaisesRegex(ValueError, "replace dummy labels"):
            validate(values, deploy=True)

    def test_public_turnstile_key_is_web_only_and_secrets_are_api_only(self):
        compose = (Path(__file__).resolve().parent / "compose.yml").read_text()
        web_environment = compose.split("  web:", 1)[1].split("  caddy:", 1)[0]
        shared_environment = compose.split("x-api-environment:", 1)[1].split(
            "x-api-service:", 1
        )[0]
        api_environment = compose.split("  api:", 1)[1].split("  media-worker:", 1)[0]
        self.assertIn("NEXT_PUBLIC_TURNSTILE_SITE_KEY", web_environment)
        self.assertNotIn("TURNSTILE_SECRET_KEY", web_environment)
        self.assertNotIn("OAUTH_GOOGLE_CLIENT_SECRET", web_environment)
        self.assertNotIn("OPENAI_API_KEY", web_environment)
        self.assertIn("TURNSTILE_SECRET_KEY", api_environment)
        self.assertIn(
            "TURNSTILE_SITE_KEY: ${NEXT_PUBLIC_TURNSTILE_SITE_KEY}", api_environment
        )
        self.assertIn("CLOUDFLARE_TURNSTILE_API_TOKEN", api_environment)
        self.assertIn("TURNSTILE_HOSTNAME_LIMIT", api_environment)
        self.assertIn("OAUTH_GOOGLE_CLIENT_SECRET", api_environment)
        self.assertIn("OPENAI_API_KEY", api_environment)
        self.assertNotIn("TURNSTILE_SECRET_KEY", shared_environment)
        self.assertNotIn("CLOUDFLARE_TURNSTILE_API_TOKEN", web_environment)
        self.assertNotIn("CLOUDFLARE_TURNSTILE_API_TOKEN", shared_environment)
        self.assertNotIn("OAUTH_GOOGLE_CLIENT_SECRET", shared_environment)
        self.assertNotIn("OPENAI_API_KEY", shared_environment)


if __name__ == "__main__":
    unittest.main()
