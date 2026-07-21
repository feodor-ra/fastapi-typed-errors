"""Layer 1 — core primitives, usable without the decorator and analysis layers."""

from .base import BaseError, ErrorResponse
from .handlers import handle_base_error
from .models import error_models

__all__ = (
    "BaseError",
    "ErrorResponse",
    "error_models",
    "handle_base_error",
)
