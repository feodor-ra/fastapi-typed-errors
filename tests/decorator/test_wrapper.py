"""Tests for ``with_errors()`` and the ``add_api_route`` patch."""

import functools
from collections.abc import Callable
from enum import StrEnum
from http import HTTPStatus
from typing import Annotated, Any, Literal, cast

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel

from fastapi_typed_errors import BaseError, Raises, with_errors


class Code(StrEnum):
    """Error codes used by the test error classes."""

    NOT_FOUND = "NOT_FOUND"
    GONE = "GONE"
    FORBIDDEN = "FORBIDDEN"
    CONFLICT = "CONFLICT"


class NotFoundError(BaseError[Literal[Code.NOT_FOUND]]):
    """404 error with a description."""

    http_status = HTTPStatus.NOT_FOUND
    description = "Entity does not exist"


class GoneError(BaseError[Literal[Code.GONE]]):
    """Second 404 error for one-status grouping."""

    http_status = HTTPStatus.NOT_FOUND
    description = "Moved away"


class ForbiddenError(BaseError[Literal[Code.FORBIDDEN]]):
    """403 error without a description."""

    http_status = HTTPStatus.FORBIDDEN


class ConflictError(BaseError[Literal[Code.CONFLICT]]):
    """409 error for imperative registration tests."""

    http_status = HTTPStatus.CONFLICT


class Item(BaseModel):
    """Success payload."""

    item_id: int


type AliasedItem = Annotated[Item, Raises[NotFoundError]]
type RawStream = StreamingResponse


def conflicting(q: int = 1) -> Annotated[Item, Raises[ConflictError]]:
    """Plain module-level endpoint for imperative registration tests.

    Args:
        q: Arbitrary query parameter.

    Returns:
        Annotated[Item, Raises[ConflictError]]: The success payload.
    """
    return Item(item_id=q)


@pytest.fixture
def router() -> APIRouter:
    """Router with ``Raises`` handling enabled.

    Returns:
        APIRouter: A fresh wrapped router.
    """
    return with_errors(APIRouter())


def _responses(router: APIRouter, path: str, method: str = "get") -> dict[str, Any]:
    """Extract a route's OpenAPI responses mapping.

    Args:
        router: Router carrying the registered route.
        path: Route path to look up.
        method: HTTP method of the route.

    Returns:
        dict[str, Any]: The OpenAPI ``responses`` of the route.
    """
    app = FastAPI()
    app.include_router(router)
    return app.openapi()["paths"][path][method]["responses"]


def test_returns_the_same_router_instance() -> None:
    """``with_errors`` patches in place and preserves identity."""
    router = APIRouter()

    assert with_errors(router) is router


def test_wrapping_twice_is_a_noop(router: APIRouter) -> None:
    """A second ``with_errors`` call does not re-wrap ``add_api_route``."""
    patched = with_errors(router).add_api_route

    assert getattr(patched, "_fastapi_typed_errors_wrapped", False) is True
    inner = getattr(patched, "__wrapped__", None)
    assert inner is not None
    assert getattr(inner, "_fastapi_typed_errors_wrapped", False) is False


def test_injects_statuses_and_descriptions(router: APIRouter) -> None:
    """Declared errors land in ``responses`` grouped by status."""

    @router.get("/items")
    def endpoint() -> Annotated[Item, Raises[NotFoundError, ForbiddenError]]:
        raise NotImplementedError

    responses = _responses(router, "/items")

    assert responses["404"]["description"] == "Entity does not exist"
    assert responses["403"]["description"] == HTTPStatus.FORBIDDEN.phrase


def test_one_status_union_gets_discriminator(router: APIRouter) -> None:
    """Two errors on one status build a discriminated ``oneOf`` union."""

    @router.get("/union")
    def endpoint() -> Annotated[Item, Raises[NotFoundError, GoneError]]:
        raise NotImplementedError

    entry = _responses(router, "/union")["404"]

    schema = entry["content"]["application/json"]["schema"]
    assert "oneOf" in schema
    assert schema["discriminator"]["propertyName"] == "code"
    assert entry["description"] == "Entity does not exist; Moved away"


def test_explicit_responses_win_per_status(router: APIRouter) -> None:
    """A user-provided entry replaces the derived one wholesale for its status."""

    @router.get("/override", responses={404: {"description": "Manual"}, 418: {"description": "Teapot"}})
    def endpoint() -> Annotated[Item, Raises[NotFoundError, ForbiddenError]]:
        raise NotImplementedError

    responses = _responses(router, "/override")

    assert responses["404"]["description"] == "Manual"
    assert responses["418"]["description"] == "Teapot"
    assert responses["403"]["description"] == HTTPStatus.FORBIDDEN.phrase


