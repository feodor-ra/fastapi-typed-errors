---
title: Overview
---

# fastapi-typed-errors

**Typed HTTP errors for FastAPI.** Exact `Literal` codes in OpenAPI, discriminated `oneOf` unions on the `code` field, and a single source of truth — the error class itself.

---

## Why

In plain FastAPI an error is `HTTPException(404, "...")`. The error code lives in a string, OpenAPI has neither a code type nor a response-body model, and the list of errors a route can raise has to be duplicated by hand into `responses={}`. Clients can't switch on the code, and the docs drift away from the code fast.

`fastapi-typed-errors` makes an error a **class**: the HTTP status, machine-readable code and response model are declared once and derived automatically.

=== "Before"

    ```python
    @app.get("/items/{item_id}")
    def get_item(item_id: int):
        if item_id == 0:
            raise HTTPException(404, "No item")  # (1)!
        return {"item_id": item_id}
    ```

    1. The error code is just a string in `detail`; in OpenAPI the 404 has neither an exact code nor a body schema.

=== "After"

    ```python
    class NotFoundError(BaseError[Literal[ErrorCode.NOT_FOUND]]):
        http_status = HTTPStatus.NOT_FOUND


    @router.get("/items/{item_id}")
    def get_item(item_id: int) -> Annotated[Item, Raises[NotFoundError]]:  # (1)!
        if item_id == 0:
            raise NotFoundError("No item")
        return Item(item_id=item_id)
    ```

    1. The declared error lands in `responses` automatically: a 404 with the exact `Literal["NOT_FOUND"]` and a `{code, detail}` body.

=== "…or with auto magic"

    ```python
    router = with_errors(APIRouter(), auto=True)  # (1)!


    @router.get("/items/{item_id}")
    def get_item(item_id: int) -> Item:  # (2)!
        if item_id == 0:
            raise NotFoundError("No item")
        return Item(item_id=item_id)
    ```

    1. Turn on auto-fill once, on the router.
    2. Not a single marker — `responses` build themselves: the walker finds `raise NotFoundError` (and errors raised by dependencies) statically. See [auto=True](guide/decorator.md#auto).

The error response body is always predictable:

```json
{ "code": "NOT_FOUND", "detail": "No item" }
```

And in OpenAPI the route gets one entry per status — with an exact code and a body model. Here is how it renders in Swagger UI:

![Swagger UI Responses panel: 200 → Item, 403 → ErrorResponse[FORBIDDEN], 404 → oneOf of ErrorResponse[NOT_FOUND] / ErrorResponse[GONE] discriminated by code](assets/swagger-responses.svg){ .fte-shot }

## Features

<div class="grid cards" markdown>

-   :material-shield-check: **Single source of truth**

    ---

    Status, code and response model are declared once in the error class. The metaclass derives the rest.

    [:octicons-arrow-right-24: Core](guide/core.md)

-   :material-code-braces: **Exact types in OpenAPI**

    ---

    Every status gets an exact `Literal` code; several errors on one status become a discriminated `oneOf` union on `code`.

    [:octicons-arrow-right-24: error_models](guide/core.md#error_models)

-   :material-tag-arrow-up: **Declared right in the annotation**

    ---

    `-> Annotated[Item, Raises[NotFoundError, ForbiddenError]]` — and `responses` fill themselves.

    [:octicons-arrow-right-24: Decorator](guide/decorator.md)

-   :material-radar: **CI contract checking**

    ---

    `check_raises` compares what's declared against what's actually raised — in the endpoint and its dependencies.

    [:octicons-arrow-right-24: CI checker](guide/checker.md)

-   :material-auto-fix: **Auto-fill**

    ---

    `with_errors(router, auto=True)` finds errors statically and fills `responses` without a single marker.

    [:octicons-arrow-right-24: auto=True](guide/decorator.md#auto)

-   :material-puzzle: **Extensible**

    ---

    Your own envelope response model, your own codes (`StrEnum` or a bare `Literal`), compatibility with `ABC`.

    [:octicons-arrow-right-24: Customization](guide/customization.md)

</div>

## Install

=== "uv"

    ```bash
    uv add fastapi-typed-errors
    # with the CLI for the CI check:
    uv add "fastapi-typed-errors[cli]"
    ```

=== "pip"

    ```bash
    pip install fastapi-typed-errors
    pip install "fastapi-typed-errors[cli]"
    ```

!!! info "Requirements"

    - Python **3.12+** (PEP 695 generics)
    - FastAPI **≥ 0.115** (the `0.137`–`0.138` versions are excluded — see [Limitations](guide/limitations.md#fastapi))
    - Pydantic **≥ 2.9**

## Next

<div class="grid cards" markdown>

-   :material-rocket-launch: **[Quickstart](quickstart.md)** — a working app in a minute.
-   :material-book-open-variant: **[Guide](guide/core.md)** — concepts, decorator, checker, extension.
-   :material-api: **[API Reference](reference/core.md)** — signatures from the docstrings.

</div>
