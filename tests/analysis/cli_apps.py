"""Importable FastAPI apps for the CLI tests (loaded via ``module:attribute``)."""

from typing import Annotated

from fastapi import FastAPI
from walker_helpers import ConflictError, ForbiddenError, NotFoundError

from fastapi_typed_errors import Raises


def _ok() -> Annotated[dict[str, int], Raises[NotFoundError]]:
    raise NotFoundError("x")


def _bad() -> Annotated[dict[str, int], Raises[NotFoundError]]:
    raise ForbiddenError("x")


def _over() -> Annotated[dict[str, int], Raises[NotFoundError, ConflictError]]:
    raise NotFoundError("x")


def _bad_hint() -> "Annotated[dict[str, int], Raises[Missing]]":  # ruff:ignore[undefined-name]  # ty: ignore[unresolved-reference]
    return {"x": 1}


app_ok = FastAPI()
app_ok.router.add_api_route("/ok", _ok, methods=["GET"])

app_bad = FastAPI()
app_bad.router.add_api_route("/bad", _bad, methods=["GET"])

app_over = FastAPI()
app_over.router.add_api_route("/over", _over, methods=["GET"])

app_typeerror = FastAPI()
app_typeerror.router.add_api_route("/e", _bad_hint, methods=["GET"], response_model=dict)

not_an_app = 42
