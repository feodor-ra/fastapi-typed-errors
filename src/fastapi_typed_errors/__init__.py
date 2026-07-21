"""fastapi-typed-errors — typed error responses for FastAPI.

Literal error codes in OpenAPI, discriminated ``oneOf`` unions, and a single
source of truth: the error class itself.
"""

from .core import (
    BaseError,
    ErrorResponse,
    error_models,
    handle_base_error,
)

__all__ = (
    "BaseError",
    "ErrorResponse",
    "error_models",
    "handle_base_error",
)
