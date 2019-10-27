# starlette_exporter
Prometheus exporter for Starlette and FastAPI.

The middleware collects basic metrics:

* Counter: starlette_requests_total
* Histogram: starlette_request_duration_seconds

Metrics include labels for the HTTP method, the path, and the response status code.

```
starlette_requests_total{method="GET",path="/",status_code="200"} 1.0
```

Use the HTTP handler `handle_metrics` at path `/metrics` to expose a metrics endpoint to Prometheus.

## Usage

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

## Developing

```sh
git clone https://github.com/stephenhillier/starlette_exporter
cd starlette_exporter
pytest tests
```

## License

Code released under the [Apache License, Version 2.0](https://github.com/bcgov/gwells/blob/master/LICENSE).
