"""Return a current TOTP for browser acceptance without exposing it to the app."""

import json
import sys

import pyotp


def main() -> None:
    secret = json.load(sys.stdin)["secret"]
    print(json.dumps({"code": pyotp.TOTP(secret).now()}))


if __name__ == "__main__":
    main()
