from typing import Any, Dict

from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Host, Match, Mount, Route

from starlette_exporter.middleware import get_matching_route_path


async def endpoint(request):
    return Response()


def http_scope(path, host="example.com"):
    return {
        "type": "http",
        "method": "GET",
        "path": path,
        "root_path": "",
        "headers": [(b"host", host.encode())],
    }


def test_host_descends_into_child_routes():
    hosted_app = Starlette(routes=[Route("/users/{user_id}", endpoint)])
    routes = [Host("example.com", app=hosted_app)]

    assert (
        get_matching_route_path(http_scope("/users/123"), routes)
        == "/users/{user_id}"
    )


def test_host_rejects_wrong_host():
    hosted_app = Starlette(routes=[Route("/users/{user_id}", endpoint)])
    routes = [Host("example.com", app=hosted_app)]

    assert get_matching_route_path(
        http_scope("/users/123", host="other.example.com"), routes
    ) is None


def test_host_rejects_unmatched_child_without_using_literal_path():
    hosted_app = Starlette(routes=[Route("/users/{user_id}", endpoint)])
    routes = [Host("example.com", app=hosted_app)]

    assert get_matching_route_path(http_scope("/unhandled/123"), routes) is None


def test_host_nested_under_mount_includes_mount_prefix():
    hosted_app = Starlette(routes=[Route("/users/{user_id}", endpoint)])
    routes = [
        Mount("/api", routes=[Host("example.com", app=hosted_app)]),
    ]

    assert (
        get_matching_route_path(http_scope("/api/users/123"), routes)
        == "/api/users/{user_id}"
    )


class HeaderRoute(Route):
    def matches(self, scope: Dict[str, Any]):
        match, child_scope = super().matches(scope)
        if match != Match.NONE and (b"x-route", b"preferred") not in scope["headers"]:
            return Match.NONE, {}
        return match, child_scope


def test_route_subclass_matching_override_is_honored():
    routes = [
        HeaderRoute("/items/{preferred}", endpoint),
        Route("/items/{fallback}", endpoint),
    ]

    assert (
        get_matching_route_path(http_scope("/items/value"), routes)
        == "/items/{fallback}"
    )
    preferred_scope = http_scope("/items/value")
    preferred_scope["headers"].append((b"x-route", b"preferred"))
    assert (
        get_matching_route_path(preferred_scope, routes)
        == "/items/{preferred}"
    )
