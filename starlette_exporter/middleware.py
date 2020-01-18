""" Middleware for exporting Prometheus metrics using Starlette """
import time
from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from logging import getLogger

logger = getLogger("exporter")

REQUEST_TIME = Histogram(
            'starlette_request_duration_seconds',
            'HTTP request duration, in seconds',
            ('method', 'path', 'status_code'),
        )

REQUEST_COUNT = Counter(
            'starlette_requests_total',
            'Total HTTP requests',
            ('method', 'path', 'status_code'),
        )

class PrometheusMiddleware(BaseHTTPMiddleware):
    """ Middleware that collects Prometheus metrics for each request.
        Use in conjuction with the Prometheus exporter endpoint handler.
    """



    def __init__(self, app: ASGIApp, group_paths: bool = False):
        super().__init__(app)
        self.group_paths = group_paths

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
            if self.group_paths and request.scope.get('endpoint', None):
                try:
                    path = [route for route in request.scope['router'].routes if route.endpoint == request.scope['endpoint']][0].path
                except Exception as e:
                    logger.error(e)

            end = time.time()

            REQUEST_COUNT.labels(method, path, status_code).inc()
            REQUEST_TIME.labels(method, path, status_code).observe(end - begin)

        return response
