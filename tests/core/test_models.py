"""Tests for ``error_models()``."""

from enum import StrEnum
from http import HTTPStatus
from typing import Annotated, Literal, get_args, get_origin

import pytest
from pydantic import TypeAdapter

from fastapi_typed_errors import BaseError, ErrorResponse, error_models


class Code(StrEnum):
    """Error codes used by the test error classes."""

    NOT_FOUND = "NOT_FOUND"
    FORBIDDEN = "FORBIDDEN"


class NotFoundError(BaseError[Literal[Code.NOT_FOUND]]):
    """Test error carrying the NOT_FOUND code."""

    http_status = HTTPStatus.NOT_FOUND


class ForbiddenError(BaseError[Literal[Code.FORBIDDEN]]):
    """Test error carrying the FORBIDDEN code."""

    http_status = HTTPStatus.FORBIDDEN


class WideResponse[T: str](ErrorResponse[T]):
    """Custom response base distinct from ``ErrorResponse``."""

    extra: str = "x"


class NotFoundTwin(BaseError[Literal[Code.NOT_FOUND]]):
    """Same code as ``NotFoundError`` but a distinct response model."""

    http_status = HTTPStatus.NOT_FOUND
    response_base = WideResponse


@pytest.fixture
def union() -> type[ErrorResponse[Literal[Code.NOT_FOUND, Code.FORBIDDEN]]]:
    """Discriminated union built from two error classes.

    Returns:
        type[ErrorResponse[Literal[Code.NOT_FOUND, Code.FORBIDDEN]]]: The
            ``error_models`` result for two distinct codes.
    """
    return error_models(NotFoundError, ForbiddenError)


def test_single_class_returns_its_model() -> None:
    """A single class yields its parametrized response model directly."""
    assert error_models(NotFoundError) is NotFoundError.model


def test_multiple_classes_build_discriminated_union(
    union: type[ErrorResponse[Literal[Code.NOT_FOUND, Code.FORBIDDEN]]],
) -> None:
    """Several classes yield an ``Annotated`` union discriminated by ``code``."""
    assert get_origin(union) is Annotated
    inner, field = get_args(union)
    assert set(get_args(inner)) == {NotFoundError.model, ForbiddenError.model}
    assert field.discriminator == "code"


def test_union_validates_by_discriminator(
    union: type[ErrorResponse[Literal[Code.NOT_FOUND, Code.FORBIDDEN]]],
) -> None:
    """The built union picks the right model from the ``code`` value."""
    parsed = TypeAdapter(union).validate_python({"code": "FORBIDDEN", "detail": "no"})

    assert type(parsed) is ForbiddenError.model
    assert parsed.code is Code.FORBIDDEN


def test_repeated_classes_are_deduplicated() -> None:
    """Passing the same class twice collapses to the single-model form."""
    assert error_models(NotFoundError, NotFoundError) is NotFoundError.model


def test_no_classes_rejected() -> None:
    """Calling without arguments raises a clear ``TypeError``."""
    with pytest.raises(TypeError, match="at least one error class"):
        error_models()


def test_same_code_on_distinct_models_rejected() -> None:
    """One code shared by two distinct models cannot be discriminated."""
    with pytest.raises(TypeError, match="shared by multiple distinct"):
        error_models(NotFoundError, NotFoundTwin)
