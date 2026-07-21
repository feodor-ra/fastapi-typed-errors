"""Tests for ``BaseError`` and the ``BaseErrorMeta`` metaclass."""

from enum import StrEnum
from http import HTTPStatus
from typing import Literal

import pytest

from fastapi_typed_errors import BaseError, ErrorResponse
from fastapi_typed_errors.core.base import BaseErrorMeta


class Code(StrEnum):
    """Error codes used by the test error classes."""

    NOT_FOUND = "NOT_FOUND"
    FORBIDDEN = "FORBIDDEN"


class NotFoundError(BaseError[Literal[Code.NOT_FOUND]]):
    """Test error with a description."""

    http_status = HTTPStatus.NOT_FOUND
    description = "Entity does not exist"


class ForbiddenError(BaseError[Literal[Code.FORBIDDEN]]):
    """Test error without a description."""

    http_status = HTTPStatus.FORBIDDEN


class WideResponse[T: str](ErrorResponse[T]):
    """Custom response base with an extra field."""

    extra: str = "x"


class AppError[T: str](BaseError[T]):
    """Intermediate generic base carrying a custom ``response_base``."""

    response_base = WideResponse


class CustomError(AppError[Literal[Code.FORBIDDEN]]):
    """Concrete error inheriting the custom response base."""

    http_status = HTTPStatus.FORBIDDEN


def test_code_extracted_from_enum_literal() -> None:
    """The metaclass pulls the code out of the ``Literal`` generic parameter."""
    assert NotFoundError.error_code is Code.NOT_FOUND


def test_code_extracted_from_bare_string_literal() -> None:
    """A plain string ``Literal`` works as the error code too."""

    class BareError(BaseError[Literal["BARE"]]):
        """Error declared without an enum."""

        http_status = HTTPStatus.CONFLICT

    assert BareError.error_code == "BARE"


def test_error_classes_use_the_metaclass() -> None:
    """Concrete errors are instances of the public ``BaseErrorMeta``."""
    assert type(NotFoundError) is BaseErrorMeta


def test_model_is_parametrized_response() -> None:
    """The derived model validates the exact declared code."""
    instance = NotFoundError.model(code=Code.NOT_FOUND, detail="gone")

    assert isinstance(instance, ErrorResponse)
    assert instance.code is Code.NOT_FOUND


def test_model_title_is_clean() -> None:
    """OpenAPI titles render the code value, not the enum ``repr()``."""
    assert NotFoundError.model.model_json_schema()["title"] == "ErrorResponse[NOT_FOUND]"


def test_unparametrized_model_title_is_class_name() -> None:
    """The generic base keeps its plain class name as the title."""
    assert ErrorResponse.model_json_schema()["title"] == "ErrorResponse"


def test_intermediate_base_has_no_code() -> None:
    """A generic base parametrized with a ``TypeVar`` declares no code."""
    with pytest.raises(AttributeError, match="error_code is not defined"):
        _ = AppError.error_code


def test_intermediate_base_has_no_model() -> None:
    """A generic base parametrized with a ``TypeVar`` declares no model."""
    with pytest.raises(AttributeError, match="model is not defined"):
        _ = AppError.model


def test_non_literal_parametrization_rejected() -> None:
    """``BaseError[str]`` fails at class definition time, not at request time."""
    with pytest.raises(TypeError, match="exactly one string code"):

        class _Bad(BaseError[str]):
            http_status = HTTPStatus.BAD_REQUEST


def test_enum_class_parametrization_rejected() -> None:
    """Passing the whole enum instead of ``Literal[member]`` is rejected."""
    with pytest.raises(TypeError, match="exactly one string code"):

        class _Bad(BaseError[Code]):
            http_status = HTTPStatus.BAD_REQUEST


def test_multi_literal_parametrization_rejected() -> None:
    """A ``Literal`` with several codes is rejected."""
    with pytest.raises(TypeError, match="exactly one string code"):

        class _Bad(BaseError[Literal[Code.NOT_FOUND, Code.FORBIDDEN]]):
            http_status = HTTPStatus.BAD_REQUEST


def test_response_base_inherited_from_generic_base() -> None:
    """A concrete error parametrizes the ``response_base`` of its base class."""
    response = CustomError("no").to_response()

    assert isinstance(response, WideResponse)
    assert response.extra == "x"


def test_response_base_declared_in_own_namespace() -> None:
    """A class declaring both code and ``response_base`` uses its own base."""

    class InlineError(BaseError[Literal["INLINE"]]):
        """Error overriding the response base in place."""

        http_status = HTTPStatus.CONFLICT
        response_base = WideResponse

    assert isinstance(InlineError("x").to_response(), WideResponse)


def test_detail_defaults_to_description() -> None:
    """Without an explicit detail the ``description`` is used."""
    assert NotFoundError().detail == "Entity does not exist"


def test_detail_falls_back_to_status_phrase() -> None:
    """Without a description the HTTP status phrase is used."""
    assert ForbiddenError().detail == HTTPStatus.FORBIDDEN.phrase


def test_explicit_detail_wins() -> None:
    """An explicit detail overrides all defaults."""
    assert NotFoundError("gone").detail == "gone"


def test_headers_are_stored() -> None:
    """Extra headers are passed through to ``HTTPException``."""
    assert NotFoundError(headers={"WWW-Authenticate": "Bearer"}).headers == {"WWW-Authenticate": "Bearer"}


def test_status_code_comes_from_http_status() -> None:
    """The ``HTTPException`` status code mirrors ``http_status``."""
    assert NotFoundError().status_code == HTTPStatus.NOT_FOUND


def test_to_response_carries_code_and_detail() -> None:
    """``to_response()`` builds the parametrized model from the instance."""
    response = NotFoundError("gone").to_response()

    assert type(response) is NotFoundError.model
    assert response.code is Code.NOT_FOUND
    assert response.detail == "gone"


def test_metaclass_standalone_defaults_to_error_response() -> None:
    """The metaclass works without ``BaseError``, falling back to ``ErrorResponse``."""

    class RogueBase[T: str](metaclass=BaseErrorMeta):
        """Generic base using the metaclass directly."""

    class RogueError(RogueBase[Literal["ROGUE"]]):
        """Concrete error outside the BaseError hierarchy."""

    assert issubclass(RogueError.model, ErrorResponse)


def test_two_parameter_generic_base_declares_no_code() -> None:
    """A base parametrized with two arguments is skipped by code extraction."""

    class TwoParam[T: str, U: str](BaseError[T]):
        """Base carrying an extra, unrelated type parameter."""

    class Odd(TwoParam[Literal["ODD"], Literal["X"]]):
        """Parametrization the extractor must skip."""

        http_status = HTTPStatus.BAD_REQUEST

    with pytest.raises(AttributeError, match="error_code is not defined"):
        _ = Odd.error_code
