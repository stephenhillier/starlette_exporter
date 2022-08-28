import time
from http import HTTPStatus

import aiofiles
import pytest
from prometheus_client import REGISTRY
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Mount, Route, Router
from starlette.staticfiles import StaticFiles
from starlette.testclient import TestClient

import starlette_exporter
from starlette_exporter import PrometheusMiddleware, handle_metrics, from_header
from starlette_exporter.optional_metrics import response_body_size, request_body_size


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

        @app.route("/200")
        @app.route("/200/{test_param}", methods=["GET", "POST", "OPTIONS"])
        def normal_response(request):
            return JSONResponse({"message": "Hello World"})

        @app.route("/200_or_httpstatus/{test_param}", methods=["GET", "OPTIONS"])
        def httpstatus_respnse(request):
            """
            Returns a JSON Response using status_code = HTTPStatus.OK if the param is set to OK
            otherewise it returns a JSON response with status_code = 200
            """
            if request.path_params["test_param"] == "OK":
                return Response(status_code=HTTPStatus.OK)
            else:
                return Response(status_code=200)

        @app.route("/200_with_httpstatus/{test_param}", methods=["GET", "OPTIONS"])
        def httpstatus_respnse(request):
            """
            Returns a JSON Response using status_code = HTTPStatus.OK if the param is set to OK
            otherewise it returns a JSON response with status_code = 200
            """
            if request.path_params["test_param"] == "OK":
                return Response(status_code=HTTPStatus.OK)
            else:
                return Response(status_code=200)

        @app.route("/500")
        @app.route("/500/{test_param}")
        async def error(request):
            raise HTTPException(status_code=500, detail="this is a test error")

        @app.route("/unhandled")
        @app.route("/unhandled/{test_param}")
        async def unhandled(request):
            test_dict = {"yup": 123}
            return JSONResponse({"message": test_dict["value_error"]})

        @app.route("/test_methods", methods=["POST"])
        async def test_methods_post(request):
            return JSONResponse({"message": "Hello World"})

        @app.route("/test_methods", methods=["GET"])
        async def test_methods_get(request):
            return JSONResponse({"message": "Hello World"})

        @app.route("/background")
        async def background(request):
            def backgroundtask():
                time.sleep(0.1)

            task = BackgroundTask(backgroundtask)
            return JSONResponse({"message": "task started"}, background=task)

        @app.route("/health")
        def healthcheck(request):
            return JSONResponse({"message": "Healthcheck route"})

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
        app.mount("/static", app=StaticFiles(directory="tests/static"), name="static")
        return app

    return _testapp


