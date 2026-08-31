"""Read-only production dependency preflight.

Run from apps/api inside the release image with production secrets injected by the
deployment platform. Output contains check state and stable error codes only.
"""

import argparse
import json
import smtplib
import socket
import ssl
from dataclasses import asdict, dataclass

import boto3
import redis
import stripe
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from sqlalchemy import create_engine, text

from app.config import Settings


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    code: str


def passed(name: str, code: str = "ok") -> Check:
    return Check(name, "pass", code)


def failed(name: str, code: str) -> Check:
    return Check(name, "fail", code)


def database_check(settings: Settings) -> Check:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            current = MigrationContext.configure(connection).get_current_revision()
        script = ScriptDirectory.from_config(Config("alembic.ini"))
        heads = script.get_heads()
        if len(heads) != 1 or current != heads[0]:
            return failed("database", "migration_head_mismatch")
        return passed("database", "reachable_at_migration_head")
    except Exception:
        return failed("database", "unreachable_or_migration_unreadable")
    finally:
        engine.dispose()


def redis_check(settings: Settings) -> Check:
    client = redis.from_url(settings.redis_url, socket_connect_timeout=3, socket_timeout=3)
    try:
        return (
            passed("redis", "authenticated_ping")
            if client.ping()
            else failed("redis", "ping_rejected")
        )
    except Exception:
        return failed("redis", "unreachable_or_authentication_failed")
    finally:
        client.close()


def storage_check(settings: Settings) -> Check:
    client = boto3.client(
        "s3",
        endpoint_url=str(settings.s3_endpoint),
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=BotoConfig(connect_timeout=3, read_timeout=3, s3={"addressing_style": "path"}),
    )
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
        versioning = client.get_bucket_versioning(Bucket=settings.s3_bucket).get("Status")
        if versioning != "Enabled":
            return failed("object_storage", "versioning_not_enabled")
        acl = client.get_bucket_acl(Bucket=settings.s3_bucket)
        public_uris = {
            "http://acs.amazonaws.com/groups/global/AllUsers",
            "http://acs.amazonaws.com/groups/global/AuthenticatedUsers",
        }
        if any(grant.get("Grantee", {}).get("URI") in public_uris for grant in acl["Grants"]):
            return failed("object_storage", "public_acl_detected")
        try:
            policy = client.get_bucket_policy_status(Bucket=settings.s3_bucket)
        except Exception:
            if not str(settings.s3_endpoint).endswith(".digitaloceanspaces.com/"):
                return failed("object_storage", "public_policy_state_unverifiable")
            try:
                policy_document = json.loads(
                    client.get_bucket_policy(Bucket=settings.s3_bucket)["Policy"]
                )
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code")
                if code in {"NoSuchBucketPolicy", "NoSuchPolicy", "404"}:
                    return passed("object_storage", "reachable_private_and_versioned")
                return failed("object_storage", "public_policy_state_unverifiable")
            except Exception:
                return failed("object_storage", "public_policy_state_unverifiable")
            statements = policy_document.get("Statement", [])
            statements = statements if isinstance(statements, list) else [statements]
            for statement in statements:
                principal = statement.get("Principal")
                public_principal = principal == "*" or (
                    isinstance(principal, dict) and principal.get("AWS") == "*"
                )
                if statement.get("Effect") != "Allow" or not public_principal:
                    continue
                actions = statement.get("Action", [])
                actions = [actions] if isinstance(actions, str) else actions
                if {"s3:GetObject", "s3:ListBucket", "s3:*"}.intersection(actions):
                    return failed("object_storage", "public_policy_detected_or_unknown")
            return passed("object_storage", "reachable_private_and_versioned")
        if policy.get("PolicyStatus", {}).get("IsPublic") is not False:
            return failed("object_storage", "public_policy_detected_or_unknown")
        return passed("object_storage", "reachable_private_and_versioned")
    except Exception:
        return failed("object_storage", "unreachable_or_policy_unreadable")


def smtp_check(settings: Settings) -> Check:
    if not all(
        (
            settings.smtp_host,
            settings.smtp_username,
            settings.smtp_password,
            settings.smtp_from_email,
        )
    ):
        return failed("smtp", "configuration_incomplete")
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=5) as smtp:
            smtp.ehlo()
            if settings.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            smtp.login(settings.smtp_username, settings.smtp_password)
        return passed("smtp", "authenticated_without_sending")
    except Exception:
        return failed("smtp", "connection_tls_or_authentication_failed")


def billing_check(settings: Settings) -> Check:
    if settings.billing_provider == "disabled":
        return passed("billing", "payments_intentionally_disabled")
    if settings.billing_provider != "stripe" or not settings.stripe_secret_key:
        return failed("billing", "supported_provider_not_configured")
    try:
        account = stripe.Account.retrieve(api_key=settings.stripe_secret_key)
    except stripe.StripeError:
        return failed("billing", "provider_authentication_or_connection_failed")
    if not getattr(account, "id", None):
        return failed("billing", "provider_account_unverifiable")
    return passed("billing", "provider_account_authenticated_read_only")


def malware_scanner_check(settings: Settings) -> Check:
    if settings.malware_scanner_mode != "clamav_tcp" or not settings.malware_scanner_host:
        return failed("malware_scanner", "production_scanner_not_configured")
    try:
        with socket.create_connection(
            (settings.malware_scanner_host, settings.malware_scanner_port), timeout=5
        ) as connection:
            connection.settimeout(5)
            connection.sendall(b"zPING\0")
            response = connection.recv(64).strip(b"\0\r\n")
    except Exception:
        return failed("malware_scanner", "unreachable_or_invalid_response")
    return (
        passed("malware_scanner", "private_clamd_ping")
        if response == b"PONG"
        else failed("malware_scanner", "unreachable_or_invalid_response")
    )


def configuration_check(settings: Settings) -> Check:
    if settings.app_env != "production":
        return failed("configuration", "app_env_is_not_production")
    return passed("configuration", "production_validation_passed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run secret-safe production dependency checks")
    parser.add_argument(
        "--configuration-only",
        action="store_true",
        help="Validate production settings without contacting dependencies",
    )
    args = parser.parse_args()
    try:
        settings = Settings()
    except Exception:
        print(json.dumps({"status": "fail", "checks": [], "code": "configuration_invalid"}))
        raise SystemExit(1) from None
    checks = [configuration_check(settings)]
    if not args.configuration_only and checks[0].status == "pass":
        checks.extend(
            (
                database_check(settings),
                redis_check(settings),
                storage_check(settings),
                smtp_check(settings),
                billing_check(settings),
                malware_scanner_check(settings),
            )
        )
    success = all(item.status == "pass" for item in checks)
    print(
        json.dumps(
            {
                "status": "pass" if success else "fail",
                "checks": [asdict(item) for item in checks],
                "secrets_in_output": False,
            },
            sort_keys=True,
        )
    )
    raise SystemExit(0 if success else 1)


if __name__ == "__main__":
    main()
