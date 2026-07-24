# fastapi-typed-errors

**English** · [Русский](README.ru.md)

![Python](https://img.shields.io/badge/python-3.12%2B-blue) ![License](https://img.shields.io/badge/license-MIT-green) [![Coverage Status](https://coveralls.io/repos/github/feodor-ra/fastapi-typed-errors/badge.svg?branch=main)](https://coveralls.io/github/feodor-ra/fastapi-typed-errors?branch=main) [![Docs](https://img.shields.io/badge/docs-online-blueviolet)](https://feodor-ra.github.io/fastapi-typed-errors/)

**Typed HTTP errors for FastAPI** — exact `Literal` codes in OpenAPI, discriminated `oneOf` unions on the `code` field, and a single source of truth: the error class itself.

In plain FastAPI, `raise HTTPException(404, "...")` buries the error code in a string — clients can't switch on it, OpenAPI has no code type or body schema, and you hand-maintain `responses={}` on every route. This package makes an error a **class**: its HTTP status, machine-readable code and response model are declared once and derived automatically, so your error contract is typed, self-documenting, and verifiable in CI.

```python
class NotFoundError(BaseError[Literal[ErrorCode.NOT_FOUND]]):
    http_status = HTTPStatus.NOT_FOUND


@router.get("/items/{item_id}")
def get_item(item_id: int) -> Annotated[Item, Raises[NotFoundError]]:
    if item_id == 0:
        raise NotFoundError("No item")
    return Item(item_id=item_id)
```

The response body is always `{"code": "NOT_FOUND", "detail": "No item"}`, and OpenAPI gets a `404` with the **exact** `Literal["NOT_FOUND"]` code and body model — no manual `responses`.

## Install

```bash
pip install fastapi-typed-errors          # core + decorator
pip install "fastapi-typed-errors[cli]"   # + the CI-checker CLI
```

Requires Python **3.12+**, FastAPI **≥ 0.115**, Pydantic **≥ 2.9**.

## How to use it

**1. Define errors and register the one handler.**

```python
from fastapi import FastAPI
from fastapi_typed_errors import BaseError, handle_base_error

app = FastAPI()
app.add_exception_handler(BaseError, handle_base_error)
```

**2. Declare errors — pick your level of magic:**

```python
# a) by hand (core only) — write responses yourself
@app.get("/x", responses={404: {"model": error_models(NotFoundError)}})
def a() -> Item: ...


# b) declared — the marker fills responses for you
router = with_errors(APIRouter())


@router.get("/y")
def b() -> Annotated[Item, Raises[NotFoundError, ForbiddenError]]: ...


# c) automatic — no markers at all; errors are found statically
router = with_errors(APIRouter(), auto=True)


@router.get("/z")
def c(user: Annotated[User, Depends(current_user)]) -> Item:
    raise NotFoundError("...")  # auto -> 404, plus whatever current_user raises
```

**3. Verify the contract in CI.** `check_raises` compares what each route *declares* against what it can actually *raise* — in the endpoint and its whole dependency tree:

```python
def test_error_contracts() -> None:
    assert check_raises(app).ok
```

Or as a command: `fastapi-typed-errors check app.main:app` (exit `0`/`1`/`2`).

## Why it's cool

- **Exact types in OpenAPI** — a precise `Literal` code per status; several errors on one status become a discriminated `oneOf` union, so Swagger UI shows a variant picker by code.
- **Single source of truth** — status, code and model declared once; the metaclass derives the rest.
- **Zero-boilerplate `responses`** — via the `Raises` marker or fully automatic `auto=True`.
- **Static contract checking** — `check_raises` catches a raise you forgot to declare (or a dead declaration) before it ships.
- **Non-invasive** — `with_errors` patches the router in place and preserves object identity, so `include_router`, websockets and app-level decorators keep working natively.
- **Rigorous** — fully typed (`py.typed`), 100% branch-covered, checked with `ruff` + `ty` at max strictness.

## Documentation

📖 **[Full documentation](https://feodor-ra.github.io/fastapi-typed-errors/)** — guide, customization (custom envelopes, `ABC`, bare-string codes), limitations, and an auto-generated API reference. Available in English and Russian.

## License

[MIT](LICENSE).
