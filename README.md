# starlette_exporter

## Prometheus exporter for Starlette and FastAPI

starlette_exporter collects basic metrics for Starlette and FastAPI based applications:

* starlette_requests_total: a counter representing the total requests
* starlette_request_duration_seconds: a histogram representing the distribution of request response times
* starlette_requests_in_progress: a gauge that keeps track of how many concurrent requests are being processed

Metrics include labels for the HTTP method, the path, and the response status code.

```
starlette_requests_total{method="GET",path="/",status_code="200"} 1.0
starlette_request_duration_seconds_bucket{le="0.01",method="GET",path="/",status_code="200"} 1.0
```

Use the HTTP handler `handle_metrics` at path `/metrics` to expose a metrics endpoint to Prometheus.

## Table of Contents

* [starlette_exporter](#starlette_exporter)
  * [Prometheus exporter for Starlette and FastAPI](#prometheus-exporter-for-starlette-and-fastapi)
  * [Table of Contents](#table-of-contents)
  * [Usage](#usage)
    * [Starlette](#starlette)
    * [FastAPI](#fastapi)
  * [Options](#options)
  * [Labels](#labels)
  * [Exemplars](#exemplars)
  * [Custom Metrics](#custom-metrics)
  * [Multiprocess mode (gunicorn deployments)](#multiprocess-mode-gunicorn-deployments)
  * [Developing](#developing)
  * [License](#license)
  * [Dependencies](#dependencies)
  * [Credits](#credits)

## Usage

```sh
pip install starlette_exporter
```

### Starlette

```python
from starlette.applications import Starlette
from starlette_exporter import PrometheusMiddleware, handle_metrics

app = Starlette()
app.add_middleware(PrometheusMiddleware)
app.add_route("/metrics", handle_metrics)

...
```

### FastAPI

```python
from fastapi import FastAPI
from starlette_exporter import PrometheusMiddleware, handle_metrics

app = FastAPI()
app.add_middleware(PrometheusMiddleware)
app.add_route("/metrics", handle_metrics)

...
```

## Options

`app_name`: Sets the value of the `app_name` label for exported metrics (default: `starlette`).

`prefix`: Sets the prefix of the exported metric names (default: `starlette`).

`labels`: Optional dict containing default labels that will be added to all metrics. The values can be either a static value or a callback function that
retrieves a value from the `Request` object. [See below](#labels) for examples.

`exemplars`: Optional dict containing label/value pairs. The "value" should be a callback function that returns the desired value at runtime.

`group_paths`: Populate the path label using named parameters (if any) in the router path, e.g. `/api/v1/items/{item_id}`. This will group requests together by endpoint (regardless of the value of `item_id`). As of v0.18.0, the default is `True`, and changing to `False` is highly discouraged (see [warnings about cardinality](https://grafana.com/blog/2022/02/15/what-are-cardinality-spikes-and-why-do-they-matter/)).

`filter_unhandled_paths`: setting this to `True` will cause the middleware to ignore requests with unhandled paths (in other words, 404 errors). This helps prevent filling up the metrics with 404 errors and/or intentially bad requests. Default is `True`.

`group_unhandled_paths`: Similar to `filter_unhandled_paths`, but instead of ignoring the requests, they are grouped under the `__unknown__` path. This option overrides `filter_unhandled_paths` by setting it to `False`. The default value is `False`.

`buckets`: accepts an optional list of numbers to use as histogram buckets. The default value is `None`, which will cause the library to fall back on the Prometheus defaults (currently `[0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0]`).

`skip_paths`: accepts an optional list of paths, or regular expressions for paths, that will not collect metrics. The default value is `None`, which will cause the library to collect metrics on every requested path. This option is useful to avoid collecting metrics on health check, readiness or liveness probe endpoints.

`skip_methods`: accepts an optional list of methods that will not collect metrics. The default value is `None`, which will cause the library to collect request metrics with each method. This option is useful to avoid collecting metrics on requests related to the communication description for endpoints.

`always_use_int_status`: accepts a boolean. The default value is False. If set to True the libary will attempt to convert the `status_code` value to an integer (e.g. if you are using HTTPStatus, HTTPStatus.OK will become 200 for all metrics).

`optional_metrics`: a list of pre-defined metrics that can be optionally added to the default metrics. The following optional metrics are available:

* `response_body_size`: a counter that tracks the size of response bodies for each endpoint

For optional metric examples, [see below](#optional-metrics).

Full example:

```python
app.add_middleware(
  PrometheusMiddleware,
  app_name="hello_world",
  prefix='myapp',
  labels={
      "server_name": os.getenv("HOSTNAME"),
  }),
  buckets=[0.1, 0.25, 0.5],
  skip_paths=['/health'],
  skip_methods=['OPTIONS'],
  always_use_int_status=False),
  exemplars=lambda: {"trace_id": get_trace_id}  # function that returns a trace id
```

## Labels

The included metrics have built-in default labels such as `app_name`, `method`, `path`, and `status_code`. Additional default labels can be
added by passing a dictionary to the `labels` arg to `PrometheusMiddleware`. Each label's value can be either a static
value or, optionally, a callback function. The built-in default label names are reserved and cannot be reused.

If a callback function is used, it will receive the Request instance as its argument.

```python
app.add_middleware(
  PrometheusMiddleware,
  labels={
     "service": "api",
     "env": os.getenv("ENV")
    }
```

Ensure that label names follow [Prometheus naming conventions](https://prometheus.io/docs/practices/naming/) and that label
values are constrained (see [this writeup from Grafana on cardinality](https://grafana.com/blog/2022/02/15/what-are-cardinality-spikes-and-why-do-they-matter/)).

### Label helpers

**`from_header(key: string, allowed_values: Optional[Iterable] = None, default: str = "")`**: a convenience function for using a header value as a label.

`allowed_values` allows you to supply a list of allowed values. If supplied, header values not in the list will result in
an empty string being returned. This allows you to constrain the label values, reducing the risk of excessive cardinality.

`default`: the default value if the header does not exist.

Do not use headers that could contain unconstrained values (e.g. user id) or user-supplied values.


**`from_response_header(key: str, allowed_values: Optional[Iterable] = None, default: str = "")`**: a helper
function that extracts a value from a response header. This may be useful if you are using a middleware
or decorator that populates a header.

The same options (and warnings) apply as the `from_header` function.

```python
from starlette_exporter import PrometheusMiddleware, from_header

app.add_middleware(
  PrometheusMiddleware,
  labels={
      "host": from_header("X-Internal-Org", allowed_values=("accounting", "marketing", "product"))
      "cache": from_response_header("X-FastAPI-Cache", allowed_values=("hit", "miss"))
    }
```

## Exemplars

Exemplars are used for labeling histogram observations or counter increments with a trace id. This allows adding
trace ids to your charts (for example, latency graphs could include traces corresponding to various latency buckets).

To add exemplars to `starlette_exporter` metrics, pass a dict to the PrometheusMiddleware class with label as well as
a callback function that returns a string (typically the current trace id).

**Example:**

```python
# must use `handle_openmetrics` instead of `handle_metrics` for exemplars to appear in /metrics output.
from starlette_exporter import PrometheusMiddleware, handle_openmetrics

app.add_middleware(
  PrometheusMiddleware,
  exemplars=lambda: {"trace_id": get_trace_id}  # supply your own callback function
)

app.add_route("/metrics", handle_openmetrics)
```

Exemplars are only supported by the openmetrics-text exposition format. A new `handle_openmetrics` handler function is provided
(see above example).

For more information, see the [Grafana exemplar documentation](https://grafana.com/docs/grafana/latest/fundamentals/exemplars/).

## Optional metrics

Optional metrics are pre-defined metrics that can be added to the default metrics.

* `response_body_size`: the size of response bodies returned, in bytes
* `request_body_size`: the size of request bodies received, in bytes

**Example**:

```python
from fastapi import FastAPI
from starlette_exporter import PrometheusMiddleware, handle_metrics
from starlette_exporter.optional_metrics import response_body_size, request_body_size

app = FastAPI()
app.add_middleware(PrometheusMiddleware, optional_metrics=[response_body_size, request_body_size])
```

## Custom Metrics

starlette_exporter will export all the prometheus metrics from the process, so custom metrics can be created by using the prometheus_client API.

**Example**:

```python
from prometheus_client import Counter
from starlette.responses import RedirectResponse

REDIRECT_COUNT = Counter("redirect_total", "Count of redirects", ["redirected_from"])

async def some_view(request):
    REDIRECT_COUNT.labels("some_view").inc()
    return RedirectResponse(url="https://example.com", status_code=302)
```

The new metric will now be included in the the `/metrics` endpoint output:

```
...
redirect_total{redirected_from="some_view"} 2.0
...
```

## Multiprocess mode (gunicorn deployments)

Running starlette_exporter in a multiprocess deployment (e.g. with gunicorn) will need the `PROMETHEUS_MULTIPROC_DIR` env variable set, as well as extra gunicorn config.

For more information, see the [Prometheus Python client documentation](https://github.com/prometheus/client_python#multiprocess-mode-eg-gunicorn).

## Developing

This package supports Python 3.6+.

```sh
git clone https://github.com/stephenhillier/starlette_exporter
cd starlette_exporter
pytest tests
```

## License

Code released under the [Apache License, Version 2.0](./LICENSE).

## Dependencies

https://github.com/prometheus/client_python (>= 0.12)

https://github.com/encode/starlette

## Credits

Starlette - https://github.com/encode/starlette

FastAPI - https://github.com/tiangolo/fastapi

Flask exporter - https://github.com/rycus86/prometheus_flask_exporter

Alternate Starlette exporter - https://github.com/perdy/starlette-prometheus
