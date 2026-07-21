# fastapi-typed-errors

Typed error responses for FastAPI: `Literal` error codes in OpenAPI, discriminated `oneOf` unions, and a single source of truth — the error class itself.

> **Status: draft.** Layers 1 (`core`) and 2 (`decorator`) are implemented; the AST analysis layer (CI checker + `auto`) is coming.

## Requirements

- Python **3.12+** (PEP 695 generics)
- FastAPI ≥ 0.115, Pydantic ≥ 2.9

## Quick start

Declare errors once, right in the return annotation — `with_errors` fills `responses={}` for you:

```python
from enum import StrEnum
from http import HTTPStatus
from typing import Annotated, Literal

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

from fastapi_typed_errors import BaseError, Raises, handle_base_error, with_errors


class ErrorCode(StrEnum):
    NOT_FOUND = "NOT_FOUND"
    FORBIDDEN = "FORBIDDEN"


class NotFoundError(BaseError[Literal[ErrorCode.NOT_FOUND]]):
    http_status = HTTPStatus.NOT_FOUND
    description = "Requested entity does not exist"


class ForbiddenError(BaseError[Literal[ErrorCode.FORBIDDEN]]):
    http_status = HTTPStatus.FORBIDDEN


class Item(BaseModel):
    item_id: int


app = FastAPI()
app.add_exception_handler(BaseError, handle_base_error)

router = with_errors(APIRouter())


@router.get("/items/{item_id}")
def get_item(item_id: int) -> Annotated[Item, Raises[NotFoundError, ForbiddenError]]:
    if item_id == 0:
        raise NotFoundError(f"No item {item_id}")
    return Item(item_id=item_id)


app.include_router(router)
```

The error response body is always:

```json
{"code": "NOT_FOUND", "detail": "No item 0"}
```

OpenAPI gets a `404` and a `403` entry with the **exact** `Literal` code each; several errors sharing one status become a discriminated `oneOf` union automatically. The success (`200`) schema stays clean — the `Raises` marker is invisible to pydantic.

`with_errors(router)` returns the **same** `APIRouter` instance with its `add_api_route` patched on the instance, so object identity is preserved: `include_router`, websockets, imperative `add_api_route(...)` calls and app-level decorators all work natively. For an application, wrap its router: `with_errors(app.router)`.

## Core layer only

The decorator layer is optional sugar — `responses={}` can always be filled by hand with `error_models()`:

```python
@app.get(
    "/items/{item_id}",
    responses={
        404: {"model": error_models(NotFoundError)},
        403: {"model": error_models(ForbiddenError)},
    },
)
def get_item(item_id: int) -> Item: ...
```

## Notes

- Error codes are any `StrEnum` members you bring, or plain strings: `BaseError[Literal["NOT_FOUND"]]`.
- Wrap **before** registering: routes added to the router before `with_errors(router)` are not retrofitted.
- An explicit `responses={<status>: ...}` on the route wins wholesale over `Raises`-derived entries for the same status. Use `int` status keys.
- Shared error tuples work in both spellings: `Raises[*TOKEN_ERRORS]` and `Raises(*TOKEN_ERRORS)`.
- Markers are found through PEP 695 `type` aliases, nested `Annotated` bases and union arms (`Annotated[Item, Raises[...]] | None`) — a declared `Raises` is never dropped silently.
- Unresolvable return annotations without `Raises` (the `if TYPE_CHECKING:` import pattern) pass through untouched, exactly like stock FastAPI; with `Raises` mentioned they fail fast with a clear `TypeError`.
- `-> Annotated[Response subclass, Raises[...]]` and `-> Annotated[None, Raises[...]]` are normalized to `response_model=None`, restoring stock FastAPI semantics for raw-response and empty routes.
- Bare stream returns (`-> Annotated[AsyncIterator[X], Raises[...]]`, the SSE/JSONL feature) are not supported — annotate a `Response` subclass instead.
- `Raises` metadata on a router that was **not** passed through `with_errors` is inert — nothing is injected and nothing fails (the upcoming analysis layer will catch such drift).
- Status descriptions come from each error's `description`; several errors on one status get their descriptions joined with `;`, and the HTTP status phrase is the fallback.
- Customize the response body by overriding `response_base` with your own generic subclass of `ErrorResponse`.
- `BaseError` subclasses `fastapi.HTTPException`; mixing it with `ABC` and other custom-metaclass bases raises a metaclass conflict. The metaclass is public for exactly this case — build a combined one: `class Meta(BaseErrorMeta, ABCMeta): ...` (`from fastapi_typed_errors.core.base import BaseErrorMeta`; deliberately not re-exported from the package root).
- The handler is registered explicitly — the same way you call `app.add_middleware(...)`; the package does not touch your app behind your back. `handle_base_error` is typed `(Request, Exception)` to match Starlette's handler contract, so the registration line stays clean under every type checker; registering it for a non-`BaseError` exception type fails fast with a `TypeError` at runtime.
