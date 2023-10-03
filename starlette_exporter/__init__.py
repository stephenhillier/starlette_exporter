__all__ = [
    'PrometheusMiddleware',
    'from_header',
    'handle_metrics',
]

import os
from typing import Optional

from prometheus_client import (
    generate_latest,
    CONTENT_TYPE_LATEST,
    REGISTRY,
    multiprocess,
    CollectorRegistry,
)
from prometheus_client.openmetrics.exposition import (
    generate_latest as openmetrics_generate_latest,
    CONTENT_TYPE_LATEST as openmetrics_content_type_latest,
)
from starlette.requests import Request
from starlette.responses import Response

from .middleware import PrometheusMiddleware
from .labels import from_header

class MetricsHandler:
    def __init__(self, registry: CollectorRegistry = REGISTRY):
        """A class wrapper that allows you to inject your own metrics registry instead of the default."""
        self.registry = registry

    def handle_metrics(self, request: Request) -> Response:
        return handle_metrics(request, self.registry)

    def handle_openmetrics(self, request: Request) -> Response:
        return handle_openmetrics(request, self.registry)


def handle_metrics(request: Request, registry: Optional[CollectorRegistry] = None) -> Response:
    """A handler to expose Prometheus metrics
    Example usage:

        ```
        app.add_middleware(PrometheusMiddleware)
        app.add_route("/metrics", handle_metrics)
        ```
    """
    if registry is None:
        registry = REGISTRY
        if (
            "prometheus_multiproc_dir" in os.environ
            or "PROMETHEUS_MULTIPROC_DIR" in os.environ
        ):
            registry = CollectorRegistry()
            multiprocess.MultiProcessCollector(registry)

    headers = {"Content-Type": CONTENT_TYPE_LATEST}
    return Response(generate_latest(registry), status_code=200, headers=headers)


def handle_openmetrics(request: Request, registry: Optional[CollectorRegistry] = None) -> Response:
    """A handler to expose Prometheus metrics in OpenMetrics format.
    This is required to expose metrics with exemplars.
    Example usage:

        ```
        app.add_middleware(PrometheusMiddleware)
        app.add_route("/metrics", openmetrics_handler)
        ```
    """
    if registry is None:
        registry = REGISTRY
        if (
            "prometheus_multiproc_dir" in os.environ
            or "PROMETHEUS_MULTIPROC_DIR" in os.environ
        ):
            registry = CollectorRegistry()
            multiprocess.MultiProcessCollector(registry)

    headers = {"Content-Type": openmetrics_content_type_latest}
    return Response(
        openmetrics_generate_latest(registry),
        status_code=200,
        headers=headers,
    )
