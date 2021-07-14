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

1. [Usage](#usage)
    1. [Starlette](#starlette)
    1. [FastAPI](#fastapi)
1. [Options](#options)
1. [Custom metrics](#custom-metrics)
1. [Multiprocess mode (gunicorn deployments)](#multiprocess-mode-gunicorn-deployments)
1. [Developing](#developing)
1. [License](#license)

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

`group_paths`: setting this to `True` will populate the path label using named parameters (if any) in the router path, e.g. `/api/v1/items/{item_id}`.  This will group requests together by endpoint (regardless of the value of `item_id`). This option may come with a performance hit for larger routers. Default is `False`, which will result in separate metrics for different URLs (e.g., `/api/v1/items/42`, `/api/v1/items/43`, etc.).

`filter_unhandled_paths`: setting this to `True` will cause the middleware to ignore requests with unhandled paths (in other words, 404 errors). This helps prevent filling up the metrics with 404 errors and/or intentially bad requests. Default is `False`.

`buckets`: accepts an optional list of numbers to use as histogram buckets. The default value is `None`, which will cause the library to fall back on the Prometheus defaults (currently `[0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0]`).

Example:
```python
app.add_middleware(PrometheusMiddleware, app_name="hello_world", group_paths=True, prefix='myapp', buckets=[0.1, 0.25, 0.5])
```

## Custom Metrics

starlette_exporter will export all the prometheus metrics from the process, so custom metrics can be created by using the prometheus_client API.

#### Example:

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

```sh
git clone https://github.com/stephenhillier/starlette_exporter
cd starlette_exporter
pytest tests
```

## License

Code released under the [Apache License, Version 2.0](./LICENSE).


## Dependencies

https://github.com/prometheus/client_python

https://github.com/encode/starlette

## Credits

Starlette - https://github.com/encode/starlette

FastAPI - https://github.com/tiangolo/fastapi

Flask exporter - https://github.com/rycus86/prometheus_flask_exporter

Alternate Starlette exporter - https://github.com/perdy/starlette-prometheus
