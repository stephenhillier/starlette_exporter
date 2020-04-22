import pytest

from starlette.applications import Starlette
from starlette.testclient import TestClient
from starlette.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette_exporter import PrometheusMiddleware, handle_metrics


class TestMiddleware:
    @pytest.fixture
    def app(self):
        """ create a test app with various endpoints for the test scenarios """
        app = Starlette()
        app.add_middleware(PrometheusMiddleware)
        app.add_route("/metrics", handle_metrics)

        @app.route("/200")
        def normal_response(request):
            return JSONResponse({"message": "Hello World"})

        @app.route("/500")
        async def error(request):
            raise HTTPException(status_code=500, detail="this is a test error")
            
        @app.route("/unhandled")
        async def unhandled(request):
            test_dict = {"yup": 123}
            return JSONResponse({"message": test_dict["value_error"]})
        return app

    @pytest.fixture
    def client(self, app):
        return TestClient(app)

    def test_200(self, client):
        """ test that requests appear in the counter """
        client.get('/200')
        metrics = client.get('/metrics').content.decode()
        assert """starlette_requests_total{app_name="starlette",method="GET",path="/200",status_code="200"} 1.0""" in metrics
    
    def test_500(self, client):
        """ test that a handled exception (HTTPException) gets logged in the requests counter """

        client.get('/500')
        metrics = client.get('/metrics').content.decode()

        assert """starlette_requests_total{app_name="starlette",method="GET",path="/500",status_code="500"} 1.0""" in metrics
    
    def test_unhandled(self, client):
        """ test that an unhandled exception still gets logged in the requests counter """
        try:
            client.get('/unhandled')
        except:
            pass
        metrics = client.get('/metrics').content.decode()

        assert """starlette_requests_total{app_name="starlette",method="GET",path="/unhandled",status_code="500"} 1.0""" in metrics

    def test_histogram(self, client):
        """ test that histogram buckets appear after making requests """

        client.get('/200')
        client.get('/500')
        try:
            client.get('/unhandled')
        except: 
            pass

        metrics = client.get('/metrics').content.decode()

        assert """starlette_request_duration_seconds_bucket{app_name="starlette",le="0.005",method="GET",path="/200",status_code="200"}""" in metrics
        assert """starlette_request_duration_seconds_bucket{app_name="starlette",le="0.005",method="GET",path="/500",status_code="500"}""" in metrics
        assert """starlette_request_duration_seconds_bucket{app_name="starlette",le="0.005",method="GET",path="/unhandled",status_code="500"}""" in metrics


class TestMiddlewareGroupedPaths:
    """ tests for group_paths option (using named parameters to group endpoint metrics with path params together) """

    @pytest.fixture
    def app(self):
        """ create a test app with various endpoints for the test scenarios """
        app = Starlette()
        app.add_middleware(PrometheusMiddleware, group_paths=True)
        app.add_route("/metrics", handle_metrics)

        @app.route("/200/{test_param}")
        def normal_response(request):
            return JSONResponse({"message": "Hello World"})

        @app.route("/500/{test_param}")
        async def error(request):
            raise HTTPException(status_code=500, detail="this is a test error")
            
        @app.route("/unhandled/{test_param}")
        async def unhandled(request):
            test_dict = {"yup": 123}
            return JSONResponse({"message": test_dict["value_error"]})
        return app

    @pytest.fixture
    def client(self, app):
        return TestClient(app)

    def test_200(self, client):
        """ test that requests appear in the counter """
        client.get('/200/111')
        metrics = client.get('/metrics').content.decode()

        assert """starlette_requests_total{app_name="starlette",method="GET",path="/200/{test_param}",status_code="200"} 1.0""" in metrics
    
    def test_500(self, client):
        """ test that a handled exception (HTTPException) gets logged in the requests counter """

        client.get('/500/1111')
        metrics = client.get('/metrics').content.decode()

        assert """starlette_requests_total{app_name="starlette",method="GET",path="/500/{test_param}",status_code="500"} 1.0""" in metrics
    
    def test_unhandled(self, client):
        """ test that an unhandled exception still gets logged in the requests counter """
        try:
            client.get('/unhandled/11111')
        except:
            pass
        metrics = client.get('/metrics').content.decode()

        assert """starlette_requests_total{app_name="starlette",method="GET",path="/unhandled/{test_param}",status_code="500"} 1.0""" in metrics

    def test_404(self, client):
        """ test that a 404 is handled properly, even though the path won't be matched """
        try:
            client.get('/not_found/11111')
        except:
            pass
        metrics = client.get('/metrics').content.decode()

        assert """starlette_requests_total{app_name="starlette",method="GET",path="/not_found/11111",status_code="404"} 1.0""" in metrics


    def test_histogram(self, client):
        """ test that histogram buckets appear after making requests """

        client.get('/200/1')
        client.get('/500/12')
        try:
            client.get('/unhandled/111')
        except: 
            pass

        metrics = client.get('/metrics').content.decode()

        assert """starlette_request_duration_seconds_bucket{app_name="starlette",le="0.005",method="GET",path="/200/{test_param}",status_code="200"}""" in metrics
        assert """starlette_request_duration_seconds_bucket{app_name="starlette",le="0.005",method="GET",path="/500/{test_param}",status_code="500"}""" in metrics
        assert """starlette_request_duration_seconds_bucket{app_name="starlette",le="0.005",method="GET",path="/unhandled/{test_param}",status_code="500"}""" in metrics