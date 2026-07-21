"""Tests for the ``Raises`` marker."""

from enum import StrEnum
from http import HTTPStatus
from typing import Literal

import pytest

from fastapi_typed_errors import BaseError, Raises


class Code(StrEnum):
    """Error codes used by the test error classes."""

    NOT_FOUND = "NOT_FOUND"
    FORBIDDEN = "FORBIDDEN"


class NotFoundError(BaseError[Literal[Code.NOT_FOUND]]):
    """Test error with the NOT_FOUND code."""

    http_status = HTTPStatus.NOT_FOUND


class ForbiddenError(BaseError[Literal[Code.FORBIDDEN]]):
    """Test error with the FORBIDDEN code."""

    http_status = HTTPStatus.FORBIDDEN


class AppError[T: str](BaseError[T]):
    """Intermediate generic base without a code."""


class NoStatusError(BaseError[Literal["NO_STATUS"]]):
    """Error with a code but no declared ``http_status``."""


def test_subscription_with_one_class() -> None:
    """``Raises[A]`` stores a single error class."""
    assert Raises[NotFoundError].errors == (NotFoundError,)


def test_subscription_with_many_classes() -> None:
    """``Raises[A, B]`` keeps the declaration order."""
    assert Raises[NotFoundError, ForbiddenError].errors == (NotFoundError, ForbiddenError)


def test_star_subscription_unpacks_shared_tuples() -> None:
    """``Raises[*SHARED]`` accepts an unpacked tuple."""
    shared = (NotFoundError, ForbiddenError)

    assert Raises[*shared].errors == shared


def test_constructor_form_is_equivalent() -> None:
    """``Raises(A, B)`` is the statically clean spelling of the subscription."""
    assert Raises(NotFoundError, ForbiddenError).errors == (NotFoundError, ForbiddenError)


def test_repr_renders_subscription_form() -> None:
    """The marker repr mirrors how it was written."""
    assert repr(Raises[NotFoundError, ForbiddenError]) == "Raises[NotFoundError, ForbiddenError]"


def test_empty_marker_rejected() -> None:
    """A marker without error classes is meaningless."""
    with pytest.raises(TypeError, match="at least one error class"):
        Raises()


def test_non_error_member_rejected() -> None:
    """Only ``BaseError`` subclasses are accepted."""
    with pytest.raises(TypeError, match="only BaseError subclasses"):
        Raises[int]  # ty: ignore[invalid-argument-type]


def test_codeless_member_rejected() -> None:
    """An intermediate generic base has no code and is rejected eagerly."""
    with pytest.raises(TypeError, match="cannot be used in Raises"):
        Raises[AppError]


def test_statusless_member_rejected() -> None:
    """A member without a declared ``http_status`` is rejected eagerly."""
    with pytest.raises(TypeError, match="cannot be used in Raises"):
        Raises[NoStatusError]
