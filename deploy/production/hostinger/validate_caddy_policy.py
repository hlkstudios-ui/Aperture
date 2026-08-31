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


def route_has_denial(route: dict, header_name: str | None = None) -> bool:
    denied = any(
        handler.get("handler") == "static_response"
        and handler.get("status_code") == 404
        for handler in route.get("handle", [])
        if isinstance(handler, dict)
    )
    if not denied:
        return False
    matcher = json.dumps(route.get("match", []), sort_keys=True)
    return '"not"' in matcher and (header_name is None or header_name in matcher)


def route_has_proxy(route: dict) -> bool:
    return route_has_handler(route, "reverse_proxy") or (
        route_has_handler(route, "subroute") and "reverse_proxy" in json.dumps(route)
    )


def route_propagates_trusted_public_host(route: dict) -> bool:
    matcher = route.get("match", [])
    if not any(
        isinstance(item, dict)
        and item.get("header", {}).get("X-Aperture-Public-Host") == ["*"]
        for item in matcher
    ):
        return False
    expected = ["{http.request.header.X-Aperture-Public-Host}"]
    request_sets: dict[str, list[str]] = {}
    for handler in route.get("handle", []):
        if not isinstance(handler, dict) or handler.get("handler") != "headers":
            continue
        values = handler.get("request", {}).get("set", {})
        if isinstance(values, dict):
            request_sets.update(values)
    return (
        request_sets.get("Host") == expected
        and request_sets.get("X-Forwarded-Host") == expected
    )


def route_has_minio_proxy(route: dict) -> bool:
    return route_has_handler(route, "reverse_proxy") and "minio:9000" in json.dumps(
        route, sort_keys=True
    )


def route_has_status(route: dict, status_code: int) -> bool:
    return any(
        handler.get("handler") == "static_response"
        and handler.get("status_code") == status_code
        for handler in route.get("handle", [])
        if isinstance(handler, dict)
    )


def validate_storage_boundary(servers: dict) -> None:
    required_markers = {
        "X-Amz-Content-Sha256",
        "STREAMING-UNSIGNED-PAYLOAD-TRAILER",
        "X-Amz-Meta-Snowball-Auto-Extract",
        "X-Minio-Replication-Server-Side-Encryption-Sealed-Key",
        "X-Minio-Replication-Server-Side-Encryption-Seal-Algorithm",
        "X-Minio-Replication-Server-Side-Encryption-Iv",
        '"method": ["POST"]',
        '"select": ["*"]',
        '"select-type": ["2"]',
        '"path": ["/minio/storage/*"]',
    }
    minio_proxy_found = False
    for route_list in walk_route_lists(servers):
        proxy_indexes = [
            index
            for index, route in enumerate(route_list)
            if route_has_minio_proxy(route)
        ]
        for proxy_index in proxy_indexes:
            minio_proxy_found = True
            denials = [
                route
                for route in route_list[:proxy_index]
                if route_has_status(route, 403) or route_has_status(route, 404)
            ]
            serialized = json.dumps(denials, sort_keys=True)
            missing = sorted(marker for marker in required_markers if marker not in serialized)
            if not missing:
                return
    if not minio_proxy_found:
        raise ValueError("public MinIO reverse proxy is missing")
    raise ValueError("MinIO advisory denials are incomplete or follow the storage proxy")


def route_is_guarded_media_proxy(route: dict) -> bool:
    paths = {
        path
        for matcher in route.get("match", [])
        if isinstance(matcher, dict)
        for path in matcher.get("path", [])
    }
    if paths != {"/api/edge-media/*"}:
        return False
    proxy_found = False
    for route_list in walk_route_lists(route):
        proxy_indexes = [
            index
            for index, child in enumerate(route_list)
            if route_has_handler(child, "reverse_proxy")
        ]
        if not proxy_indexes:
            continue
        proxy_found = True
        denial_indexes = [
            index
            for index, child in enumerate(route_list)
            if route_has_denial(child, "X-Aperture-Origin-Secret")
        ]
        if not denial_indexes or max(denial_indexes) >= min(proxy_indexes):
            return False
    return proxy_found


def validate(model: dict) -> None:
    servers = model.get("apps", {}).get("http", {}).get("servers", {})
    validate_storage_boundary(servers)
    routes = list(walk_routes(servers))
    serialized = json.dumps(routes, sort_keys=True)
    if "X-Aperture-Origin-Secret" not in serialized:
        raise ValueError("origin admission matcher is missing")
    if "X-Aperture-Studio-Edge" not in serialized:
        raise ValueError("private Studio admission matcher is missing")
    if (
        "/studio/*" not in serialized
        or "/api/admin/*" not in serialized
        or "/api/gateway/admin/*" not in serialized
    ):
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
    trusted_host_policy_found = False
    for route_list in walk_route_lists(servers):
        route_text = json.dumps(route_list)
        if "X-Aperture-Origin-Secret" not in route_text:
            continue
        if "X-Aperture-Studio-Edge" not in route_text:
            continue
        denial_indexes = [
            index
            for index, route in enumerate(route_list)
            if route_has_denial(route)
        ]
        proxy_indexes = [
            index
            for index, route in enumerate(route_list)
            if route_has_proxy(route) and not route_is_guarded_media_proxy(route)
        ]
        propagation_indexes = [
            index
            for index, route in enumerate(route_list)
            if route_propagates_trusted_public_host(route)
        ]
        if denial_indexes and proxy_indexes and max(denial_indexes) < min(proxy_indexes):
            ordered_policy_found = True
        if (
            denial_indexes
            and propagation_indexes
            and proxy_indexes
            and max(denial_indexes) < min(propagation_indexes) < min(proxy_indexes)
        ):
            trusted_host_policy_found = True
    if not ordered_policy_found:
        raise ValueError("Caddy denial matchers do not precede application proxy routes")
    if not trusted_host_policy_found:
        raise ValueError(
            "trusted public-host propagation is missing or outside the admitted proxy boundary"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    validate(json.loads(args.input.read_text()))
    print("Caddy origin and private Studio admission policy is valid.")


if __name__ == "__main__":
    main()
