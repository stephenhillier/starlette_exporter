import time
from http import HTTPStatus
from pathlib import Path

import pytest
from prometheus_client import REGISTRY
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

import starlette_exporter
from starlette_exporter import (handle_metrics, handle_openmetrics, PrometheusMiddleware)

BASE_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture
def testapp():
    """create a test app with various endpoints for the test scenarios"""

    # unregister all the collectors before we start
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)

    PrometheusMiddleware._metrics = {}

    def _testapp(**middleware_options):
        app = Starlette()
        app.add_middleware(
            starlette_exporter.PrometheusMiddleware, **middleware_options
        )
        app.add_route("/metrics", handle_metrics)
        app.add_route("/openmetrics", handle_openmetrics)

        def normal_response(request):
            return JSONResponse({"message": "Hello World"})

        app.add_route("/200", normal_response)
        app.add_route(
            "/200/{test_param}", normal_response, methods=["GET", "POST", "OPTIONS"]
        )

        def httpstatus_response(request):
            """
            Returns a JSON Response using status_code = HTTPStatus.OK if the param is set to OK
            otherewise it returns a JSON response with status_code = 200
            """
            if request.path_params["test_param"] == "OK":
                return Response(status_code=HTTPStatus.OK)
            else:
                return Response(status_code=200)

        app.add_route(
            "/200_or_httpstatus/{test_param}",
            httpstatus_response,
            methods=["GET", "OPTIONS"],
        )

        async def error(request):
            raise HTTPException(status_code=500, detail="this is a test error")

        app.add_route("/500", error)
        app.add_route("/500/{test_param}", error)

        async def unhandled(request):
            test_dict = {"yup": 123}
            return JSONResponse({"message": test_dict["value_error"]})

        app.add_route("/unhandled", unhandled)
        app.add_route("/unhandled/{test_param}", unhandled)

        async def background(request):
            def backgroundtask():
                time.sleep(0.1)

            task = BackgroundTask(backgroundtask)
            return JSONResponse({"message": "task started"}, background=task)

        app.add_route("/background", background)

        def healthcheck(request):
            return JSONResponse({"message": "Healthcheck route"})

        app.add_route("/health", healthcheck)

        # testing routes added using Mount
        async def test_mounted_function(request):
            return JSONResponse({"message": "Hello World"})

        async def test_mounted_function_param(request):
            return JSONResponse({"message": request.path_params.get("item")})

        mounted_routes = Mount(
            "/",
            routes=[
                Route("/test/{item}", test_mounted_function_param, methods=["GET"]),
                Route("/test", test_mounted_function),
            ],
        )

        app.mount("/mounted", mounted_routes)
        app.mount("/static", app=StaticFiles(directory=BASE_DIR / "tests/static"), name="static")
        return app

    return _testapp
