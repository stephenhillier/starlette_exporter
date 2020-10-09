import pytest

from prometheus_client import REGISTRY
from starlette.applications import Starlette
from starlette.testclient import TestClient
from starlette.responses import JSONResponse
from starlette.exceptions import HTTPException

import starlette_exporter
from starlette_exporter import PrometheusMiddleware, handle_metrics


@pytest.fixture
def testapp():
    """ create a test app with various endpoints for the test scenarios """

    # unregister all the collectors before we start
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)

    PrometheusMiddleware._metrics = {}

    def _testapp(**middleware_options):
        app = Starlette()
        app.add_middleware(starlette_exporter.PrometheusMiddleware, **middleware_options)
        app.add_route("/metrics", handle_metrics)

        @app.route("/200")
        @app.route("/200/{test_param}")
        def normal_response(request):
            return JSONResponse({"message": "Hello World"})

        @app.route("/500")
        @app.route("/500/{test_param}")
        async def error(request):
            raise HTTPException(status_code=500, detail="this is a test error")

        @app.route("/unhandled")
        @app.route("/unhandled/{test_param}")
        async def unhandled(request):
            test_dict = {"yup": 123}
            return JSONResponse({"message": test_dict["value_error"]})

        return app
    return _testapp


class TestMiddleware:
    @pytest.fixture
    def client(self, testapp):
        return TestClient(testapp())

    def test_200(self, client):
        """ test that requests appear in the counter """
        client.get('/200')
        metrics = client.get('/metrics').content.decode()
        assert (
            """starlette_requests_total{app_name="starlette",method="GET",path="/200",status_code="200"} 1.0"""
            in metrics
        )

    def test_500(self, client):
        """ test that a handled exception (HTTPException) gets logged in the requests counter """

        client.get('/500')
        metrics = client.get('/metrics').content.decode()

        assert (
            """starlette_requests_total{app_name="starlette",method="GET",path="/500",status_code="500"} 1.0"""
            in metrics
        )

    def test_unhandled(self, client):
        """ test that an unhandled exception still gets logged in the requests counter """
        try:
            client.get('/unhandled')
        except:
            pass
        metrics = client.get('/metrics').content.decode()

        assert (
            """starlette_requests_total{app_name="starlette",method="GET",path="/unhandled",status_code="500"} 1.0"""
            in metrics
        )

    def test_histogram(self, client):
        """ test that histogram buckets appear after making requests """

        client.get('/200')
        client.get('/500')
        try:
            client.get('/unhandled')
        except:
            pass

        metrics = client.get('/metrics').content.decode()

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

    def test_app_name(self, testapp):
        """ test that app_name label is populated correctly """
        client = TestClient(testapp(app_name="testing"))

        client.get('/200')
        metrics = client.get('/metrics').content.decode()
        assert (
            """starlette_requests_total{app_name="testing",method="GET",path="/200",status_code="200"} 1.0"""
            in metrics
        )

    def test_prefix(self, testapp):
        """ test that metric prefixes work """
        client = TestClient(testapp(prefix="myapp"))

        client.get('/200')
        metrics = client.get('/metrics').content.decode()
        assert (
            """myapp_requests_total{app_name="starlette",method="GET",path="/200",status_code="200"} 1.0"""
            in metrics
        )

    def test_multi_init(self, testapp):
        """ test that the middleware is happy being initialised multiple times """
        # newer starlette versions do this
        # prometheus doesn't like the same metric being registered twice.
        PrometheusMiddleware(None)
        PrometheusMiddleware(None)

    def test_multi_prefix(self, testapp):
        """ test that two collecting apps don't clash """
        client1 = TestClient(testapp(prefix="app1"))
        client2 = TestClient(testapp(prefix="app2"))

        client1.get('/200')
        client2.get('/200')

        # both will return the same metrics though
        metrics1 = client1.get('/metrics').content.decode()
        metrics2 = client2.get('/metrics').content.decode()

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


class TestMiddlewareGroupedPaths:
    """ tests for group_paths option (using named parameters to group endpoint metrics with path params together) """

    @pytest.fixture
    def client(self, testapp):
        return TestClient(testapp(group_paths=True))

    def test_200(self, client):
        """ test that requests appear in the counter """
        client.get('/200/111')
        metrics = client.get('/metrics').content.decode()

        assert (
            """starlette_requests_total{app_name="starlette",method="GET",path="/200/{test_param}",status_code="200"} 1.0"""
            in metrics
        )

    def test_500(self, client):
        """ test that a handled exception (HTTPException) gets logged in the requests counter """

        client.get('/500/1111')
        metrics = client.get('/metrics').content.decode()

        assert (
            """starlette_requests_total{app_name="starlette",method="GET",path="/500/{test_param}",status_code="500"} 1.0"""
            in metrics
        )

    def test_unhandled(self, client):
        """ test that an unhandled exception still gets logged in the requests counter """
        try:
            client.get('/unhandled/11111')
        except:
            pass
        metrics = client.get('/metrics').content.decode()

        assert (
            """starlette_requests_total{app_name="starlette",method="GET",path="/unhandled/{test_param}",status_code="500"} 1.0"""
            in metrics
        )

    def test_404(self, client):
        """ test that a 404 is handled properly, even though the path won't be matched """
        try:
            client.get('/not_found/11111')
        except:
            pass
        metrics = client.get('/metrics').content.decode()

        assert (
            """starlette_requests_total{app_name="starlette",method="GET",path="/not_found/11111",status_code="404"} 1.0"""
            in metrics
        )

    def test_histogram(self, client):
        """ test that histogram buckets appear after making requests """

        client.get('/200/1')
        client.get('/500/12')
        try:
            client.get('/unhandled/111')
        except:
            pass

        metrics = client.get('/metrics').content.decode()

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
