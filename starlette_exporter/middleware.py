""" Middleware for exporting Prometheus metrics using Starlette """
import time
from logging import getLogger

from prometheus_client import Counter, Histogram
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send


logger = getLogger("exporter")


class PrometheusMiddleware:
    """ Middleware that collects Prometheus metrics for each request.
        Use in conjuction with the Prometheus exporter endpoint handler.
    """
    _metrics = {}

    def __init__(
        self, app: ASGIApp, group_paths: bool = False, app_name: str = "starlette",
        prefix="starlette", buckets=None
    ):
        self.app = app
        self.group_paths = group_paths
        self.app_name = app_name
        self.prefix = prefix
        self.kwargs = {}
        if buckets is not None:
            self.kwargs['buckets'] = buckets

    # Starlette initialises middleware multiple times, so store metrics on the class
    @property
    def request_count(self):
        metric_name = f"{self.prefix}_requests_total"
        if metric_name not in PrometheusMiddleware._metrics:
            PrometheusMiddleware._metrics[metric_name] = Counter(
                metric_name,
                "Total HTTP requests",
                ("method", "path", "status_code", "app_name"),
            )
        return PrometheusMiddleware._metrics[metric_name]

    @property
    def request_time(self):
        metric_name = f"{self.prefix}_request_duration_seconds"
        if metric_name not in PrometheusMiddleware._metrics:
            PrometheusMiddleware._metrics[metric_name] = Histogram(
                metric_name,
                "HTTP request duration, in seconds",
                ("method", "path", "status_code", "app_name"),
                **self.kwargs,
            )
        return PrometheusMiddleware._metrics[metric_name]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ["http"]:
            await self.app(scope, receive, send)
            return

        request = Request(scope)

        method = request.method
        path = request.url.path
        begin = time.perf_counter()

        # Default status code used when the application does not return a valid response
        # or an unhandled exception occurs.
        status_code = 500

        async def wrapped_send(message: Message) -> None:
            if message['type'] == 'http.response.start':
                nonlocal status_code
                status_code = message['status']

            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        finally:
            # group_paths enables returning the original router path (with url param names)
            # for example, when using this option, requests to /api/product/1 and /api/product/3
            # will both be grouped under /api/product/{product_id}. See the README for more info.
            if (
                self.group_paths
                and request.scope.get('endpoint', None)
                and request.scope.get('router', None)
            ):
                try:
                    # try to match the request scope's handler function against one of handlers in the app's router.
                    # if a match is found, return the path used to mount the handler (e.g. api/product/{product_id}).
                    path = [
                        route
                        for route in request.scope['router'].routes
                        if (
                            hasattr(route, 'endpoint')
                            and route.endpoint == request.scope['endpoint']
                        )
                        # for endpoints handled by another app, like fastapi.staticfiles.StaticFiles,
                        # check if the request endpoint matches a mounted app.
                        or (
                            hasattr(route, 'app')
                            and route.app == request.scope['endpoint']
                        )
                    ][0].path
                except IndexError:
                    # no route matched.
                    # this can happen for routes that don't have an endpoint function.
                    pass
                except Exception as e:
                    logger.error(e)

            end = time.perf_counter()

            labels = [method, path, status_code, self.app_name]

            self.request_count.labels(*labels).inc()
            self.request_time.labels(*labels).observe(end - begin)
