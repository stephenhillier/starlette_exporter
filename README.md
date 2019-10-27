# starlette_exporter
Prometheus exporter for Starlette and FastAPI

# Usage

## Starlette

```python
        from starlette.applications import Starlette
        from starlette_exporter import PrometheusMiddleware, handle_metrics

        app = Starlette()
        app.add_middleware(PrometheusMiddleware)
        app.add_route("/metrics", handle_metrics)

        ...
```

## FastAPI

```python
        from fastapi import FastAPI
        from starlette_exporter import PrometheusMiddleware, handle_metrics

        app = FastAPI()
        app.add_middleware(PrometheusMiddleware)
        app.add_route("/metrics", handle_metrics)

        ...
```

# Developing

```sh
git clone https://github.com/stephenhillier/starlette_exporter
cd starlette_exporter
pytest tests
```

# License

Code released under the [Apache License, Version 2.0](https://github.com/bcgov/gwells/blob/master/LICENSE).
