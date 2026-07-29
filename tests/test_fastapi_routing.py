import asyncio

import pytest
from prometheus_client import REGISTRY, generate_latest

fastapi = pytest.importorskip("fastapi")
fastapi_version = tuple(int(part) for part in fastapi.__version__.split(".")[:2])

from fastapi import APIRouter, FastAPI
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Mount, Route

from starlette_exporter import PrometheusMiddleware
from starlette_exporter.middleware import get_matching_route_path


@pytest.fixture
def isolated_metrics_registry():
    existing_collectors = set(REGISTRY._collector_to_names)
    existing_metrics = PrometheusMiddleware._metrics
    PrometheusMiddleware._metrics = {}
    try:
        yield
    finally:
        for collector in set(REGISTRY._collector_to_names) - existing_collectors:
            REGISTRY.unregister(collector)
        PrometheusMiddleware._metrics = existing_metrics


async def make_request(app, path):
    request_sent = False
    response_status = None

    async def receive():
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        nonlocal response_status
        if message["type"] == "http.response.start":
            response_status = message["status"]

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver")],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }

    await app(scope, receive, send)
    return response_status


async def starlette_endpoint(request):
    return Response()


def http_scope(path):
    return {
        "type": "http",
        "method": "GET",
        "path": path,
        "root_path": "",
        "headers": [(b"host", b"testserver")],
    }


def test_nested_included_router_path_is_grouped(isolated_metrics_registry):
    items = APIRouter()

    @items.get("/{item_id}")
    async def get_item(item_id: str):
        return {"item_id": item_id}

    api = APIRouter()
    api.include_router(items, prefix="/items")

    app = FastAPI()
    app.include_router(api, prefix="/api")
    app.add_middleware(
        PrometheusMiddleware,
        group_paths=True,
        prefix="fastapi_routing",
    )

    status_code = asyncio.run(make_request(app, "/api/items/123"))
    metrics = generate_latest(REGISTRY).decode()

    assert status_code == 200
    assert (
        'fastapi_routing_requests_total{app_name="starlette",'
        'method="GET",path="/api/items/{item_id}",status_code="200"} 1.0'
        in metrics
    )


def test_included_starlette_route_path_is_grouped():
    router = APIRouter(
        routes=[Route("/users/{user_id}", starlette_endpoint)],
    )
    app = FastAPI()
    app.include_router(router, prefix="/api")

    assert (
        get_matching_route_path(http_scope("/api/users/123"), app.routes)
        == "/api/users/{user_id}"
    )


@pytest.mark.skipif(
    fastapi_version < (0, 137),
    reason="FastAPI <0.137 does not retain mounts from included routers",
)
def test_included_mount_descends_into_child_routes():
    mounted_app = Starlette(
        routes=[Route("/users/{user_id}", starlette_endpoint)],
    )
    router = APIRouter(
        routes=[Mount("/sub", app=mounted_app)],
    )
    app = FastAPI()
    app.include_router(router, prefix="/api")

    assert (
        get_matching_route_path(http_scope("/api/sub/users/123"), app.routes)
        == "/api/sub/users/{user_id}"
    )
