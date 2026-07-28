import asyncio

import pytest
from prometheus_client import REGISTRY, generate_latest

fastapi = pytest.importorskip("fastapi")

from fastapi import APIRouter, FastAPI

from starlette_exporter import PrometheusMiddleware


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
