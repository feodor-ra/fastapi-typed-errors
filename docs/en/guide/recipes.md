---
title: Recipes
---

# Recipes

Ready-made patterns for common tasks.

## A shared tuple of auth errors

Token/auth errors are usually the same across many routes. Factor them into a tuple and unpack them with the marker:

```python
from typing import Final

TOKEN_ERRORS: Final = (RequiredTokenError, InvalidTokenError, WrongTokenTypeError)


@router.get("/me")
def me(user: Annotated[User, Depends(current_user)]) -> Annotated[User, Raises[*TOKEN_ERRORS]]: ...
```

All three codes on `401` automatically become a discriminated `oneOf` union.

## Dependency errors without manual declaration

If the auth errors live in dependencies (`Depends`), turn on [`auto=True`](decorator.md#auto) — and don't declare them at all:

```python
router = with_errors(APIRouter(), auto=True)


def current_user(token: Annotated[str, Depends(oauth)]) -> User:
    if invalid(token):
        raise InvalidTokenError("bad token")  # found automatically
    ...


@router.get("/me")
def me(user: Annotated[User, Depends(current_user)]) -> User:
    return user  # the 401 from the dependency lands in responses by itself
```

## The `get_or_404` factory

A common pattern is a shared helper that raises the class passed to it:

```python
def get_or_404[M](value: M | None, *, error: type[BaseError[Any]]) -> M:
    if value is None:
        raise error("not found")
    return value


@router.get("/items/{item_id}")
def get_item(item_id: int) -> Annotated[Item, Raises[NotFoundError]]:
    item = get_or_404(repo.find(item_id), error=NotFoundError)
    return item
```

The walker (`auto` and `check_raises`) understands this factory: the error class passed as a **call argument** counts as potentially raised.

## Testing error contracts

One line in a test guarantees the declarations haven't drifted from the code:

```python
from fastapi_typed_errors import check_raises


def test_error_contracts() -> None:
    assert check_raises(app).ok
```

The full response body is easy to check too, via `TestClient`:

```python
def test_not_found() -> None:
    response = TestClient(app).get("/items/0")
    assert response.status_code == 404
    assert response.json() == {"code": "NOT_FOUND", "detail": "gone"}
```

## The whole application

Wrap the application's router so that `app.get(...)` decorators understand `Raises` too:

```python
app = FastAPI()
app.add_exception_handler(BaseError, handle_base_error)
with_errors(app.router, auto=True)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

---

**Next:** [Limitations](limitations.md) — what is out of scope and why.
