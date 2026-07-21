"""Tests for the CI checker ``check_raises``."""

import functools
from typing import Annotated

import fastapi.routing
import pytest
from fastapi import APIRouter, Depends, FastAPI, WebSocket
from fastapi.security import OAuth2PasswordBearer
from walker_helpers import ConflictError, ForbiddenError, NotFoundError, TokenError

from fastapi_typed_errors import Raises, check_raises, with_errors

oauth = OAuth2PasswordBearer(tokenUrl="token")


def dep_token() -> None:
    """Dependency raising directly.

    Raises:
        TokenError: Always.
    """
    raise TokenError("x")


def dep_inner() -> None:
    """Sub-dependency raising directly.

    Raises:
        ConflictError: Always.
    """
    raise ConflictError("x")


def dep_outer(_: Annotated[None, Depends(dep_inner)]) -> None:
    """Dependency that depends on another (nested tree)."""


def plain_dep() -> None:
    """Dependency wrapped in ``functools.partial`` at the call site."""


def ep_match() -> Annotated[dict[str, int], Raises[NotFoundError]]:
    """Raise exactly what it declares.

    Raises:
        NotFoundError: Always.
    """
    raise NotFoundError("boom")


def ep_silent() -> dict[str, int]:
    """Declare nothing and raise nothing.

    Returns:
        dict[str, int]: A constant payload.
    """
    return {"x": 1}


def ep_undeclared() -> Annotated[dict[str, int], Raises[NotFoundError]]:
    """Raise an error it does not declare (and declare one it never raises).

    Raises:
        ForbiddenError: Always.
    """
    raise ForbiddenError("nope")


def ep_overdeclared() -> Annotated[dict[str, int], Raises[NotFoundError, ConflictError]]:
    """Declare more than it raises.

    Raises:
        NotFoundError: Always.
    """
    raise NotFoundError("x")


def ep_with_dep(_: Annotated[None, Depends(dep_token)]) -> Annotated[dict[str, int], Raises[NotFoundError, TokenError]]:
    """Raise directly and via a dependency, declaring both.

    Raises:
        NotFoundError: Always.
    """
    raise NotFoundError("x")


def ep_nested_dep(_: Annotated[None, Depends(dep_outer)]) -> Annotated[dict[str, int], Raises[ConflictError]]:
    """Inherit a raise from a dependency-of-a-dependency.

    Returns:
        dict[str, int]: A constant payload.
    """
    return {"x": 1}


def ep_secured(_: Annotated[str, Depends(oauth)]) -> Annotated[dict[str, int], Raises[NotFoundError]]:
    """Depend on a security scheme, which must be skipped by the walker.

    Raises:
        NotFoundError: Always.
    """
    raise NotFoundError("x")


def ep_partial_dep(
    _: Annotated[None, Depends(functools.partial(plain_dep))],
) -> Annotated[dict[str, int], Raises[NotFoundError]]:
    """Depend on a ``functools.partial`` dependency.

    Raises:
        NotFoundError: Always.
    """
    raise NotFoundError("x")


def ep_bad_hint() -> "Annotated[dict[str, int], Raises[Missing]]":  # ruff:ignore[undefined-name]  # ty: ignore[unresolved-reference]
    """Declare an unresolvable ``Raises`` marker.

    Returns:
        dict[str, int]: A constant payload.
    """
    return {"x": 1}


