""" Middleware for exporting Prometheus metrics using Starlette """
import os
import time
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST, REGISTRY, multiprocess, CollectorRegistry
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.endpoints import HTTPEndpoint
from starlette.responses import Response
from starlette.exceptions import HTTPException

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

    async def dispatch(self, request, call_next):
        
        method = request.method
        path = request.url.path
        begin = time.time()

        # Default status code for unhandled exceptions. Exceptions that are handled in the application
        # and raise a `starlette.exceptions.HTTPException` will return a valid response, and the status
        # code will be set accordingly. In other words, an exception is not expected here if the 
        # application code explicitly raises an HTTPException, but an unhandled ValueError will result
        # in an exception here. It's assumed that a 500 status code will be appropriate in that case.
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            raise e
        finally:
            end = time.time()
            REQUEST_COUNT.labels(method, path, status_code).inc()
            REQUEST_TIME.labels(method, path, status_code).observe(end - begin)

        return response


def handle_metrics(request):
    """ A handler to expose Prometheus metrics
        Example usage:

        ```
        app.add_middleware(PrometheusMiddleware)
        app.add_route("/metrics", handle_metrics)
        ```
    """
    registry = REGISTRY
    if 'prometheus_multiproc_dir' in os.environ:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    
    headers = {'Content-Type': CONTENT_TYPE_LATEST}
    return Response(generate_latest(), status_code=200, headers=headers)
