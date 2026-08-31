"""Static security contract for the main-branch production workflow."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

from deploy.production.hostinger.deploy_release import REQUIRED_BUNDLE_FILES


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "quality.yml"

PINNED_ACTIONS = {
    "actions/checkout": "d23441a48e516b6c34aea4fa41551a30e30af803",
    "actions/setup-python": "ece7cb06caefa5fff74198d8649806c4678c61a1",
    "actions/setup-node": "249970729cb0ef3589644e2896645e5dc5ba9c38",
    "docker/login-action": "dbcb813823bdd20940b903addbd779551569679f",
    "docker/setup-buildx-action": "37fe631027851001ddb9b187196cc803df7f5f0e",
    "actions/upload-artifact": "ea165f8d65b6e75b540449e92b4886f43607fa02",
    "actions/download-artifact": "634f93cb2916e3fdff6788551b99b062d0335ce0",
    "tailscale/github-action": "306e68a486fd2350f2bfc3b19fcd143891a4a2d8",
}


class GitHubDeployWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = WORKFLOW_PATH.read_text(encoding="utf-8")
        cls.workflow = yaml.safe_load(cls.raw)
        if not isinstance(cls.workflow, dict):
            raise AssertionError("quality workflow must parse as a YAML mapping")
        cls.jobs = cls.workflow["jobs"]
        cls.publish = cls.jobs["publish-release"]
        cls.deploy = cls.jobs["deploy-production"]
        cls.publish_raw = cls.raw.split("  publish-release:", 1)[1].split(
            "  deploy-production:", 1
        )[0]
        cls.deploy_raw = cls.raw.split("  deploy-production:", 1)[1]

    def test_release_is_same_workflow_and_directly_depends_on_all_quality_jobs(self) -> None:
        self.assertNotIn("workflow_run", self.raw)
        self.assertNotIn("workflow_call", self.raw)
        self.assertNotIn("workflow_dispatch", self.raw)
        quality = {"api", "web", "deployment-controls"}
        self.assertEqual(set(self.publish["needs"]), quality)
        self.assertEqual(
            set(self.deploy["needs"]), quality | {"publish-release"}
        )
        expected_condition = (
            "github.event_name == 'push' && "
            "github.ref == 'refs/heads/main' && "
            "vars.PRODUCTION_DEPLOY_ENABLED == 'true'"
        )
        self.assertEqual(self.publish["if"], expected_condition)
        self.assertEqual(self.deploy["if"], expected_condition)
        self.assertIn("ref: ${{ github.sha }}", self.publish_raw)
        self.assertIn('test "$(git rev-parse --verify HEAD)" = "$GITHUB_SHA"', self.publish_raw)

    def test_all_third_party_actions_are_immutable_and_checkouts_drop_credentials(self) -> None:
        uses: list[tuple[str, dict[str, object]]] = []
        for job in self.jobs.values():
            for step in job.get("steps", []):
                reference = step.get("uses")
                if reference:
                    uses.append((reference, step))
        self.assertTrue(uses)
        for reference, step in uses:
            action, separator, revision = reference.partition("@")
            self.assertTrue(separator, reference)
            self.assertIn(action, PINNED_ACTIONS, reference)
            self.assertEqual(revision, PINNED_ACTIONS[action], reference)
            self.assertRegex(revision, r"^[0-9a-f]{40}$")
            if action == "actions/checkout":
                self.assertIs(step.get("with", {}).get("persist-credentials"), False)

    def test_job_permissions_and_concurrency_are_fail_closed(self) -> None:
        self.assertEqual(self.workflow["permissions"], {"contents": "read"})
        self.assertEqual(
            self.publish["permissions"],
            {"contents": "read", "packages": "write"},
        )
        self.assertEqual(
            self.deploy["permissions"],
            {"contents": "read", "id-token": "write"},
        )
        self.assertEqual(self.deploy["environment"]["name"], "production")
        self.assertGreaterEqual(self.deploy["timeout-minutes"], 240)
        self.assertEqual(self.deploy["concurrency"]["group"], "aperture-production")
        self.assertIs(self.deploy["concurrency"]["cancel-in-progress"], False)
        self.assertIn("PRODUCTION_DEPLOY_ENABLED", self.deploy_raw)
        self.assertIn('!= "true"', self.deploy_raw)
        self.assertIn("exit 1", self.deploy_raw)

    def test_publish_uses_github_token_and_only_public_release_inputs(self) -> None:
        self.assertIn("registry: ghcr.io", self.publish_raw)
        self.assertIn("username: ${{ github.actor }}", self.publish_raw)
        self.assertIn("password: ${{ github.token }}", self.publish_raw)
        self.assertNotIn("secrets.", self.publish_raw)
        self.assertNotIn("secrets: inherit", self.raw)
        for name in (
            "APERTURE_REUSE_CADDY_IMAGE",
            "APERTURE_REUSE_STORAGE_IMAGE",
            "APERTURE_REUSE_NODE_EXPORTER_IMAGE",
            "APERTURE_REUSE_BLACKBOX_IMAGE",
        ):
            self.assertIn(f"${{{{ vars.{name} }}}}", self.publish_raw)
            self.assertIn(f'"{name}"', self.publish_raw)
        for forbidden in (
            "POSTGRES_PASSWORD",
            "SESSION_SECRET",
            "STRIPE_SECRET_KEY",
            "TAILSCALE_AUTH_KEY",
            "HOSTINGER_API_TOKEN",
        ):
            self.assertNotIn(forbidden, self.publish_raw)

    def test_release_identity_and_payload_are_immutable_and_allowlisted(self) -> None:
        for identity_part in (
            "GITHUB_SHA",
            "GITHUB_RUN_ID",
            "GITHUB_RUN_ATTEMPT",
        ):
            self.assertIn(identity_part, self.publish_raw)
        self.assertIn("release-manifests/$RELEASE_ID.release.json", self.publish_raw)
        self.assertIn("release-manifests/$RELEASE_ID.release.sha256", self.publish_raw)
        self.assertIn("sha256sum --strict --check", self.publish_raw)
        self.assertIn(
            'sha256sum "$RELEASE_ID.release.json" "$RELEASE_ID.source.tar.gz"',
            self.publish_raw,
        )
        self.assertNotIn('install -m 0600 "$published_checksum"', self.publish_raw)
        self.assertIn("git archive --format=tar --output", self.publish_raw)
        self.assertIn("deploy/production/hostinger", self.publish_raw)
        self.assertIn("deploy/production/private-studio", self.publish_raw)
        self.assertIn("deploy/production/public_edge_smoke.py", self.publish_raw)
        self.assertIn("ops/prometheus-alerts.yml", self.publish_raw)
        self.assertIn(".aperture-source-sha", self.publish_raw)
        self.assertIn("printf '%s\\n' \"$GITHUB_SHA\"", self.publish_raw)
        self.assertNotRegex(self.publish_raw, r"git archive[^\n]+(?:--\s+)?[.](?:\s|$)")
        self.assertNotIn("git ls-tree", self.publish_raw)
        self.assertIn("actions/upload-artifact@", self.publish_raw)
        self.assertIn("release-payload/*", self.publish_raw)
        self.assertIn("mapfile -t checksum_lines", self.deploy_raw)
        self.assertIn('"  $RELEASE_ID.release.json"', self.deploy_raw)
        self.assertIn('"  $RELEASE_ID.source.tar.gz"', self.deploy_raw)

        publisher = re.search(
            r"^\s+allowed_files=\(\n(?P<files>.*?)^\s+\)$",
            self.publish_raw,
            flags=re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(publisher)
        published_files = {
            line.strip()
            for line in publisher.group("files").splitlines()
            if line.strip()
        }
        self.assertEqual(
            published_files | {".aperture-source-sha"},
            set(REQUIRED_BUNDLE_FILES),
        )
        for filename in REQUIRED_BUNDLE_FILES:
            self.assertIn(f'"{filename}"', self.deploy_raw)

    def test_deploy_uses_wif_and_pinned_openssh_with_one_secret(self) -> None:
        secret_names = set(
            re.findall(r"\$\{\{\s*secrets\.([A-Z0-9_]+)\s*}}", self.raw)
        )
        self.assertEqual(secret_names, {"APERTURE_DEPLOY_SSH_PRIVATE_KEY"})
        self.assertIn("tailscale/github-action@", self.deploy_raw)
        self.assertIn(
            "oauth-client-id: ${{ vars.APERTURE_TAILSCALE_OIDC_CLIENT_ID }}",
            self.deploy_raw,
        )
        self.assertIn(
            "audience: ${{ vars.APERTURE_TAILSCALE_OIDC_AUDIENCE }}",
            self.deploy_raw,
        )
        self.assertIn("tags: tag:aperture-ci", self.deploy_raw)
        self.assertIn("StrictHostKeyChecking=yes", self.deploy_raw)
        self.assertIn("UserKnownHostsFile=", self.deploy_raw)
        self.assertIn("ServerAliveInterval=15", self.deploy_raw)
        self.assertIn("ServerAliveCountMax=3", self.deploy_raw)
        self.assertIn("ssh-keygen -F", self.deploy_raw)
        self.assertIn("ssh-ed25519", self.deploy_raw)
        self.assertNotIn("ssh-keyscan", self.deploy_raw)
        self.assertIn("scp \"${ssh_options[@]}\"", self.deploy_raw)
        self.assertIn("sudo -n /usr/local/sbin/aperture-deploy-release", self.deploy_raw)
        self.assertIn("aperture-deploy-release --start", self.deploy_raw)
        self.assertIn("aperture-deploy-release --status", self.deploy_raw)
        for flag in (
            "--bundle",
            "--manifest",
            "--checksum",
            "--expected-current-source-sha",
            "--expected-source-sha",
            "--expected-release-id",
        ):
            self.assertIn(flag, self.deploy_raw)

    def test_downloaded_payload_is_mode_normalized_before_scp(self) -> None:
        normalization = 'chmod 0600 "$bundle" "$manifest" "$checksum"'
        assertion = '[[ "$(stat -c %a "$path")" == "600" ]]'
        self.assertIn(normalization, self.deploy_raw)
        self.assertIn(assertion, self.deploy_raw)
        self.assertLess(
            self.deploy_raw.index(normalization),
            self.deploy_raw.index('timeout 120s scp "${ssh_options[@]}"'),
        )

    def test_ssh_enqueues_systemd_owned_deploy_and_polls_safe_status(self) -> None:
        self.assertIn("--start --bundle", self.deploy_raw)
        self.assertIn("--status --expected-release-id", self.deploy_raw)
        self.assertIn("source_deadline=$((SECONDS + 1800))", self.deploy_raw)
        self.assertIn("deadline=$((SECONDS + 10500))", self.deploy_raw)
        self.assertIn('queued|running) sleep 15', self.deploy_raw)
        self.assertIn('value["source_commit"] != os.environ["SOURCE_SHA"]', self.deploy_raw)
        self.assertIn('value["release_id"] != os.environ["RELEASE_ID"]', self.deploy_raw)
        self.assertIn("systemd service remains authoritative", self.deploy_raw)
        self.assertIn("timeout 45s ssh", self.deploy_raw)
        self.assertIn("timeout 90s ssh", self.deploy_raw)
        self.assertIn("status_result=$?", self.deploy_raw)
        self.assertIn("if ((status_result != 0)); then", self.deploy_raw)
        self.assertIn("host-owned recovery service remains authoritative", self.deploy_raw)
        self.assertIn("reconcile_result=$?", self.deploy_raw)
        self.assertIn("VPS reconciliation path is temporarily unavailable", self.deploy_raw)
        first_start = self.deploy_raw.index("--start --bundle")
        poll_loop = self.deploy_raw.index("while ((SECONDS < deadline))")
        status_query = self.deploy_raw.index(
            "--status --expected-release-id", first_start
        )
        self.assertEqual(self.deploy_raw.count("--start --bundle"), 1)
        self.assertLess(poll_loop, first_start)
        self.assertLess(first_start, status_query)
        self.assertNotRegex(
            self.deploy_raw,
            r"aperture-deploy-release --bundle",
        )

    def test_clean_ci_supplies_only_the_committed_dummy_env_for_compose(self) -> None:
        controls = self.jobs["deployment-controls"]
        rendered = "\n".join(
            step.get("run", "") for step in controls["steps"] if "run" in step
        )
        self.assertIn("pyyaml==6.0.3", rendered)
        self.assertIn("pytest==9.0.3", rendered)
        self.assertIn("python -m pytest -q deploy/production/hostinger", rendered)
        self.assertIn("python -m pytest -q", rendered)
        self.assertNotIn("unittest discover", rendered)
        self.assertIn(
            "install -m 0600 deploy/production/hostinger/credentials.example.env .env",
            rendered,
        )
        self.assertIn("trap 'rm -f .env' EXIT", rendered)

    def test_api_starts_and_always_cleans_up_pinned_minio(self) -> None:
        api = self.jobs["api"]
        self.assertNotIn("minio", api.get("services", {}))
        rendered = "\n".join(
            step.get("run", "") for step in api["steps"] if "run" in step
        )
        self.assertIn(
            "minio/minio:RELEASE.2025-09-07T16-13-09Z server /data",
            rendered,
        )
        self.assertIn("/minio/health/live", rendered)
        cleanup = next(
            step for step in api["steps"] if step.get("name") == "Stop private object storage"
        )
        self.assertEqual(cleanup["if"], "always()")
        self.assertIn("docker rm --force aperture-ci-minio", cleanup["run"])

    def test_bundle_verifier_requires_the_exact_regular_file_contract(self) -> None:
        self.assertIn("allowed_files=(", self.publish_raw)
        self.assertIn("found != expected", self.deploy_raw)
        self.assertIn("member.isreg()", self.deploy_raw)

    def test_operations_local_script_dependencies_are_in_the_bundle(self) -> None:
        operations = (
            ROOT / "deploy" / "production" / "hostinger" / "operations.sh"
        ).read_text(encoding="utf-8")
        invoked = {
            f"deploy/production/hostinger/{name}"
            for name in re.findall(r'"\$BASE_DIR/([A-Za-z0-9_.-]+\.(?:py|sh))"', operations)
        }
        self.assertTrue(invoked)
        self.assertLessEqual(invoked, set(REQUIRED_BUNDLE_FILES))

    def test_migrations_require_an_exact_commit_scoped_production_approval(self) -> None:
        self.assertIn("fetch-depth: 0", self.deploy_raw)
        self.assertIn("persist-credentials: false", self.deploy_raw)
        self.assertNotIn("github.event.before", self.deploy_raw)
        self.assertIn("--report-current-source-sha", self.deploy_raw)
        self.assertIn("source_deadline=$((SECONDS + 1800))", self.deploy_raw)
        self.assertIn("source_result=$?", self.deploy_raw)
        self.assertIn("active-source query is temporarily blocked", self.deploy_raw)
        self.assertIn(
            "DEPLOYED_SOURCE_SHA: ${{ steps.active-production.outputs.source_sha }}",
            self.deploy_raw,
        )
        self.assertIn(
            'git diff --quiet "$DEPLOYED_SOURCE_SHA" "$GITHUB_SHA" -- apps/api/migrations/',
            self.deploy_raw,
        )
        self.assertIn("APERTURE_APPROVED_MIGRATION_SHA", self.deploy_raw)
        self.assertIn(
            '"$APERTURE_APPROVED_MIGRATION_SHA" != "$GITHUB_SHA"',
            self.deploy_raw,
        )
        active_query = self.deploy_raw.index("--report-current-source-sha")
        migration_diff = self.deploy_raw.index(
            'git diff --quiet "$DEPLOYED_SOURCE_SHA" "$GITHUB_SHA"'
        )
        guarded_deploy = self.deploy_raw.index("--expected-current-source-sha")
        self.assertLess(active_query, migration_diff)
        self.assertLess(migration_diff, guarded_deploy)

    def test_remote_staging_is_limited_to_the_dedicated_account_incoming_root(self) -> None:
        self.assertIn('incoming="incoming/$RELEASE_ID"', self.deploy_raw)
        self.assertIn("\\$HOME/incoming", self.deploy_raw)
        self.assertNotIn("aperture-incoming", self.deploy_raw)

    def test_release_context_excludes_runtime_secrets_and_database_dumps(self) -> None:
        docker_ignores = {
            line.strip()
            for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        git_ignores = {
            line.strip()
            for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        self.assertIn(".env", docker_ignores)
        self.assertIn("*.rdb", docker_ignores)
        self.assertIn("*.rdb", git_ignores)


if __name__ == "__main__":
    unittest.main()
