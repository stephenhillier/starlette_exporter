# starlette_exporter
Prometheus exporter for Starlette and FastAPI.

The middleware collects basic metrics:

* Counter: starlette_requests_total
* Histogram: starlette_request_duration_seconds

Metrics include labels for the HTTP method, the path, and the response status code.

```
starlette_requests_total{method="GET",path="/",status_code="200"} 1.0
starlette_request_duration_seconds_bucket{le="0.01",method="GET",path="/",status_code="200"} 1.0
```

Use the HTTP handler `handle_metrics` at path `/metrics` to expose a metrics endpoint to Prometheus.

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

`group_paths`: setting this to `True` will populate the path label using named parameters (if any) in the router path, e.g. `/api/v1/items/{item_id}`.  This will group requests together by endpoint (regardless of the value of `item_id`). This option may come with a performance hit for larger routers. Default is `False`, which will result in separate metrics for different URLs (e.g., `/api/v1/items/42`, `/api/v1/items/43`, etc.).

Example: 
```python
app.add_middleware(PrometheusMiddleware, group_paths=True)
```

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
