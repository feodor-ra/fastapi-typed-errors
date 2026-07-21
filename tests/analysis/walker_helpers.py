"""Shared fixtures for analysis tests: error classes and cross-module callables.

These live in a separate importable module so the walker's cross-module name
resolution (against ``fn.__globals__``) and closure handling can be exercised.
"""

from collections.abc import Callable
from enum import StrEnum
from http import HTTPStatus
from typing import Literal

from fastapi_typed_errors import BaseError


class Code(StrEnum):
    """Error codes shared across the analysis tests."""

    NOT_FOUND = "NOT_FOUND"
    FORBIDDEN = "FORBIDDEN"
    CONFLICT = "CONFLICT"
    GONE = "GONE"
    TOKEN = "TOKEN"  # ruff:ignore[hardcoded-password-string]


class NotFoundError(BaseError[Literal[Code.NOT_FOUND]]):
    """404 test error."""

    http_status = HTTPStatus.NOT_FOUND


class ForbiddenError(BaseError[Literal[Code.FORBIDDEN]]):
    """403 test error."""

    http_status = HTTPStatus.FORBIDDEN


class ConflictError(BaseError[Literal[Code.CONFLICT]]):
    """409 test error."""

    http_status = HTTPStatus.CONFLICT


class GoneError(BaseError[Literal[Code.GONE]]):
    """Second 404 test error, for one-status union cases."""

    http_status = HTTPStatus.NOT_FOUND


class TokenError(BaseError[Literal[Code.TOKEN]]):
    """401 test error, raised from dependencies."""

    http_status = HTTPStatus.UNAUTHORIZED


class AppError[T: str](BaseError[T]):
    """Codeless intermediate base — exercises the concreteness probe."""


def cross_raiser() -> None:
    """Raise across module boundaries (resolved via this module's globals).

    Raises:
        ForbiddenError: Always.
    """
    raise ForbiddenError("cross")


def make_empty_cell(*, fill: bool = False) -> Callable[[], object]:
    """Return a closure whose captured cell stays empty unless ``fill`` is set.

    Args:
        fill: When ``False`` the captured name is never assigned, leaving an
            empty closure cell.

    Returns:
        Callable[[], object]: The inner closure over the (empty) cell.
    """

    def inner() -> object:
        return captured

    if fill:
        captured = NotFoundError
    return inner