class TestMiddleware:
    @pytest.fixture
    def client(self, testapp):
        return TestClient(testapp())

    def test_200(self, client):
        """test that requests appear in the counter"""
        client.get("/200")
        metrics = client.get("/metrics").content.decode()
        assert (
            """starlette_requests_total{app_name="starlette",method="GET",path="/200",status_code="200"} 1.0"""
            in metrics
        )

    def test_500(self, client):
        """test that a handled exception (HTTPException) gets logged in the requests counter"""

        client.get("/500")
        metrics = client.get("/metrics").content.decode()

        assert (
            """starlette_requests_total{app_name="starlette",method="GET",path="/500",status_code="500"} 1.0"""
            in metrics
        )

    def test_unhandled(self, client):
        """test that an unhandled exception still gets logged in the requests counter"""
        try:
            client.get("/unhandled")
        except:
            pass
        metrics = client.get("/metrics").content.decode()

        assert (
            """starlette_requests_total{app_name="starlette",method="GET",path="/unhandled",status_code="500"} 1.0"""
            in metrics
        )

    def test_histogram(self, client):
        """test that histogram buckets appear after making requests"""

        client.get("/200")
        client.get("/500")
        try:
            client.get("/unhandled")
        except:
            pass

        metrics = client.get("/metrics").content.decode()

        assert (
            """starlette_request_duration_seconds_bucket{app_name="starlette",le="0.005",method="GET",path="/200",status_code="200"}"""
            in metrics
        )
        assert (
            """starlette_request_duration_seconds_bucket{app_name="starlette",le="0.005",method="GET",path="/500",status_code="500"}"""
            in metrics
        )
        assert (
            """starlette_request_duration_seconds_bucket{app_name="starlette",le="0.005",method="GET",path="/unhandled",status_code="500"}"""
            in metrics
        )

    def test_histogram_custom_buckets(self, testapp):
        """test that custom histogram buckets appear after making requests"""

        buckets = (10, 20, 30, 40, 50)
        client = TestClient(testapp(buckets=buckets))
        client.get("/200")
        client.get("/500")
        try:
            client.get("/unhandled")
        except:
            pass

        metrics = client.get("/metrics").content.decode()

        assert (
            """starlette_request_duration_seconds_bucket{app_name="starlette",le="50.0",method="GET",path="/200",status_code="200"}"""
            in metrics
        )
        assert (
            """starlette_request_duration_seconds_bucket{app_name="starlette",le="50.0",method="GET",path="/500",status_code="500"}"""
            in metrics
        )
        assert (
            """starlette_request_duration_seconds_bucket{app_name="starlette",le="50.0",method="GET",path="/unhandled",status_code="500"}"""
            in metrics
        )

    def test_app_name(self, testapp):
        """test that app_name label is populated correctly"""
        client = TestClient(testapp(app_name="testing"))

        client.get("/200")
        metrics = client.get("/metrics").content.decode()
        assert (
            """starlette_requests_total{app_name="testing",method="GET",path="/200",status_code="200"} 1.0"""
            in metrics
        )

    def test_filter_unhandled_paths(self, testapp):
        """test that app_name label is populated correctly"""
        client = TestClient(testapp(filter_unhandled_paths=True))

        client.get("/this_path_does_not_exist")
        metrics = client.get("/metrics").content.decode()
        assert "this_path_does_not_exist" not in metrics

    def test_mounted_path(self, testapp):
        """test that mounted paths appear even when filter_unhandled_paths is True"""
        client = TestClient(testapp(filter_unhandled_paths=True))
        client.get("/mounted/test")
        metrics = client.get("/metrics").content.decode()
        assert (
            """starlette_requests_total{app_name="starlette",method="GET",path="/mounted/test",status_code="200"} 1.0"""
            in metrics
        )

    def test_mounted_path_invalid_method(self, testapp):
        """test incorrect method when filter_unhandled_paths is True"""
        client = TestClient(testapp(filter_unhandled_paths=True))
        client.post("/mounted/test")
        metrics = client.get("/metrics").content.decode()
        assert (
            """starlette_requests_total{app_name="starlette",method="POST",path="/mounted/test",status_code="405"} 1.0"""
            in metrics
        )

    def test_mounted_path_with_param(self, testapp):
        """test that mounted paths appear even when filter_unhandled_paths is True
        this test uses a path param that needs to be found within the mounted route.
        """
        client = TestClient(testapp(filter_unhandled_paths=True, group_paths=True))
        client.get("/mounted/test/123")
        metrics = client.get("/metrics").content.decode()
        assert (
            """starlette_requests_total{app_name="starlette",method="GET",path="/mounted/test/{item}",status_code="200"} 1.0"""
            in metrics
        )

    def test_mounted_path_unhandled(self, testapp):
        """test an unhandled path that will be partially matched at the mounted base path"""
        client = TestClient(testapp(filter_unhandled_paths=True))
        client.get("/mounted/unhandled/123")
        metrics = client.get("/metrics").content.decode()
        assert """path="/mounted/unhandled""" not in metrics

        assert """path="/mounted""" not in metrics

    def test_mounted_path_unhandled(self, testapp):
        """test an unhandled path that will be partially matched at the mounted base path"""
        client = TestClient(testapp(filter_unhandled_paths=True, group_paths=True))
        client.get("/mounted/unhandled/123")
        metrics = client.get("/metrics").content.decode()
        assert """path="/mounted/unhandled""" not in metrics

        assert """path="/mounted""" not in metrics

    def test_staticfiles_path(self, testapp):
        """test a static file path"""
        client = TestClient(testapp(filter_unhandled_paths=True))
        client.get("/static/test.txt")
        metrics = client.get("/metrics").content.decode()
        assert """path="/static/test.txt""" in metrics

    def test_prefix(self, testapp):
        """test that metric prefixes work"""
        client = TestClient(testapp(prefix="myapp"))

        client.get("/200")
        metrics = client.get("/metrics").content.decode()
        assert (
            """myapp_requests_total{app_name="starlette",method="GET",path="/200",status_code="200"} 1.0"""
            in metrics
        )

    def test_multi_init(self, testapp):
        """test that the middleware is happy being initialised multiple times"""
        # newer starlette versions do this
        # prometheus doesn't like the same metric being registered twice.
        PrometheusMiddleware(None)
        PrometheusMiddleware(None)

    def test_multi_prefix(self, testapp):
        """test that two collecting apps don't clash"""
        client1 = TestClient(testapp(prefix="app1"))
        client2 = TestClient(testapp(prefix="app2"))

        client1.get("/200")
        client2.get("/200")

        # both will return the same metrics though
        metrics1 = client1.get("/metrics").content.decode()
        metrics2 = client2.get("/metrics").content.decode()

        assert (
            """app1_requests_total{app_name="starlette",method="GET",path="/200",status_code="200"} 1.0"""
            in metrics1
        )
        assert (
            """app2_requests_total{app_name="starlette",method="GET",path="/200",status_code="200"} 1.0"""
            in metrics1
        )
        assert (
            """app1_requests_total{app_name="starlette",method="GET",path="/200",status_code="200"} 1.0"""
            in metrics2
        )
        assert (
            """app2_requests_total{app_name="starlette",method="GET",path="/200",status_code="200"} 1.0"""
            in metrics2
        )

    def test_requests_in_progress(self, client):
        """test that the requests_in_progress metric (a gauge) is incremented after one request.
        This test is fairly trivial and doesn't cover decrementing at the end of the request.
        TODO: create a second asyncronous request and check that the counter is incremented
        multiple times (and decremented back to zero when all requests done).
        """

        metrics = client.get("/metrics").content.decode()
        assert (
            """starlette_requests_in_progress{app_name="starlette",method="GET"} 1.0"""
            in metrics
        )

        # try a second time as an alternate way to check that the requests_in_progress metric
        # was decremented at the end of the first request.  This test could be improved, but
        # at the very least, it checks that the gauge wasn't incremented multiple times without
        # also being decremented.
        metrics = client.get("/metrics").content.decode()
        assert (
            """starlette_requests_in_progress{app_name="starlette",method="GET"} 1.0"""
            in metrics
        )

    def test_skip_paths(self, testapp):
        """test that requests doesn't appear in the counter"""
        client = TestClient(testapp(skip_paths=["/health"]))
        client.get("/health")
        metrics = client.get("/metrics").content.decode()
        assert """path="/health""" not in metrics