def test_marker_free_endpoint_passes_through(router: APIRouter) -> None:
    """Without markers the 200 inference stays intact and nothing is injected."""

    @router.get("/plain")
    def endpoint() -> Item:
        raise NotImplementedError

    responses = _responses(router, "/plain")

    assert responses["200"]["content"]["application/json"]["schema"]["$ref"].endswith("Item")
    assert "404" not in responses


def test_endpoint_without_annotation_passes_through(router: APIRouter) -> None:
    """An unannotated endpoint registers exactly like on a stock router."""

    @router.get("/bare")
    def endpoint():  # ruff:ignore[missing-return-type-private-function]
        return {"ok": True}

    assert "404" not in _responses(router, "/bare")


def test_explicit_response_model_is_kept(router: APIRouter) -> None:
    """An explicit ``response_model`` skips normalization; injection still happens."""

    @router.get("/explicit", response_model=Item)
    def endpoint() -> Annotated[StreamingResponse, Raises[NotFoundError]]:
        raise NotImplementedError

    responses = _responses(router, "/explicit")

    assert "404" in responses
    assert responses["200"]["content"]["application/json"]["schema"]["$ref"].endswith("Item")


def test_response_annotation_normalized(router: APIRouter) -> None:
    """A ``Response`` subclass under ``Annotated`` gets ``response_model=None``."""

    @router.get("/stream")
    def endpoint() -> Annotated[StreamingResponse, Raises[NotFoundError]]:
        raise NotImplementedError

    responses = _responses(router, "/stream")

    assert "404" in responses
    assert responses["200"]["content"]["application/json"]["schema"] == {}


def test_none_annotation_normalized(router: APIRouter) -> None:
    """``Annotated[None, Raises[...]]`` keeps stock empty-response semantics."""

    @router.get("/nothing", status_code=HTTPStatus.NO_CONTENT)
    def endpoint() -> Annotated[None, Raises[ForbiddenError]]:
        raise NotImplementedError

    responses = _responses(router, "/nothing")

    assert "403" in responses
    assert "content" not in responses["204"]


def test_alias_return_annotation(router: APIRouter) -> None:
    """A PEP 695 ``type`` alias is unwrapped before marker extraction."""

    @router.get("/alias")
    def endpoint() -> AliasedItem:
        raise NotImplementedError

    assert "404" in _responses(router, "/alias")


def test_alias_nested_inside_annotated(router: APIRouter) -> None:
    """Markers inside an aliased ``Annotated`` base are merged with outer ones."""

    @router.get("/nested")
    def endpoint() -> Annotated[AliasedItem, Raises[ForbiddenError]]:
        raise NotImplementedError

    responses = _responses(router, "/nested")

    assert "404" in responses
    assert "403" in responses


def test_alias_base_is_normalized(router: APIRouter) -> None:
    """An aliased ``Response`` subclass still triggers normalization."""

    @router.get("/rawalias")
    def endpoint() -> Annotated[RawStream, Raises[NotFoundError]]:
        raise NotImplementedError

    responses = _responses(router, "/rawalias")

    assert "404" in responses
    assert responses["200"]["content"]["application/json"]["schema"] == {}


def test_union_wrapped_marker_detected(router: APIRouter) -> None:
    """``Annotated[Item, Raises[...]] | None`` does not drop the marker."""

    @router.get("/optional")
    def endpoint() -> Annotated[Item, Raises[NotFoundError]] | None:
        raise NotImplementedError

    assert "404" in _responses(router, "/optional")


def test_unresolvable_hints_without_marker_pass_through(router: APIRouter) -> None:
    """The ``TYPE_CHECKING`` import pattern registers exactly like on stock FastAPI."""

    def endpoint() -> "MissingModel":  # ruff:ignore[undefined-name]  # ty: ignore[unresolved-reference]
        ...

    router.add_api_route("/orm", endpoint, methods=["GET"], response_model=Item)

    responses = _responses(router, "/orm")
    assert responses["200"]["content"]["application/json"]["schema"]["$ref"].endswith("Item")


def test_unresolvable_parameter_hints_pass_through(router: APIRouter) -> None:
    """Broken parameter hints with no return annotation register exactly like on stock FastAPI."""

    def endpoint(_body: "MissingModel"):  # ruff:ignore[missing-return-type-private-function, undefined-name]  # ty: ignore[unresolved-reference]
        return {"ok": True}

    stock = APIRouter()
    stock.add_api_route("/broken", endpoint, methods=["GET"], response_model=Item)

    router.add_api_route("/broken", endpoint, methods=["GET"], response_model=Item)

    assert len(router.routes) == len(stock.routes) == 1


