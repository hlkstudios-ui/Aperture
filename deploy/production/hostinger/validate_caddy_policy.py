"""Validate adapted Caddy JSON preserves both origin and private-Studio admission."""

import argparse
import json
from pathlib import Path


def walk_routes(value):
    if isinstance(value, dict):
        if "handle" in value or "match" in value:
            yield value
        for child in value.values():
            yield from walk_routes(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_routes(child)


def walk_route_lists(value):
    if isinstance(value, dict):
        routes = value.get("routes")
        if isinstance(routes, list):
            yield routes
        for child in value.values():
            yield from walk_route_lists(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_route_lists(child)


def route_has_handler(route: dict, handler_name: str) -> bool:
    return any(
        handler.get("handler") == handler_name
        for handler in route.get("handle", [])
        if isinstance(handler, dict)
    )


def validate(model: dict) -> None:
    servers = model.get("apps", {}).get("http", {}).get("servers", {})
    routes = list(walk_routes(servers))
    serialized = json.dumps(routes, sort_keys=True)
    if "X-Aperture-Origin-Secret" not in serialized:
        raise ValueError("origin admission matcher is missing")
    if "X-Aperture-Studio-Edge" not in serialized:
        raise ValueError("private Studio admission matcher is missing")
    if "/studio/*" not in serialized or "/api/admin/*" not in serialized:
        raise ValueError("private Studio route coverage is incomplete")
    studio_routes = [
        route for route in routes
        if "/studio/*" in json.dumps(route) and route.get("handle", [{}])[0].get("status_code") == 404
    ]
    if not studio_routes:
        raise ValueError("private Studio denial response is missing")
    studio = json.dumps(studio_routes, sort_keys=True)
    if "X-Aperture-Studio-Edge" not in studio or '"not"' not in studio:
        raise ValueError("private Studio denial is not conditional on a missing/wrong secret")
    ordered_policy_found = False
    for route_list in walk_route_lists(servers):
        route_text = json.dumps(route_list)
        if "X-Aperture-Origin-Secret" not in route_text:
            continue
        if "X-Aperture-Studio-Edge" not in route_text:
            continue
        denial_indexes = [
            index
            for index, route in enumerate(route_list)
            if route_has_handler(route, "static_response")
        ]
        proxy_indexes = [
            index
            for index, route in enumerate(route_list)
            if route_has_handler(route, "subroute")
            and "reverse_proxy" in json.dumps(route)
        ]
        if denial_indexes and proxy_indexes and max(denial_indexes) < min(proxy_indexes):
            ordered_policy_found = True
            break
    if not ordered_policy_found:
        raise ValueError("Caddy denial matchers do not precede application proxy routes")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    validate(json.loads(args.input.read_text()))
    print("Caddy origin and private Studio admission policy is valid.")


if __name__ == "__main__":
    main()
