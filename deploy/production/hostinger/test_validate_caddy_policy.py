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
            "path": ["/studio", "/studio/*", "/api/admin", "/api/admin/*"],
        }],
    }
    proxy = {
        "handle": [{
            "handler": "subroute",
            "routes": [{"handle": [{"handler": "reverse_proxy"}]}],
        }]
    }
    return {
        "apps": {"http": {"servers": {"application": {
            "routes": [{"handle": [{"handler": "subroute", "routes": [
                origin_denial, studio_denial, proxy
            ]}]}]
        }}}}
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


if __name__ == "__main__":
    unittest.main()