def test_bare_raises_annotation_rejected(router: APIRouter) -> None:
    """A bare ``-> Raises[...]`` gets a spelling hint instead of a typing error."""

    def endpoint() -> Raises[NotFoundError]: ...

    with pytest.raises(TypeError, match="must appear inside Annotated"):
        router.add_api_route("/bad", endpoint, methods=["GET"])


def test_unparametrized_raises_rejected(router: APIRouter) -> None:
    """The bare ``Raises`` class inside ``Annotated`` demands parametrization."""

    def endpoint() -> Annotated[Item, Raises]:
        raise NotImplementedError

    with pytest.raises(TypeError, match="must be parametrized"):
        router.add_api_route("/bad", endpoint, methods=["GET"])


def test_unresolvable_hints_with_marker_rejected(router: APIRouter) -> None:
    """A string annotation mentioning ``Raises`` fails fast with a clear error."""

    def endpoint() -> "Annotated[Item, Raises[MissingError]]":  # ruff:ignore[undefined-name]  # ty: ignore[unresolved-reference]
        raise NotImplementedError

    with pytest.raises(TypeError, match="must be resolvable"):
        router.add_api_route("/bad", endpoint, methods=["GET"])


def test_missing_endpoint_delegates_the_error(router: APIRouter) -> None:
    """A non-callable endpoint is left to the original signature to reject."""
    broken = cast(Callable[..., Any], None)

    with pytest.raises(TypeError):
        router.add_api_route("/bad", broken, methods=["GET"])


def test_endpoint_passed_as_keyword(router: APIRouter) -> None:
    """App-style calls with ``endpoint=`` as a keyword are handled."""
    router.add_api_route("/kw", endpoint=conflicting, methods=["GET"])

    assert "409" in _responses(router, "/kw")


def test_path_passed_as_keyword(router: APIRouter) -> None:
    """Fully keyword-based registration is handled."""
    router.add_api_route(path="/pkw", endpoint=conflicting, methods=["GET"])

    assert "409" in _responses(router, "/pkw")


def test_partial_endpoint_unwrapped(router: APIRouter) -> None:
    """``functools.partial`` endpoints expose their annotations."""
    router.add_api_route("/partial", functools.partial(conflicting, q=2), methods=["GET"])

    assert "409" in _responses(router, "/partial")


def test_wrapped_endpoint_unwrapped(router: APIRouter) -> None:
    """``functools.wraps`` chains expose their annotations."""

    @functools.wraps(conflicting)
    def decorated(*_args: object, **_kwargs: object) -> object:
        return conflicting()

    router.add_api_route("/wrapped", decorated, methods=["GET"])

    assert "409" in _responses(router, "/wrapped")


def test_callable_instance_unwrapped(router: APIRouter) -> None:
    """Callable instances expose annotations via ``type(obj).__call__``."""

    class Endpoint:
        def __call__(self) -> Annotated[Item, Raises[ConflictError]]:
            return Item(item_id=3)

    router.add_api_route("/callable", Endpoint(), methods=["GET"])

    assert "409" in _responses(router, "/callable")


def test_app_router_wrapping_covers_app_decorators() -> None:
    """Wrapping ``app.router`` makes app-level decorators inject too."""
    app = FastAPI()
    with_errors(app.router)

    @app.get("/direct")
    def endpoint() -> Annotated[Item, Raises[NotFoundError]]:
        raise NotImplementedError

    assert "404" in app.openapi()["paths"]["/direct"]["get"]["responses"]


def test_include_router_keeps_injected_responses() -> None:
    """Injected entries survive ``include_router`` with prefixes and router-level responses."""
    parent = APIRouter(prefix="/p", responses={500: {"description": "Boom"}})
    wrapped = with_errors(parent)

    @wrapped.get("/n")
    def endpoint() -> Annotated[Item, Raises[NotFoundError]]:
        raise NotImplementedError

    app = FastAPI()
    app.include_router(parent)

    responses = app.openapi()["paths"]["/p/n"]["get"]["responses"]
    assert "404" in responses
    assert "500" in responses


def test_included_wrapped_router_serves_requests(router: APIRouter) -> None:
    """Identity preservation: the patched router still dispatches at runtime."""

    @router.get("/ping")
    def endpoint() -> Item:
        return Item(item_id=1)

    app = FastAPI()
    app.include_router(router)

    assert TestClient(app).get("/ping").json() == {"item_id": 1}
