"""Tests for ``handle_base_error``."""

import json
from enum import StrEnum
from http import HTTPStatus
from typing import Literal

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from fastapi_typed_errors import BaseError, handle_base_error


class Code(StrEnum):
    """Error codes used by the test error classes."""

    NOT_FOUND = "NOT_FOUND"
    REQUIRED_TOKEN = "REQUIRED_TOKEN"  # ruff:ignore[hardcoded-password-string]


class NotFoundError(BaseError[Literal[Code.NOT_FOUND]]):
    """Test error rendered by the handler."""

    http_status = HTTPStatus.NOT_FOUND


class RequiredTokenError(BaseError[Literal[Code.REQUIRED_TOKEN]]):
    """Test error carrying an auth challenge header."""

    http_status = HTTPStatus.UNAUTHORIZED


@pytest.fixture
def http_request() -> Request:
    """Minimal HTTP request for direct handler calls.

    Returns:
        Request: A bare request with an HTTP scope.
    """
    return Request({"type": "http"})


@pytest.fixture
def app() -> FastAPI:
    """Application with the ``BaseError`` handler registered.

    Returns:
        FastAPI: A fresh application ready for route registration.
    """
    application = FastAPI()
    application.add_exception_handler(BaseError, handle_base_error)
    return application


async def test_renders_status_code_and_detail(http_request: Request) -> None:
    """The handler renders the error's status, code and detail as JSON."""
    error = NotFoundError("gone")

    response = await handle_base_error(http_request, error)

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert json.loads(bytes(response.body)) == {"code": "NOT_FOUND", "detail": "gone"}


async def test_propagates_error_headers(http_request: Request) -> None:
    """Headers attached to the error reach the response."""
    error = RequiredTokenError(headers={"WWW-Authenticate": "Bearer"})

    response = await handle_base_error(http_request, error)

    assert response.headers["www-authenticate"] == "Bearer"


async def test_rejects_foreign_exceptions(http_request: Request) -> None:
    """A non-``BaseError`` argument means misregistration and fails fast."""
    with pytest.raises(TypeError, match="register it only for BaseError"):
        await handle_base_error(http_request, ValueError("x"))


def test_registered_handler_serves_the_error(app: FastAPI) -> None:
    """End to end: a raised error becomes the typed JSON response."""

    @app.get("/boom")
    def boom() -> dict[str, str]:
        raise NotFoundError("gone")

    response = TestClient(app).get("/boom")

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json() == {"code": "NOT_FOUND", "detail": "gone"}


def test_plain_http_exception_stays_default(app: FastAPI) -> None:
    """The ``BaseError`` handler does not hijack plain ``HTTPException``."""

    @app.get("/teapot")
    def teapot() -> dict[str, str]:
        raise HTTPException(status_code=HTTPStatus.IM_A_TEAPOT, detail="short and stout")

    response = TestClient(app).get("/teapot")

    assert response.status_code == HTTPStatus.IM_A_TEAPOT
    assert response.json() == {"detail": "short and stout"}