class TestMiddlewareGroupedPaths:
    """tests for group_paths option (using named parameters to group endpoint metrics with path params together)"""

    @pytest.fixture
    def client(self, testapp):
        return TestClient(testapp(group_paths=True))

    def test_200(self, client):
        """test that metrics are grouped by endpoint"""
        client.get("/200/111")
        metrics = client.get("/metrics").content.decode()

        assert (
            """starlette_requests_total{app_name="starlette",method="GET",path="/200/{test_param}",status_code="200"} 1.0"""
            in metrics
        )

    def test_200_options(self, client):
        """test that metrics are grouped by endpoint"""
        client.options("/200/111")
        metrics = client.get("/metrics").content.decode()

        assert (
            """starlette_requests_total{app_name="starlette",method="OPTIONS",path="/200/{test_param}",status_code="200"} 1.0"""
            in metrics
        )

        assert """method="OPTIONS",path="/200/111""" not in metrics

    def test_500(self, client):
        """test that a handled exception (HTTPException) gets logged in the requests counter"""

        client.get("/500/1111")
        metrics = client.get("/metrics").content.decode()

        assert (
            """starlette_requests_total{app_name="starlette",method="GET",path="/500/{test_param}",status_code="500"} 1.0"""
            in metrics
        )

    def test_unhandled(self, client):
        """test that an unhandled exception still gets logged in the requests counter"""
        try:
            client.get("/unhandled/11111")
        except:
            pass
        metrics = client.get("/metrics").content.decode()

        assert (
            """starlette_requests_total{app_name="starlette",method="GET",path="/unhandled/{test_param}",status_code="500"} 1.0"""
            in metrics
        )

    def test_staticfiles_path(self, testapp):
        """test a static file path, with group_paths=True"""
        client = TestClient(testapp(filter_unhandled_paths=True, group_paths=True))
        client.get("/static/test.txt")
        metrics = client.get("/metrics").content.decode()
        assert 'path="/static"' in metrics

    def test_404(self, client):
        """test that a 404 is handled properly, even though the path won't be matched"""
        try:
            client.get("/not_found/11111")
        except:
            pass
        metrics = client.get("/metrics").content.decode()

        assert (
            """starlette_requests_total{app_name="starlette",method="GET",path="/not_found/11111",status_code="404"} 1.0"""
            in metrics
        )

    def test_methods_post(self, client):
        """test that an endpoint that is registered for multiple HTTP methods works (POST)"""
        try:
            client.post("/test_methods")
        except:
            pass
        metrics = client.get("/metrics").content.decode()

        assert (
            """starlette_requests_total{app_name="starlette",method="POST",path="/test_methods",status_code="200"} 1.0"""
            in metrics
        )

    def test_methods_get(self, client):
        """test that an endpoint that is registered for multiple HTTP methods works (POST)"""
        try:
            client.get("/test_methods")
        except:
            pass
        metrics = client.get("/metrics").content.decode()

        assert (
            """starlette_requests_total{app_name="starlette",method="GET",path="/test_methods",status_code="200"} 1.0"""
            in metrics
        )

    def test_methods_invalid_method(self, client):
        """test that an endpoint that is registered for multiple HTTP methods works (POST)"""
        try:
            client.put("/test_methods")
        except:
            pass
        metrics = client.get("/metrics").content.decode()

        assert (
            """starlette_requests_total{app_name="starlette",method="PUT",path="/test_methods",status_code="405"} 1.0"""
            in metrics
        )

    def test_methods_arbitrary_method(self, client):
        """test that the `method` label won't accept arbitrary junk data"""
        try:
            client.request("ZOUNDS", url="/test_methods")
        except:
            pass
        metrics = client.get("/metrics").content.decode()

        assert (
            """starlette_requests_total{app_name="starlette",method="ZOUNDS",path="/test_methods",status_code="405"} 1.0"""
            not in metrics
        )

    def test_histogram(self, client):
        """test that histogram buckets appear after making requests"""

        client.get("/200/1")
        client.get("/500/12")
        try:
            client.get("/unhandled/111")
        except:
            pass

        metrics = client.get("/metrics").content.decode()

        assert (
            """starlette_request_duration_seconds_bucket{app_name="starlette",le="0.005",method="GET",path="/200/{test_param}",status_code="200"}"""
            in metrics
        )
        assert (
            """starlette_request_duration_seconds_bucket{app_name="starlette",le="0.005",method="GET",path="/500/{test_param}",status_code="500"}"""
            in metrics
        )
        assert (
            """starlette_request_duration_seconds_bucket{app_name="starlette",le="0.005",method="GET",path="/unhandled/{test_param}",status_code="500"}"""
            in metrics
        )


