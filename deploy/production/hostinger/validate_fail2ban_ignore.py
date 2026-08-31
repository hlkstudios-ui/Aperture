"""Validate the effective Fail2ban sshd ignore list without exposing its values."""

import argparse
import ipaddress
import sys


def parse_networks(output: str) -> set[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    networks: set[ipaddress.IPv4Network | ipaddress.IPv6Network] = set()
    for raw in output.split():
        token = raw.strip("|`-,[]()")
        try:
            networks.add(ipaddress.ip_network(token, strict=False))
        except ValueError:
            pass
    return networks


def validate(output: str, allowed_cidr: str) -> None:
    required = {
        ipaddress.ip_network("127.0.0.1/8", strict=False),
        ipaddress.ip_network("::1", strict=False),
        ipaddress.ip_network(allowed_cidr, strict=False),
    }
    if not required.issubset(parse_networks(output)):
        raise ValueError("effective Fail2ban sshd ignoreip policy is incomplete")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allowed", required=True)
    args = parser.parse_args()
    validate(sys.stdin.read(), args.allowed)
    print("Effective Fail2ban sshd ignoreip policy is valid.")


if __name__ == "__main__":
    main()
