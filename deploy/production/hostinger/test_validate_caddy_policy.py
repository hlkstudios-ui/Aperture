import copy
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "hostinger_validate_caddy_policy", ROOT / "validate_caddy_policy.py"
)
assert SPEC and SPEC.loader
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


def model():
    origin_denial = {
        "handle": [{"handler": "static_response", "status_code": 404}],
        "match": [{"not": [{"header": {"X-Aperture-Origin-Secret": ["origin"]}}]}],
    }
    studio_denial = {
        "handle": [{"handler": "static_response", "status_code": 404}],
        "match": [{
            "not": [{"header": {"X-Aperture-Studio-Edge": ["studio"]}}],
            "path": [
                "/studio",
                "/studio/*",
                "/api/admin",
                "/api/admin/*",
                "/api/gateway/admin",
                "/api/gateway/admin/*",
            ],
        }],
    }
    public_host_propagation = {
        "handle": [
            {
                "handler": "headers",
                "request": {"set": {
                    "Host": ["{http.request.header.X-Aperture-Public-Host}"]
                }},
            },
            {
                "handler": "headers",
                "request": {"set": {
                    "X-Forwarded-Host": [
                        "{http.request.header.X-Aperture-Public-Host}"
                    ]
                }},
            },
        ],
        "match": [{"header": {"X-Aperture-Public-Host": ["*"]}}],
    }
    proxy = {
        "handle": [{
            "handler": "subroute",
            "routes": [{"handle": [{"handler": "reverse_proxy"}]}],
        }]
    }
    storage_denials = [
        {
            "handle": [{"handler": "static_response", "status_code": 403}],
            "match": [{"header": {"X-Amz-Content-Sha256": [
                "STREAMING-UNSIGNED-PAYLOAD-TRAILER"
            ]}}],
        },
        {
            "handle": [{"handler": "static_response", "status_code": 403}],
            "match": [{"header": {"X-Amz-Meta-Snowball-Auto-Extract": ["*"]}}],
        },
        {
            "handle": [{"handler": "static_response", "status_code": 403}],
            "match": [{
                "method": ["POST"],
                "query": {"select": ["*"], "select-type": ["2"]},
            }],
        },
    ]
    for header in (
        "X-Minio-Replication-Server-Side-Encryption-Sealed-Key",
        "X-Minio-Replication-Server-Side-Encryption-Seal-Algorithm",
        "X-Minio-Replication-Server-Side-Encryption-Iv",
    ):
        storage_denials.append({
            "handle": [{"handler": "static_response", "status_code": 403}],
            "match": [{"header": {header: ["*"]}}],
        })
    storage_denials.append({
        "handle": [{"handler": "static_response", "status_code": 404}],
        "match": [{"path": ["/minio/storage/*"]}],
    })
    storage_proxy = {
        "handle": [{
            "handler": "reverse_proxy",
            "upstreams": [{"dial": "minio:9000"}],
        }]
    }
    return {
        "apps": {"http": {"servers": {
            "application": {
                "routes": [{"handle": [{"handler": "subroute", "routes": [
                    origin_denial, studio_denial, public_host_propagation, proxy
                ]}]}]
            },
            "storage": {
                "routes": [{"handle": [{
                    "handler": "subroute",
                    "routes": [*storage_denials, storage_proxy],
                }]}]
            },
        }}}
    }


def guarded_media_proxy():
    return {
        "handle": [{
            "handler": "subroute",
            "routes": [
                {
                    "handle": [{"handler": "static_response", "status_code": 404}],
                    "match": [{
                        "not": [{
                            "header": {"X-Aperture-Origin-Secret": ["media"]}
                        }]
                    }],
                },
                {"handle": [{"handler": "reverse_proxy"}]},
            ],
        }],
        "match": [{"path": ["/api/edge-media/*"]}],
    }


class CaddyPolicyTests(unittest.TestCase):
    def test_ordered_private_policy_passes(self):
        policy.validate(model())

    def test_proxy_before_denials_is_rejected(self):
        value = copy.deepcopy(model())
        application = value["apps"]["http"]["servers"]["application"]
        routes = application["routes"][0]["handle"][0]["routes"]
        routes.insert(0, routes.pop())
        with self.assertRaisesRegex(ValueError, "do not precede"):
            policy.validate(value)

    def test_independently_guarded_media_proxy_can_precede_application_denials(self):
        value = copy.deepcopy(model())
        application = value["apps"]["http"]["servers"]["application"]
        routes = application["routes"][0]["handle"][0]["routes"]
        routes.insert(0, guarded_media_proxy())
        policy.validate(value)

    def test_missing_trusted_public_host_propagation_is_rejected(self):
        value = copy.deepcopy(model())
        routes = value["apps"]["http"]["servers"]["application"]["routes"][0][
            "handle"
        ][0]["routes"]
        routes.pop(2)
        with self.assertRaisesRegex(ValueError, "public-host propagation"):
            policy.validate(value)

    def test_partial_trusted_public_host_propagation_is_rejected(self):
        value = copy.deepcopy(model())
        routes = value["apps"]["http"]["servers"]["application"]["routes"][0][
            "handle"
        ][0]["routes"]
        routes[2]["handle"].pop()
        with self.assertRaisesRegex(ValueError, "public-host propagation"):
            policy.validate(value)

    def test_public_host_propagation_before_origin_denial_is_rejected(self):
        value = copy.deepcopy(model())
        routes = value["apps"]["http"]["servers"]["application"]["routes"][0][
            "handle"
        ][0]["routes"]
        routes.insert(0, routes.pop(2))
        with self.assertRaisesRegex(ValueError, "public-host propagation"):
            policy.validate(value)

    def test_media_proxy_before_its_own_denial_is_rejected(self):
        value = copy.deepcopy(model())
        media = guarded_media_proxy()
        media_routes = media["handle"][0]["routes"]
        media_routes.insert(0, media_routes.pop())
        application = value["apps"]["http"]["servers"]["application"]
        routes = application["routes"][0]["handle"][0]["routes"]
        routes.insert(0, media)
        with self.assertRaisesRegex(ValueError, "do not precede"):
            policy.validate(value)

    def test_media_route_with_an_unguarded_nested_proxy_is_rejected(self):
        value = copy.deepcopy(model())
        media = guarded_media_proxy()
        media["handle"].append({
            "handler": "subroute",
            "routes": [{"handle": [{"handler": "reverse_proxy"}]}],
        })
        application = value["apps"]["http"]["servers"]["application"]
        routes = application["routes"][0]["handle"][0]["routes"]
        routes.insert(0, media)
        with self.assertRaisesRegex(ValueError, "do not precede"):
            policy.validate(value)

    def test_storage_proxy_before_advisory_denials_is_rejected(self):
        value = copy.deepcopy(model())
        routes = value["apps"]["http"]["servers"]["storage"]["routes"][0][
            "handle"
        ][0]["routes"]
        routes.insert(0, routes.pop())
        with self.assertRaisesRegex(ValueError, "advisory denials"):
            policy.validate(value)

    def test_missing_unsigned_trailer_denial_is_rejected(self):
        value = copy.deepcopy(model())
        routes = value["apps"]["http"]["servers"]["storage"]["routes"][0][
            "handle"
        ][0]["routes"]
        routes.pop(0)
        with self.assertRaisesRegex(ValueError, "advisory denials"):
            policy.validate(value)


if __name__ == "__main__":
    unittest.main()