class TestBackgroundTasks:
    """tests for ensuring the middleware handles requests involving background tasks"""

    @pytest.fixture
    def client(self, testapp):
        return TestClient(testapp())

    def test_background_task_endpoint(self, client):
        client.get("/background")

        metrics = client.get("/metrics").content.decode()
        background_metric = [
            s
            for s in metrics.split("\n")
            if (
                "starlette_request_duration_seconds_sum" in s
                and 'path="/background"' in s
            )
        ]
        duration = background_metric[0].split("} ")[1]

        # the test function contains a 0.1 second background task. Ensure the metric records the response
        # as smaller than 0.1 second.
        assert float(duration) < 0.1


class TestOptionalMetrics:
    """tests for optional additional metrics
    thanks to Stephen
    """

    @pytest.fixture
    def client(self, testapp):
        return TestClient(
            testapp(optional_metrics=[response_body_size, request_body_size])
        )

    def test_response_body_size(self, client):
        client.get("/200")

        metrics = client.get("/metrics").content.decode()
        response_size_metric = [
            s
            for s in metrics.split("\n")
            if ("starlette_response_body_bytes_total" in s and 'path="/200"' in s)
        ]
        response_size = response_size_metric[0].split("} ")[1]
        assert float(response_size) > 0.1

    def test_receive_body_size(self, client):
        client.post("/200", json={"test_post": ["d", "a"]})

        metrics = client.get("/metrics").content.decode()
        rec_size_metric = [
            s
            for s in metrics.split("\n")
            if ("starlette_request_body_bytes_total" in s and 'path="/200"' in s)
        ]
        rec_size = rec_size_metric[0].split("} ")[1]
        assert float(rec_size) > 0.1


