""" Middleware for exporting Prometheus metrics using Starlette """
from collections import OrderedDict
import time
import logging
import warnings
from inspect import iscoroutine
from typing import (
    Any,
    Callable,
    List,
    Mapping,
    Optional,
    ClassVar,
    Dict,
    Union,
    Sequence,
)

from prometheus_client import Counter, Histogram, Gauge
from prometheus_client.metrics import MetricWrapperBase
from starlette.requests import Request
from starlette.routing import BaseRoute, Match
from starlette.types import ASGIApp, Message, Receive, Send, Scope

from . import optional_metrics

logger = logging.getLogger("starlette_exporter")


def get_matching_route_path(
    scope: Dict[Any, Any],
    routes: List[BaseRoute],
    route_name: Optional[str] = None,
) -> Optional[str]:
    """
    Find a matching route and return its original path string

    Will attempt to enter mounted routes and subrouters.

    Credit to https://github.com/elastic/apm-agent-python
    """
    for route in routes:
        match, child_scope = route.matches(scope)
        if match == Match.FULL:
            # set route name
            route_name = getattr(route, "path", None)
            if route_name is None:
                return None

            # for routes of type `BaseRoute`, the base route name may not
            # be the complete path (it may represent the path to the
            # mounted router). If this is a mounted route, descend into it to
            # get the complete path.
            if isinstance(route, BaseRoute) and getattr(route, "routes", None):
                child_scope = {**scope, **child_scope}
                child_route_name = get_matching_route_path(
                    child_scope, getattr(route, "routes"), route_name
                )
                if child_route_name is None:
                    route_name = None
                else:
                    route_name += child_route_name
            return route_name
        elif match == Match.PARTIAL and route_name is None:
            route_name = getattr(route, "path", None)

    return None


