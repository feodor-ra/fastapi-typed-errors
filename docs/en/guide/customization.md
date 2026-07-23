---
title: Customization
---

# Customization and extension

## Your own response model

By default the error body is `{code, detail}`. To add your own fields (an envelope with a `status`, say), subclass `ErrorResponse` generically and point your base error class's `response_base` at it.

```python
from typing import Any, ClassVar, Literal

from fastapi_typed_errors import BaseError, ErrorResponse


class MyErrorResponse[T: str](ErrorResponse[T]):
    status: Literal["error"] = "error"  # (1)!


class AppError[T: str](BaseError[T]):
    response_base: ClassVar[type[ErrorResponse[Any]]] = MyErrorResponse


class NotFoundError(AppError[Literal["NOT_FOUND"]]):
    http_status = HTTPStatus.NOT_FOUND
```

1. The extra field sits **next to** `code`/`detail`.

The response body becomes:

```json
{ "status": "error", "code": "NOT_FOUND", "detail": "..." }
```

!!! danger "Flat extensions only"

    The shape must stay **flat**. Nested envelopes like `{"status": ..., "data": {"code": ...}}` are not supported: pydantic discriminated unions require the `code` discriminator at the **top level** of the model, otherwise `error_models()` breaks for several errors on one status.

## Bare string codes

You bring your own enum — but it isn't required. A code can be a bare string in a `Literal`:

```python
class BareError(BaseError[Literal["BARE_CODE"]]):
    http_status = HTTPStatus.CONFLICT
```

A `StrEnum` is nicer when there are many codes and you want a single registry; a bare `Literal` — for one-offs.

## description and headers

- `description: ClassVar[str | None]` — the default `detail` and the status description in OpenAPI.
- Headers pass through to `HTTPException`:

```python
class RequiredTokenError(BaseError[Literal["REQUIRED_TOKEN"]]):
    http_status = HTTPStatus.UNAUTHORIZED
    description = "Token required"


raise RequiredTokenError(headers={"WWW-Authenticate": "Bearer"})
```

## Intermediate bases

Factor shared configuration (your own `response_base`, a common code prefix) into an intermediate generic base — it is parametrized with a `TypeVar` and is **not** required to declare a code:

```python
class AppError[T: str](BaseError[T]):
    response_base = MyErrorResponse
    # no http_status here — this is not a concrete error


class NotFoundError(AppError[Literal["NOT_FOUND"]]):
    http_status = HTTPStatus.NOT_FOUND
```

The metaclass skips bases parametrized with a `TypeVar` and derives `error_code`/`model` only for concrete subclasses.

## ABC compatibility { #abc }

`BaseError` subclasses `HTTPException` and uses the `BaseErrorMeta` metaclass. Mixing it with `ABC` (which has its own `ABCMeta`) triggers a metaclass conflict. The fix is a combined metaclass:

```python
from abc import ABCMeta, abstractmethod
from fastapi_typed_errors.core.base import BaseErrorMeta  # (1)!


class ABCErrorMeta(BaseErrorMeta, ABCMeta): ...


class AbstractError[T: str](BaseError[T], metaclass=ABCErrorMeta):
    @abstractmethod
    def audit(self) -> None: ...
```

1. `BaseErrorMeta` is deliberately **not** re-exported from the package root — import it from `fastapi_typed_errors.core.base`.

## Explicit registration is a principle

The package hides no magic behind `install(app)` helpers. The handler is wired by hand:

```python
app.add_exception_handler(BaseError, handle_base_error)
```

This is the same style as `app.add_middleware(...)`: configuring the app stays explicit and under your control.

---

**Next:** [Recipes](recipes.md) — common practical patterns.