async def ws_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint the checker must ignore."""
    await websocket.accept()
    await websocket.close()


def test_matching_declarations_are_ok() -> None:
    """A route that raises exactly what it declares is not reported."""
    router = APIRouter()
    router.add_api_route("/match", ep_match, methods=["GET"])
    router.add_api_route("/silent", ep_silent, methods=["GET"])

    report = check_raises(router)

    assert report.ok
    assert report.checked == 2


def test_undeclared_error_reported() -> None:
    """A raised-but-not-declared error appears under ``undeclared``."""
    router = APIRouter()
    router.add_api_route("/u", ep_undeclared, methods=["GET"])

    report = check_raises(router)

    assert not report.ok
    assert report.routes[0].undeclared == (ForbiddenError,)
    assert report.routes[0].overdeclared == (NotFoundError,)


def test_overdeclared_error_reported_by_default() -> None:
    """A declared-but-not-raised error appears under ``overdeclared`` by default."""
    router = APIRouter()
    router.add_api_route("/o", ep_overdeclared, methods=["GET"])

    report = check_raises(router)

    assert report.routes[0].overdeclared == (ConflictError,)
    assert report.routes[0].undeclared == ()


def test_allow_overdeclared_strips_the_route() -> None:
    """With ``allow_overdeclared`` a purely overdeclared route disappears."""
    router = APIRouter()
    router.add_api_route("/o", ep_overdeclared, methods=["GET"])

    report = check_raises(router, allow_overdeclared=True)

    assert report.ok
    assert report.checked == 1


def test_dependency_raise_is_counted() -> None:
    """Errors raised by a dependency are attributed to the route."""
    router = APIRouter()
    router.add_api_route("/d", ep_with_dep, methods=["GET"])

    assert check_raises(router).ok


def test_nested_dependency_raise_is_counted() -> None:
    """Errors raised by a dependency-of-a-dependency are attributed too."""
    router = APIRouter()
    router.add_api_route("/n", ep_nested_dep, methods=["GET"])

    assert check_raises(router).ok


def test_security_scheme_is_skipped() -> None:
    """A security-scheme dependency is skipped without affecting the result."""
    router = APIRouter()
    router.add_api_route("/s", ep_secured, methods=["GET"])

    assert check_raises(router).ok


def test_partial_dependency_is_unwrapped() -> None:
    """A ``functools.partial`` dependency is handled by the security check."""
    router = APIRouter()
    router.add_api_route("/p", ep_partial_dep, methods=["GET"])

    assert check_raises(router).ok


def test_unresolvable_declaration_raises() -> None:
    """An unresolvable ``Raises`` marker fails the check loudly."""
    router = APIRouter()
    router.add_api_route("/bad", ep_bad_hint, methods=["GET"], response_model=dict)

    with pytest.raises(TypeError, match="cannot resolve type hints"):
        check_raises(router)


def test_websocket_route_ignored() -> None:
    """WebSocket routes are not checked."""
    app = FastAPI()
    app.add_api_websocket_route("/ws", ws_endpoint)
    app.router.add_api_route("/match", ep_match, methods=["GET"])

    report = check_raises(app)

    assert report.checked == 1


def test_double_include_deduplicated() -> None:
    """A router included under two prefixes is checked once."""
    child = APIRouter()
    child.add_api_route("/u", ep_undeclared, methods=["GET"])
    app = FastAPI()
    app.include_router(child, prefix="/a")
    app.include_router(child, prefix="/b")

    report = check_raises(app)

    assert report.checked == 1


def test_fastapi_app_target() -> None:
    """A ``FastAPI`` application is accepted as the target."""
    app = FastAPI()
    app.router.add_api_route("/u", ep_undeclared, methods=["GET"])

    assert not check_raises(app).ok


def test_wrapped_router_still_checked() -> None:
    """A ``with_errors`` router is checked from annotations, not responses."""
    router = with_errors(APIRouter())
    router.add_api_route("/u", ep_undeclared, methods=["GET"])

    assert check_raises(router).routes[0].undeclared == (ForbiddenError,)


def test_fallback_without_iter_route_contexts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without ``iter_route_contexts`` a flat ``routes`` walk is used."""
    monkeypatch.delattr(fastapi.routing, "iter_route_contexts")
    router = APIRouter()
    router.add_api_route("/u", ep_undeclared, methods=["GET"])

    report = check_raises(router)

    assert report.routes[0].undeclared == (ForbiddenError,)
