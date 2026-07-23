---
title: Core
---

# Core

The `core` layer is self-sufficient: it can be used without the decorator and without analysis. It gives you four things — the `BaseError` class, the `ErrorResponse` model, the `error_models()` builder for `responses={}`, and the `handle_base_error` handler.

## BaseError

Every error is a subclass of `BaseError` parametrized with its code. The code is passed as a `Literal` in the generic parameter; only `http_status` is declared in the class body.

```python
from enum import StrEnum
from http import HTTPStatus
from typing import Literal

from fastapi_typed_errors import BaseError


class ErrorCode(StrEnum):
    NOT_FOUND = "NOT_FOUND"


class NotFoundError(BaseError[Literal[ErrorCode.NOT_FOUND]]):
    http_status = HTTPStatus.NOT_FOUND
    description = "Entity not found"  # (1)!
```

1. `description: ClassVar[str | None]` is optional; see [the default detail](#the-default-detail).

At class creation the `BaseErrorMeta` metaclass extracts the code from the generic parameter and **derives** two class attributes:

| Attribute | What it is |
|---|---|
| `NotFoundError.error_code` | the code value (`ErrorCode.NOT_FOUND`) |
| `NotFoundError.model` | the parametrized response model `ErrorResponse[Literal[NOT_FOUND]]` |

`BaseError` subclasses `fastapi.HTTPException`, so `raise NotFoundError(...)` works like a regular FastAPI exception.

### Codes: StrEnum or a bare Literal

A code is any member of a `StrEnum` **or** a bare string in a `Literal`. The `T: str` bound covers both:

```python
class NotFoundError(BaseError[Literal[ErrorCode.NOT_FOUND]]): ...  # StrEnum member


class BareError(BaseError[Literal["BARE_CODE"]]): ...  # bare string
```

!!! warning "Parametrization mistakes are caught eagerly"

    Parametrizing with anything but a `TypeVar` (an intermediate base) or a `Literal` with exactly one string fails with `TypeError` **at class definition time**, not as a dangerous 500 at request time:

    ```python
    class Bad(BaseError[str]): ...  # TypeError: BaseError expects Literal with exactly one string code
    ```

### The default detail

If you don't pass `detail` when raising, it is taken from `description`, and if there is none — from the HTTP status phrase.

```python
NotFoundError().detail  # -> "Entity not found" (from description)
ForbiddenError().detail  # -> "Forbidden" (status phrase, if there is no description)
NotFoundError("gone").detail  # -> "gone" (an explicit detail wins)
```

Headers are passed through to `HTTPException`:

```python
raise RequiredTokenError(headers={"WWW-Authenticate": "Bearer"})
```

## ErrorResponse

The response body is the `ErrorResponse[T]` model with two fields:

```python
class ErrorResponse[T: str](BaseModel):
    code: T  # the exact Literal code
    detail: str
```

`to_response()` builds it from the error instance — that is what the handler does:

```python
NotFoundError("gone").to_response().model_dump()
# {"code": "NOT_FOUND", "detail": "gone"}
```

!!! note "Clean titles in OpenAPI"

    By default pydantic embeds the `repr()` of the enum member into a parametrized model's title — angle brackets included. The package sets a `model_title_generator` that renders `ErrorResponse[NOT_FOUND]` instead of `ErrorResponse[Literal[<ErrorCode.NOT_FOUND: 'NOT_FOUND'>]]`.

## error_models()

`error_models()` builds the model for the `"model"` key of a route's `responses={}`.

```python
from fastapi_typed_errors import error_models
```

- **One class** → its parametrized model directly.
- **Several classes** → a discriminated `oneOf` union on the `code` field (Swagger shows a picker by code).

```python
@app.get(
    "/items/{item_id}",
    responses={
        404: {"model": error_models(NotFoundError)},  # one model
        403: {"model": error_models(ForbiddenError, GoneError)},  # oneOf union
    },
)
def get_item(item_id: int) -> Item: ...
```

A union of two errors on one status yields `oneOf` with a discriminator in OpenAPI — Swagger UI shows a variant dropdown by code:

```json
{
  "oneOf": [
    { "$ref": "#/components/schemas/ErrorResponse_Literal_FORBIDDEN__" },
    { "$ref": "#/components/schemas/ErrorResponse_Literal_GONE__" }
  ],
  "discriminator": {
    "propertyName": "code",
    "mapping": {
      "FORBIDDEN": "#/components/schemas/ErrorResponse_Literal_FORBIDDEN__",
      "GONE": "#/components/schemas/ErrorResponse_Literal_GONE__"
    }
  }
}
```

Repeated classes are deduplicated. But one code shared by two **distinct** models inside a union is impossible — a discriminator requires unique values:

```python
error_models(NotFoundError, AnotherWithSameCode)
# TypeError: error code 'NOT_FOUND' is shared by multiple distinct response models
```

!!! tip "The manual way is always available"

    The `core` layer needs no decorator. `error_models()` can be written into `responses={}` by hand — that is the "core-only" mode. The decorator ([`with_errors`](decorator.md)) simply removes this manual work.

## The handler

`handle_base_error` is the single handler for every `BaseError`. It is registered explicitly:

```python
from fastapi_typed_errors import BaseError, handle_base_error

app.add_exception_handler(BaseError, handle_base_error)
```

It returns a `JSONResponse` with the status, a `{code, detail}` body and the error's headers.

!!! info "Why the `(Request, Exception)` signature"

    Starlette types handlers as `(Request, Exception) -> ...`, and function parameters are contravariant — a narrow `BaseError` would force a `# type: ignore` onto the registration line of **every** consumer. So the signature is wide, and misregistration (for a foreign exception type) is caught at runtime with a clear `TypeError`.

Plain `HTTPException` is not intercepted: Starlette walks the `__mro__`, so the `BaseError` handler overrides the default one only for its own subclasses.

## BaseErrorMeta

The metaclass is public — in case you mix `BaseError` with `ABC` or another custom metaclass (otherwise there is a metaclass conflict). It is **deliberately not re-exported** from the package root; import it from `core.base`:

```python
from abc import ABCMeta
from fastapi_typed_errors.core.base import BaseErrorMeta


class Meta(BaseErrorMeta, ABCMeta): ...
```

Details are in [Customization](customization.md#abc).

---

**Next:** the [decorator](decorator.md) — how to stop writing `responses={}` by hand.
