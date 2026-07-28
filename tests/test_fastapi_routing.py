import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi import APIRouter, FastAPI

from starlette_exporter.middleware import get_matching_route_path


def test_nested_included_router_path_is_grouped():
    items = APIRouter()

    @items.get("/{item_id}")
    async def get_item(item_id: str):
        return {"item_id": item_id}

    api = APIRouter()
    api.include_router(items, prefix="/items")

    app = FastAPI()
    app.include_router(api, prefix="/api")

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/items/123",
        "root_path": "",
        "headers": [],
    }

    assert get_matching_route_path(scope, app.routes) == "/api/items/{item_id}"