class TestAlwaysUseIntStatus:
    """Tests for always_use_int_status flag"""

    def test_200_with_always_use_int_status_set(self, testapp):
        """test that even though the endpoint resturns a response with HTTP status it is converted to 200"""
        client = TestClient(testapp(always_use_int_status=True))
        client.get("/200_or_httpstatus/OK")
        metrics = client.get("/metrics").content.decode()

        assert (
            """starlette_requests_total{app_name="starlette",method="GET",path="/200_or_httpstatus/OK",status_code="200"} 1.0"""
            in metrics
        ), metrics

    def test_200_HTTPStatusOK(self, testapp):
        """Test that status_code metric is HTTPStatus.OK if status_code=HTTPStatus.OK in the response
        and always_use_int_status is not set"""
        client = TestClient(testapp())
        client.get("/200_or_httpstatus/OK")
        metrics = client.get("/metrics").content.decode()

        assert (
            """starlette_requests_total{app_name="starlette",method="GET",path="/200_or_httpstatus/OK",status_code="HTTPStatus.OK"} 1.0"""
            in metrics
        ), metrics

    def test_200_always_use_int_status_set(self, testapp):
        """Test that status_code metric is 200 if status_code=200 in the response and always_use_int_status is set"""
        client = TestClient(testapp(always_use_int_status=True))
        client.get("/200")
        metrics = client.get("/metrics").content.decode()

        assert (
            """starlette_requests_total{app_name="starlette",method="GET",path="/200",status_code="200"} 1.0"""
            in metrics
        ), metrics


class TestDefaultLabels:
    """tests for the default labels option (`labels` argument on the middleware constructor)"""

    def test_str_default_labels(self, testapp):
        """test setting default labels with string values"""
        labels = {"foo": "bar", "hello": "world"}
        client = TestClient(testapp(labels=labels))
        client.get("/200")
        metrics = client.get("/metrics").content.decode()

        assert (
            """starlette_requests_total{app_name="starlette",foo="bar",hello="world",method="GET",path="/200",status_code="200"} 1.0"""
            in metrics
        ), metrics

    def test_callable_default_values(self, testapp):
        """test using callables for the default value"""

        # set up a callable that retrieves a header value from the request
        f = lambda x: x.headers.get("foo")

        labels = {"foo": f, "hello": "world"}

        client = TestClient(testapp(labels=labels))
        client.get("/200", headers={"foo": "bar"})
        metrics = client.get("/metrics").content.decode()

        assert (
            """starlette_requests_total{app_name="starlette",foo="bar",hello="world",method="GET",path="/200",status_code="200"} 1.0"""
            in metrics
        ), metrics

    def test_from_header(self, testapp):
        """test with the library-provided from_header function"""
        labels = {"foo": from_header("foo"), "hello": "world"}
        client = TestClient(testapp(labels=labels))
        client.get("/200", headers={"foo": "bar"})
        metrics = client.get("/metrics").content.decode()

        assert (
            """starlette_requests_total{app_name="starlette",foo="bar",hello="world",method="GET",path="/200",status_code="200"} 1.0"""
            in metrics
        ), metrics

    def test_from_header_allowed_values(self, testapp):
        """test with the library-provided from_header function"""
        labels = {
            "foo": from_header("foo", allowed_values=("bar", "baz")),
            "hello": "world",
        }
        client = TestClient(testapp(labels=labels))
        client.get("/200", headers={"foo": "bar"})
        metrics = client.get("/metrics").content.decode()

        assert (
            """starlette_requests_total{app_name="starlette",foo="bar",hello="world",method="GET",path="/200",status_code="200"} 1.0"""
            in metrics
        ), metrics

    def test_from_header_allowed_values_disallowed_value(self, testapp):
        """test with the library-provided from_header function"""
        labels = {
            "foo": from_header("foo", allowed_values=("bar", "baz")),
            "hello": "world",
        }
        client = TestClient(testapp(labels=labels))
        client.get("/200", headers={"foo": "zounds"})
        metrics = client.get("/metrics").content.decode()

        assert (
            """starlette_requests_total{app_name="starlette",foo="zounds",hello="world",method="GET",path="/200",status_code="200"} 1.0"""
            not in metrics
        ), metrics

        assert (
            """starlette_requests_total{app_name="starlette",foo="",hello="world",method="GET",path="/200",status_code="200"} 1.0"""
            in metrics
        ), metrics
