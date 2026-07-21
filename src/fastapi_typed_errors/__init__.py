"""fastapi-typed-errors — typed error responses for FastAPI.

Literal error codes in OpenAPI, discriminated ``oneOf`` unions, and a single
source of truth: the error class itself.
"""

from .analysis import RaisesReport, RouteDiscrepancy, check_raises
from .core import (
    BaseError,
    ErrorResponse,
    error_models,
    handle_base_error,
)
from .decorator import Raises, with_errors

__all__ = (
    "BaseError",
    "ErrorResponse",
    "Raises",
    "RaisesReport",
    "RouteDiscrepancy",
    "check_raises",
    "error_models",
    "handle_base_error",
    "with_errors",
)