class PrometheusMiddleware:
    """Middleware that collects Prometheus metrics for each request.
    Use in conjuction with the Prometheus exporter endpoint handler.
    """

    _metrics: ClassVar[Dict[str, MetricWrapperBase]] = {}

    def __init__(
        self,
        app: ASGIApp,
        group_paths: bool = False,
        app_name: str = "starlette",
        prefix: str = "starlette",
        buckets: Optional[Sequence[Union[float, str]]] = None,
        filter_unhandled_paths: bool = False,
        skip_paths: Optional[List[str]] = None,
        skip_methods: Optional[List[str]] = None,
        optional_metrics: Optional[List[str]] = None,
        always_use_int_status: bool = False,
        labels: Optional[Mapping[str, Union[str, Callable]]] = None,
        exemplars: Optional[Callable] = None,
    ):
        self.app = app
        self.app_name = app_name
        self.prefix = prefix

        if group_paths is False or filter_unhandled_paths is False:
            warnings.warn(
                "group_paths and filter_unhandled_paths will change defaults from False to True in the next release. "
                "See https://github.com/stephenhillier/starlette_exporter/issues/79 for more info",
                FutureWarning,
            )
        self.group_paths = group_paths
        self.filter_unhandled_paths = filter_unhandled_paths

        self.kwargs = {}
        if buckets is not None:
            self.kwargs["buckets"] = buckets
        self.skip_paths = []
        if skip_paths is not None:
            self.skip_paths = skip_paths
        self.skip_methods = []
        if skip_methods is not None:
            self.skip_methods = skip_methods
        self.optional_metrics_list = []
        if optional_metrics is not None:
            self.optional_metrics_list = optional_metrics
        self.always_use_int_status = always_use_int_status

        self.labels = OrderedDict(labels) if labels is not None else None
        self.exemplars = exemplars

    # Default metrics

    @property
    def request_count(self):
        metric_name = f"{self.prefix}_requests_total"
        if metric_name not in PrometheusMiddleware._metrics:
            PrometheusMiddleware._metrics[metric_name] = Counter(
                metric_name,
                "Total HTTP requests",
                (
                    "method",
                    "path",
                    "status_code",
                    "app_name",
                    *self._default_label_keys(),
                ),
            )
        return PrometheusMiddleware._metrics[metric_name]

    @property
    def response_body_size_count(self):
        """
        Optional metric for tracking the size of response bodies.
        If using gzip middleware, you should test that the starlette_exporter middleware computes
        the proper response size value. Please post any feedback on this metric as an issue
        at https://github.com/stephenhillier/starlette_exporter.

        """
        if (
            self.optional_metrics_list is not None
            and optional_metrics.response_body_size in self.optional_metrics_list
        ):
            metric_name = f"{self.prefix}_response_body_bytes_total"
            if metric_name not in PrometheusMiddleware._metrics:
                PrometheusMiddleware._metrics[metric_name] = Counter(
                    metric_name,
                    "Total HTTP response body bytes",
                    (
                        "method",
                        "path",
                        "status_code",
                        "app_name",
                        *self._default_label_keys(),
                    ),
                )
            return PrometheusMiddleware._metrics[metric_name]
        else:
            pass

    @property
    def request_body_size_count(self):
        """
        Optional metric tracking the received content-lengths of request bodies
        """
        if (
            self.optional_metrics_list is not None
            and optional_metrics.request_body_size in self.optional_metrics_list
        ):
            metric_name = f"{self.prefix}_request_body_bytes_total"
            if metric_name not in PrometheusMiddleware._metrics:
                PrometheusMiddleware._metrics[metric_name] = Counter(
                    metric_name,
                    "Total HTTP request body bytes",
                    (
                        "method",
                        "path",
                        "status_code",
                        "app_name",
                        *self._default_label_keys(),
                    ),
                )
            return PrometheusMiddleware._metrics[metric_name]
        else:
            pass

    @property
    def request_time(self):
        metric_name = f"{self.prefix}_request_duration_seconds"
        if metric_name not in PrometheusMiddleware._metrics:
            PrometheusMiddleware._metrics[metric_name] = Histogram(
                metric_name,
                "HTTP request duration, in seconds",
                (
                    "method",
                    "path",
                    "status_code",
                    "app_name",
                    *self._default_label_keys(),
                ),
                **self.kwargs,
            )
        return PrometheusMiddleware._metrics[metric_name]

    @property
    def requests_in_progress(self):
        metric_name = f"{self.prefix}_requests_in_progress"
        if metric_name not in PrometheusMiddleware._metrics:
            PrometheusMiddleware._metrics[metric_name] = Gauge(
                metric_name,
                "Total HTTP requests currently in progress",
                ("method", "app_name", *self._default_label_keys()),
                multiprocess_mode="livesum",
            )
        return PrometheusMiddleware._metrics[metric_name]

    def _default_label_keys(self) -> List[str]:
        if self.labels is None:
            return []
        return list(self.labels.keys())

    async def _default_label_values(self, request: Request):
        if self.labels is None:
            return []

        values: List[str] = []

        for k, v in self.labels.items():
            if callable(v):
                parsed_value = ""
                # if provided a callable, try to use it on the request.
                try:
                    result = v(request)
                    if iscoroutine(result):
                        result = await result
                except Exception:
                    logger.warn(f"label function for {k} failed", exc_info=True)
                else:
                    parsed_value = str(result)
                values.append(parsed_value)
                continue

            values.append(v)

        return values

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ["http"]:
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)

        method = request.method
        path = request.url.path

        if path in self.skip_paths or method in self.skip_methods:
            await self.app(scope, receive, send)
            return

        begin = time.perf_counter()
        end = None

        default_labels = await self._default_label_values(request)

        # Increment requests_in_progress gauge when request comes in
        self.requests_in_progress.labels(method, self.app_name, *default_labels).inc()

        status_code = None

        # optional request and response body size metrics
        response_body_size: int = 0

        request_body_size: int = 0
        if (
            self.optional_metrics_list is not None
            and optional_metrics.request_body_size in self.optional_metrics_list
        ):
            if request.headers.get("content-length"):
                request_body_size = int(request.headers["content-length"])

        async def wrapped_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                nonlocal status_code
                status_code = message["status"]

                if self.always_use_int_status:
                    try:
                        status_code = int(message["status"])
                    except ValueError as e:
                        logger.warning(
                            f"always_use_int_status flag selected but failed to convert status_code to int for value: {status_code}"
                        )

                # find response body size for optional metric
                if (
                    self.optional_metrics_list is not None
                    and optional_metrics.response_body_size
                    in self.optional_metrics_list
                ):
                    nonlocal response_body_size
                    for message_content_length in message["headers"]:
                        if (
                            message_content_length[0].decode("utf-8")
                            == "content-length"
                        ):
                            response_body_size += int(
                                message_content_length[1].decode("utf-8")
                            )

            if message["type"] == "http.response.body":
                nonlocal end
                end = time.perf_counter()

            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        except Exception:
            status_code = 500
            raise
        finally:
            # Decrement 'requests_in_progress' gauge after response sent
            self.requests_in_progress.labels(
                method, self.app_name, *default_labels
            ).dec()

            if self.filter_unhandled_paths or self.group_paths:
                grouped_path = self._get_router_path(scope)

                # filter_unhandled_paths removes any requests without mapped endpoint from the metrics.
                if self.filter_unhandled_paths and grouped_path is None:
                    return

                # group_paths enables returning the original router path (with url param names)
                # for example, when using this option, requests to /api/product/1 and /api/product/3
                # will both be grouped under /api/product/{product_id}. See the README for more info.
                if self.group_paths and grouped_path is not None:
                    path = grouped_path

            if status_code is None:
                request = Request(scope, receive)
                if await request.is_disconnected():
                    # In case no response was returned and the client is disconnected, 499 is reported as status code.
                    status_code = 499
                else:
                    status_code = 500

            labels = [method, path, status_code, self.app_name, *default_labels]

            # optional extra arguments to be passed as kwargs to observations
            # note: only used for histogram observations and counters to support exemplars
            extra = {}
            if self.exemplars:
                extra["exemplar"] = self.exemplars()

            # optional response body size metric
            if (
                self.optional_metrics_list is not None
                and optional_metrics.response_body_size in self.optional_metrics_list
                and self.response_body_size_count is not None
            ):
                self.response_body_size_count.labels(*labels).inc(
                    response_body_size, **extra
                )

            # optional request body size metric
            if (
                self.optional_metrics_list is not None
                and optional_metrics.request_body_size in self.optional_metrics_list
                and self.request_body_size_count is not None
            ):
                self.request_body_size_count.labels(*labels).inc(
                    request_body_size, **extra
                )

            # if we were not able to set end when the response body was written,
            # set it now.
            if end is None:
                end = time.perf_counter()

            self.request_count.labels(*labels).inc(**extra)
            self.request_time.labels(*labels).observe(end - begin, **extra)

    @staticmethod
    def _get_router_path(scope: Scope) -> Optional[str]:
        """Returns the original router path (with url param names) for given request."""
        if not (scope.get("endpoint", None) and scope.get("router", None)):
            return None

        root_path = scope.get("root_path", "")
        app = scope.get("app", {})

        if hasattr(app, "root_path"):
            app_root_path = getattr(app, "root_path")
            if root_path.startswith(app_root_path):
                root_path = root_path[len(app_root_path) :]

        base_scope = {
            "type": scope.get("type"),
            "path": root_path + scope.get("path", ""),
            "path_params": scope.get("path_params", {}),
            "method": scope.get("method"),
            "headers": scope.get("headers", {}),
        }

        try:
            path = get_matching_route_path(
                base_scope, getattr(scope.get("router"), "routes")
            )
            return path
        except:
            # unhandled path
            pass

        return None
