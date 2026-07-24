"""Packaging smoke test — run against the built wheel/sdist before publishing.

Exercises the public API end to end (metaclass derivation, the router patch,
OpenAPI generation and the checker) from an installed distribution, so a broken
build or a missing ``py.typed``/module is caught before it reaches PyPI.
"""

from enum import StrEnum
from http import HTTPStatus
from typing import Annotated, Literal

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

from fastapi_typed_errors import (
    BaseError,
    Raises,
    check_raises,
    error_models,
    handle_base_error,
    with_errors,
)


class Code(StrEnum):
    """Smoke error codes."""

    NOT_FOUND = "NOT_FOUND"


class NotFoundError(BaseError[Literal[Code.NOT_FOUND]]):
    """Smoke error."""

    http_status = HTTPStatus.NOT_FOUND


class Item(BaseModel):
    """Smoke payload."""

    item_id: int


def main() -> None:
    """Register a typed error end to end and assert the OpenAPI is typed."""
    app = FastAPI()
    app.add_exception_handler(BaseError, handle_base_error)
    router = with_errors(APIRouter())

    @router.get("/items/{item_id}")
    def get_item(item_id: int) -> Annotated[Item, Raises[NotFoundError]]:
        """Raise the typed error (a registration and analysis target).

        Args:
            item_id: Ignored.

        Raises:
            NotFoundError: Always.
        """
        raise NotFoundError(str(item_id))

    app.include_router(router)

    responses = app.openapi()["paths"]["/items/{item_id}"]["get"]["responses"]
    assert "404" in responses
    assert responses["200"]["content"]["application/json"]["schema"]["$ref"].endswith("Item")
    assert error_models(NotFoundError) is NotFoundError.model
    assert check_raises(app).ok


if __name__ == "__main__":
    main()
