"""The ``BaseError`` exception handler."""

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from .base import BaseError


async def handle_base_error(  # ruff:ignore[unused-async]
    request: Request,  # ruff:ignore[unused-function-argument]
    error: Exception,
) -> Response:
    """Handle any ``BaseError`` raised inside a route or dependency.

    Starlette resolves handlers by walking ``type(exc).__mro__``, so this
    handler takes precedence over the default ``HTTPException`` handler for
    all ``BaseError`` subclasses while leaving plain ``HTTPException`` alone.

    The ``error`` parameter is typed ``Exception`` to match Starlette's
    handler contract, keeping the registration line clean for every type
    checker; misregistration is caught at runtime instead.

    Example:
        Register it explicitly, the FastAPI way::

            app.add_exception_handler(BaseError, handle_base_error)

    Args:
        request: Incoming request; unused, required by the handler signature.
        error: The raised error; must be a ``BaseError`` instance.

    Returns:
        Response: JSON response built from ``error.to_response()`` with the
            error's HTTP status and headers.

    Raises:
        TypeError: If the handler was registered for (and called with) an
            exception type that is not a ``BaseError`` subclass.
    """
    if not isinstance(error, BaseError):
        msg = f"handle_base_error received {type(error).__name__}; register it only for BaseError and its subclasses"
        raise TypeError(msg)
    return JSONResponse(
        status_code=error.status_code,
        content=error.to_response().model_dump(mode="json"),
        headers=error.headers,
    )
