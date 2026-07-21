"""``error_models()`` — response models for the FastAPI ``responses={}`` mapping."""

from typing import Annotated, Any, Union, overload

from pydantic import Field

from .base import BaseError, ErrorResponse


@overload
def error_models[C1: str](
    e1: type[BaseError[C1]],
) -> type[ErrorResponse[C1]]: ...


@overload
def error_models[C1: str, C2: str](
    e1: type[BaseError[C1]],
    e2: type[BaseError[C2]],
) -> type[ErrorResponse[C1 | C2]]: ...


@overload
def error_models[C1: str, C2: str, C3: str](
    e1: type[BaseError[C1]],
    e2: type[BaseError[C2]],
    e3: type[BaseError[C3]],
) -> type[ErrorResponse[C1 | C2 | C3]]: ...


@overload
def error_models[C1: str, C2: str, C3: str, C4: str](
    e1: type[BaseError[C1]],
    e2: type[BaseError[C2]],
    e3: type[BaseError[C3]],
    e4: type[BaseError[C4]],
) -> type[ErrorResponse[C1 | C2 | C3 | C4]]: ...


@overload
def error_models[C1: str, C2: str, C3: str, C4: str, C5: str](
    e1: type[BaseError[C1]],
    e2: type[BaseError[C2]],
    e3: type[BaseError[C3]],
    e4: type[BaseError[C4]],
    e5: type[BaseError[C5]],
) -> type[ErrorResponse[C1 | C2 | C3 | C4 | C5]]: ...


@overload
def error_models[C1: str, C2: str, C3: str, C4: str, C5: str, C6: str](
    e1: type[BaseError[C1]],
    e2: type[BaseError[C2]],
    e3: type[BaseError[C3]],
    e4: type[BaseError[C4]],
    e5: type[BaseError[C5]],
    e6: type[BaseError[C6]],
) -> type[ErrorResponse[C1 | C2 | C3 | C4 | C5 | C6]]: ...


@overload
def error_models[C1: str, C2: str, C3: str, C4: str, C5: str, C6: str, C7: str](
    e1: type[BaseError[C1]],
    e2: type[BaseError[C2]],
    e3: type[BaseError[C3]],
    e4: type[BaseError[C4]],
    e5: type[BaseError[C5]],
    e6: type[BaseError[C6]],
    e7: type[BaseError[C7]],
) -> type[ErrorResponse[C1 | C2 | C3 | C4 | C5 | C6 | C7]]: ...


@overload
def error_models[C1: str, C2: str, C3: str, C4: str, C5: str, C6: str, C7: str, C8: str](
    e1: type[BaseError[C1]],
    e2: type[BaseError[C2]],
    e3: type[BaseError[C3]],
    e4: type[BaseError[C4]],
    e5: type[BaseError[C5]],
    e6: type[BaseError[C6]],
    e7: type[BaseError[C7]],
    e8: type[BaseError[C8]],
) -> type[ErrorResponse[C1 | C2 | C3 | C4 | C5 | C6 | C7 | C8]]: ...


@overload
def error_models[C: str](*error_classes: type[BaseError[C]]) -> type[ErrorResponse[C]]: ...


def error_models[C: str](*error_classes: type[BaseError[C]]) -> type[ErrorResponse[C]]:
    """Build a Pydantic model for the ``"model"`` key of a route's ``responses={}``.

    Args:
        *error_classes: ``BaseError`` subclasses to combine; repeated classes
            are deduplicated.

    Returns:
        type[ErrorResponse[C]]: For a single class — its parametrized response
            model directly. For several classes — a discriminated union on the
            ``code`` field, which renders as a proper ``oneOf`` in OpenAPI.

    Raises:
        TypeError: If called with no arguments, or if one error code is
            shared by multiple distinct response models (such a union cannot
            be discriminated).
    """
    if not error_classes:
        msg = "error_models() requires at least one error class"
        raise TypeError(msg)
    # Dedupe repeats; a code shared by *different* models cannot be discriminated.
    by_code: dict[str, type[ErrorResponse[Any]]] = {}
    for error_class in error_classes:
        existing = by_code.get(error_class.error_code)
        if existing is not None and existing is not error_class.model:
            msg = (
                f"error code {error_class.error_code!r} is shared by multiple distinct "
                "response models; codes inside one union must be unique"
            )
            raise TypeError(msg)
        by_code[error_class.error_code] = error_class.model
    models = tuple(by_code.values())
    if len(models) == 1:
        return models[0]
    # Runtime-built discriminated union — not statically expressible.
    return Annotated[Union[models], Field(discriminator="code")]  # ty: ignore[invalid-return-type, invalid-type-form]  # ruff:ignore[non-pep604-annotation-union]
