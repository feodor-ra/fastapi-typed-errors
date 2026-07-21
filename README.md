# fastapi-typed-errors

Typed error responses for FastAPI: `Literal` error codes in OpenAPI, discriminated `oneOf` unions, and a single source of truth — the error class itself.

> **Status: draft.** Layer 1 (`core`) only; the `with_errors` decorator and AST analysis layers are coming.

## Requirements

- Python **3.12+** (PEP 695 generics)
- FastAPI ≥ 0.115, Pydantic ≥ 2.7

## Quick start

```python
from enum import StrEnum
from http import HTTPStatus
from typing import Literal

from fastapi import FastAPI
from fastapi_typed_errors import BaseError, error_models, handle_base_error


class ErrorCode(StrEnum):
    NOT_FOUND = "NOT_FOUND"
    FORBIDDEN = "FORBIDDEN"


class NotFoundError(BaseError[Literal[ErrorCode.NOT_FOUND]]):
    http_status = HTTPStatus.NOT_FOUND
    description = "Requested entity does not exist"


class ForbiddenError(BaseError[Literal[ErrorCode.FORBIDDEN]]):
    http_status = HTTPStatus.FORBIDDEN


app = FastAPI()
app.add_exception_handler(BaseError, handle_base_error)


@app.get(
    "/items/{item_id}",
    responses={
        404: {"model": error_models(NotFoundError)},
        403: {"model": error_models(ForbiddenError)},
    },
)
def get_item(item_id: int) -> dict[str, int]:
    if item_id == 0:
        raise NotFoundError(f"No item {item_id}")
    return {"item_id": item_id}
```

The response body is always:

```json
{"code": "NOT_FOUND", "detail": "No item 0"}
```

and OpenAPI shows the **exact** `Literal` code per status — several errors on one status become a discriminated `oneOf` union via `error_models(A, B, ...)`.

## Notes

- Error codes are any `StrEnum` members you bring, or plain strings: `BaseError[Literal["NOT_FOUND"]]`.
- Customize the response body by overriding `response_base` with your own generic subclass of `ErrorResponse`.
- `BaseError` subclasses `fastapi.HTTPException`; mixing it with `ABC` and other custom-metaclass bases raises a metaclass conflict. The metaclass is public for exactly this case — build a combined one: `class Meta(BaseErrorMeta, ABCMeta): ...` (`from fastapi_typed_errors.core.base import BaseErrorMeta`; deliberately not re-exported from the package root).
- The handler is registered explicitly — the same way you call `app.add_middleware(...)`; the package does not touch your app behind your back. `handle_base_error` is typed `(Request, Exception)` to match Starlette's handler contract, so the registration line stays clean under every type checker; registering it for a non-`BaseError` exception type fails fast with a `TypeError` at runtime.
