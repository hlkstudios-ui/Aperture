from types import SimpleNamespace

import stripe
from botocore.exceptions import ClientError

from scripts.production_preflight import (
    billing_check,
    configuration_check,
    malware_scanner_check,
    storage_check,
)


def test_configuration_preflight_requires_production() -> None:
    assert configuration_check(SimpleNamespace(app_env="production")).status == "pass"
    result = configuration_check(SimpleNamespace(app_env="staging"))
    assert result.status == "fail"
    assert result.code == "app_env_is_not_production"


def test_billing_preflight_authenticates_without_mutation(monkeypatch) -> None:
    captured = {}

    def retrieve(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id="acct_fake_verified")

    monkeypatch.setattr("scripts.production_preflight.stripe.Account.retrieve", retrieve)
    settings = SimpleNamespace(billing_provider="stripe", stripe_secret_key="sk_live_fake")
    result = billing_check(settings)
    assert result.status == "pass"
    assert result.code == "provider_account_authenticated_read_only"
    assert captured == {"api_key": "sk_live_fake"}

    result = billing_check(SimpleNamespace(billing_provider="unavailable", stripe_secret_key=None))
    assert result.status == "fail"
    assert result.code == "supported_provider_not_configured"

    monkeypatch.setattr(
        "scripts.production_preflight.stripe.Account.retrieve",
        lambda **_: (_ for _ in ()).throw(stripe.AuthenticationError("secret detail")),
    )
    result = billing_check(settings)
    assert result.status == "fail"
    assert result.code == "provider_authentication_or_connection_failed"


def test_malware_scanner_preflight_requires_valid_clamd_ping(monkeypatch) -> None:
    class Connection:
        sent = b""

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def settimeout(self, _timeout):
            return None

        def sendall(self, value):
            self.sent = value

        def recv(self, _size):
            return b"PONG\0"

    connection = Connection()
    monkeypatch.setattr(
        "scripts.production_preflight.socket.create_connection",
        lambda *_args, **_kwargs: connection,
    )
    settings = SimpleNamespace(
        malware_scanner_mode="clamav_tcp",
        malware_scanner_host="private-scanner",
        malware_scanner_port=3310,
    )
    result = malware_scanner_check(settings)
    assert result.status == "pass"
    assert result.code == "private_clamd_ping"
    assert connection.sent == b"zPING\0"

    connection.recv = lambda _size: b"unexpected"
    assert malware_scanner_check(settings).status == "fail"


def test_storage_preflight_requires_versioning_and_private_policy(monkeypatch) -> None:
    class Storage:
        def head_bucket(self, **_):
            return {}

        def get_bucket_versioning(self, **_):
            return {"Status": "Enabled"}

        def get_bucket_acl(self, **_):
            return {"Grants": []}

        def get_bucket_policy_status(self, **_):
            return {"PolicyStatus": {"IsPublic": False}}

    monkeypatch.setattr("scripts.production_preflight.boto3.client", lambda *_, **__: Storage())
    settings = SimpleNamespace(
        s3_endpoint="https://storage.example.com",
        s3_region="ca-central-1",
        s3_access_key="injected",
        s3_secret_key="injected",
        s3_bucket="production-media",
    )
    assert storage_check(settings).status == "pass"

    class PublicStorage(Storage):
        def get_bucket_policy_status(self, **_):
            return {"PolicyStatus": {"IsPublic": True}}

    monkeypatch.setattr(
        "scripts.production_preflight.boto3.client", lambda *_, **__: PublicStorage()
    )
    result = storage_check(settings)
    assert result.status == "fail"
    assert result.code == "public_policy_detected_or_unknown"


def test_storage_preflight_accepts_digitalocean_private_acl_without_policy(monkeypatch) -> None:
    class Spaces:
        def head_bucket(self, **_):
            return {}

        def get_bucket_versioning(self, **_):
            return {"Status": "Enabled"}

        def get_bucket_acl(self, **_):
            return {"Grants": []}

        def get_bucket_policy_status(self, **_):
            raise NotImplementedError

        def get_bucket_policy(self, **_):
            raise ClientError(
                {"Error": {"Code": "NoSuchBucketPolicy", "Message": "not configured"}},
                "GetBucketPolicy",
            )

    monkeypatch.setattr("scripts.production_preflight.boto3.client", lambda *_, **__: Spaces())
    settings = SimpleNamespace(
        s3_endpoint="https://tor1.digitaloceanspaces.com/",
        s3_region="tor1",
        s3_access_key="fake",
        s3_secret_key="fake",
        s3_bucket="production-media",
    )
    assert storage_check(settings).status == "pass"


def test_storage_preflight_accepts_digitalocean_policy_without_public_allow(monkeypatch) -> None:
    class Spaces:
        def head_bucket(self, **_):
            return {}

        def get_bucket_versioning(self, **_):
            return {"Status": "Enabled"}

        def get_bucket_acl(self, **_):
            return {"Grants": []}

        def get_bucket_policy_status(self, **_):
            raise NotImplementedError

        def get_bucket_policy(self, **_):
            return {
                "Policy": '{"Statement":[{"Effect":"Deny","Principal":"*",'
                '"Action":["s3:GetObject","s3:ListBucket"],"Resource":"*"}]}'
            }

    monkeypatch.setattr("scripts.production_preflight.boto3.client", lambda *_, **__: Spaces())
    settings = SimpleNamespace(
        s3_endpoint="https://tor1.digitaloceanspaces.com/",
        s3_region="tor1",
        s3_access_key="fake",
        s3_secret_key="fake",
        s3_bucket="production-media",
    )
    assert storage_check(settings).status == "pass"

    class PublicSpaces(Spaces):
        def get_bucket_policy(self, **_):
            return {
                "Policy": '{"Statement":[{"Effect":"Allow","Principal":"*",'
                '"Action":"s3:GetObject","Resource":"*"}]}'
            }

    monkeypatch.setattr(
        "scripts.production_preflight.boto3.client", lambda *_, **__: PublicSpaces()
    )
    result = storage_check(settings)
    assert result.status == "fail"
    assert result.code == "public_policy_detected_or_unknown"
