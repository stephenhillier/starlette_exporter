""" Middleware for exporting Prometheus metrics using Starlette """
import time
from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from logging import getLogger

logger = getLogger("exporter")


REQUEST_TIME = Histogram(
    "starlette_request_duration_seconds",
    "HTTP request duration, in seconds",
    ("method", "path", "status_code", "app_name"),
)


REQUEST_COUNT = Counter(
    "starlette_requests_total",
    "Total HTTP requests",
    ("method", "path", "status_code", "app_name"),
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """ Middleware that collects Prometheus metrics for each request.
        Use in conjuction with the Prometheus exporter endpoint handler.
    """
    def __init__(self, app: ASGIApp, group_paths: bool = False, app_name: str = "starlette"):
        super().__init__(app)
        self.group_paths = group_paths
        self.app_name = app_name

    async def dispatch(self, request, call_next):
        method = request.method
        path = request.url.path
        begin = time.time()

        # Default status code used when the application does not return a valid response
        # or an unhandled exception occurs.
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code

        except Exception as e:
            raise e

        finally:
            # group_paths enables returning the original router path (with url param names)
            # the second check is to ensure that an endpoint was matched before trying to determine the name.
            if self.group_paths and request.scope.get('endpoint', None) and request.scope.get('router', None):
                try:
                    path = [route for route in request.scope['router'].routes if route.endpoint == request.scope['endpoint']][0].path
                except Exception as e:
                    logger.error(e)

            end = time.time()

            labels = [method, path, status_code, self.app_name]

            REQUEST_COUNT.labels(*labels).inc()
            REQUEST_TIME.labels(*labels).observe(end - begin)

        return response
