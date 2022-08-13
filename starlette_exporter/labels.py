"""utilities for working with labels"""
from typing import Callable

from starlette.requests import Request

def from_header(key: str) -> Callable:
    """returns a function that retrieves a header value from a request.
    The returned function can be passed to the `labels` argument of PrometheusMiddleware
    to label metrics using a header value.

    example:

    ```
        PrometheusMiddleware(
            labels={
                "host": from_header("host")
            }
        )
    ```

    
    This function is essentially the same as using:

    ```
        PrometheusMiddleware(
            labels={
                "host": lambda r: r.headers.get("host")
            }
        )
    ```
    If similar functionality is needed using something other than the request headers,
    try using the lambda function form.
    """

    def inner(r: Request):
        return r.headers.get(key, None)

    return inner
        
