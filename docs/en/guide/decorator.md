---
title: Decorator
---

# The decorator: with_errors and Raises

The `decorator` layer removes the manual `responses={}`. Errors are declared right in the endpoint's return annotation with the `Raises` marker, and `with_errors` fills `responses` at registration.

## with_errors

`with_errors(router)` returns the **same** `APIRouter` object with its `add_api_route` patched in place (an instance patch), and teaches it to understand `Raises`.

```python
from fastapi import APIRouter
from fastapi_typed_errors import with_errors

router = with_errors(APIRouter())
```

!!! abstract "Why the same object, not a wrapper"

    In FastAPI 0.139 the lazy `include_router` compares the included router **by identity** (`included_router.original_router is self`). Any duck-typed wrapper passes OpenAPI generation but silently 404s at runtime. Preserving identity makes `include_router`, websockets, app-level decorators and imperative registration work natively on every FastAPI version.

The single interception point is `add_api_route`, where all 8 verb decorators, `api_route` and the `app.*` methods converge. For an application, wrap its router:

```python
with_errors(app.router)
```

The patch is **idempotent**: a second `with_errors` is a no-op.

!!! warning "Wrap before registering"

    Routes added to the router **before** `with_errors(router)` are not retrofitted. Wrap first, then register.

## The Raises marker

`Raises[...]` is inert `Annotated` metadata in the return annotation. It lists the errors a route can raise.

```python
from typing import Annotated
from fastapi_typed_errors import Raises


@router.get("/items/{item_id}")
def get_item(item_id: int) -> Annotated[Item, Raises[NotFoundError, ForbiddenError]]:
    if item_id == 0:
        raise NotFoundError("gone")
    return Item(item_id=item_id)
```

The success (`200`) schema stays clean — pydantic ignores the marker. Several errors on one status become a discriminated `oneOf` union.

### Spellings and shared tuples

Shared error sets (auth errors, say) are convenient to factor into a tuple and unpack:

```python
from typing import Final

TOKEN_ERRORS: Final = (RequiredTokenError, InvalidTokenError, WrongTokenTypeError)


# both spellings are equivalent:
def a() -> Annotated[Item, Raises[*TOKEN_ERRORS]]: ...
def b() -> Annotated[Item, Raises(*TOKEN_ERRORS)]: ...
```

The constructor form `Raises(*TOKEN_ERRORS)` is the statically clean fallback for type checkers.

!!! note "Validation is at import time"

    `Raises[...]` validates each member as soon as it is evaluated (i.e. at module import): it must be a `BaseError` subclass with a declared `error_code` and `http_status`, and the list is non-empty. Otherwise — a `TypeError` naming the offender.

### What Raises finds in the annotation

The marker is found through PEP 695 `type` aliases, nested `Annotated` bases and union arms — a declared marker is **never dropped silently**:

```python
type ItemNF = Annotated[Item, Raises[NotFoundError]]


def a() -> ItemNF: ...  # alias
def b() -> Annotated[Item, Raises[NotFoundError]] | None: ...  # union wrapper
```

## Merge semantics

What ends up in the final `responses`:

- **`Raises` markers** and (with `auto=True`) the **errors found by the walker** are unioned.
- An **explicit `responses={<status>: ...}`** on the route beats the derived entries **wholesale for that status** (no model merging). Use `int` status keys.
- Router-level `responses` are merged by FastAPI itself and lose to per-route ones.

```python
@router.get("/x", responses={404: {"description": "Custom", "model": MyModel}})
def endpoint() -> Annotated[Item, Raises[NotFoundError]]:  # 404 comes from responses, not from Raises
    ...
```

Status descriptions come from the classes' `description`; several on one status are joined with `;`, with the HTTP status phrase as the fallback.

## Response and None normalization

`-> Annotated[Response subclass, Raises[...]]` and `-> Annotated[None, Raises[...]]` are normalized to `response_model=None` — otherwise FastAPI, not seeing through `Annotated`, would treat it as a model and fail with `FastAPIError` (or grow a spurious `null` schema).

```python
from fastapi.responses import StreamingResponse


@router.get("/download")
def download() -> Annotated[StreamingResponse, Raises[NotFoundError]]: ...
```

!!! danger "Bare stream returns are not supported"

    `-> Annotated[AsyncIterator[X], Raises[...]]` (SSE/JSONL) is not supported: FastAPI can't see the stream type through `Annotated`, and there is no public way to set `stream_item_type`. For streaming with `Raises`, annotate a `Response` subclass.

## auto=True { #auto }

`with_errors(router, auto=True)` fills `responses` **without a single marker**: at registration each endpoint and **its whole dependency tree** are statically walked (with the same walker as the [CI checker](checker.md)), and the found errors flow into `responses` — unioned with any `Raises` you do write.

```python
from fastapi import Depends

router = with_errors(APIRouter(), auto=True)


def current_user(token: Annotated[str, Depends(oauth)]) -> User:
    if not token:
        raise RequiredTokenError("token required")  # (1)!
    ...


@router.get("/items/{item_id}")
def get_item(item_id: int, user: Annotated[User, Depends(current_user)]) -> Item:
    if item_id == 0:
        raise NotFoundError("gone")  # (2)!
    return Item(item_id=item_id)
```

1. An error from a dependency — also lands in the route's `responses` (401).
2. An error from the endpoint body (404).

The result: `responses` contains both `404` (from the endpoint) and `401` (from the dependency) — with no explicit declarations.

!!! info "How it works"

    The walker collects `raise` statements from the endpoint's source and its helpers, and the `Depends` tree is rebuilt at registration via FastAPI's public functions. Security schemes (`OAuth2PasswordBearer` and the like) are skipped — they raise a plain `HTTPException`, not a `BaseError`. The walker's limitations (local variables, `self.method()`, dynamics) are the same as the checker's — see [Limitations](limitations.md#walker).

!!! tip "auto vs Raises"

    - `Raises` — a precise, checkable declaration (the checker verifies it against reality).
    - `auto` — "document what I already raise", with no manual work.

    They combine: declare part of it explicitly (dynamic `raise`s the AST can't see, for instance), and `auto` picks up the rest.

The `auto` flag is set on the **first** `with_errors` call (the patch is idempotent, so a later call does not change it).

## Other subtleties

- **Endpoint unwrapping** (for reading annotations only): `functools.partial`, `functools.wraps` chains, callable instances (`type(obj).__call__`). The original object is always what gets registered.
- **Unresolvable annotations** without a mention of `Raises` (the `if TYPE_CHECKING:` pattern) pass through like stock FastAPI; with `Raises` mentioned — a fast `TypeError`.
- **A marker on an unwrapped router** is inert — nothing is injected and nothing fails. The [CI checker](checker.md) reads annotations directly, so it still catches such drift.

---

**Next:** the [CI checker](checker.md) — comparing what's declared against what's actually raised.
