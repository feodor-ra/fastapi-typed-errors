# fastapi-typed-errors

Public PyPI package: typed HTTP errors for FastAPI — exact `Literal` error codes in OpenAPI, discriminated `oneOf` unions on the `code` field, single source of truth (the error class itself).

**Keep this file up to date**: when adding features or making changes, extend and correct the relevant sections.

## Status

Draft. Only the `core` layer is implemented. Linters/type checker are configured (see Tooling); tests are not set up yet. Licensed under MIT (`LICENSE` + PEP 639 metadata in `pyproject.toml`).

## Architecture — three independent layers

Each layer is usable without the next one:

1. **`core`** (done) — `BaseError`, the `BaseErrorMeta` metaclass, `ErrorResponse`, `error_models()`, `handle_base_error`.
2. **`decorator`** (planned) — `with_errors(router)` + `Support[...]` in the return annotation (Annotated syntax). A router wrapper with a single interception point in `add_api_route`; subclassing `APIRouter` was rejected.
3. **`analysis`** (planned) — AST walk over `raise` statements: a CI checker (declared vs actually raised) and `auto=True` (auto-populating `responses`). Study fastapi-docx before implementing.

## Layout

src-layout, package `src/fastapi_typed_errors/`:

- `core/base.py` — `_model_title`, `ErrorResponse`, `BaseErrorMeta`, `BaseError` (hard dependency order, see the ordering convention).
- `core/models.py` — `error_models()` with 8 `@overload`s (typeshed pattern) + catch-all.
- `core/handlers.py` — `handle_base_error`.
- `__init__.py` / `core/__init__.py` — public API re-exports.
- `py.typed` — the package is typed.

## Key core-layer decisions

- Python ≥ 3.12 (PEP 695 generics); dependencies: fastapi ≥ 0.115, pydantic ≥ 2.9 (`model_title_generator`).
- The user brings their own enum: a code is any `StrEnum` member **or** a bare `Literal["CODE"]` (the `T: str` bound covers both).
- The metaclass extracts the code from `__orig_bases__` (`get_origin`/`get_args`), filtering bases via `isinstance(get_origin(orig_base), mcs)`; it writes `error_code` and `model` into the namespace **before** `type.__new__` — otherwise the metaclass properties would intercept the assignment.
- Eager validation: parametrizing with anything but a `TypeVar` (intermediate generic base) or a single-string `Literal` raises `TypeError` at class definition time — a mistake like `BaseError[str]` must not surface as an opaque 500 at request time.
- `response_base: ClassVar` — a substitutable response model base; users subclass `ErrorResponse` generically (`class MyResp[T: str](ErrorResponse[T])`) and point their own error base class at it.
- `description: ClassVar[str | None]` — the default `detail` and the OpenAPI status description (consumed by the decorator layer).
- OpenAPI titles: `model_title_generator` (`_model_title`) renders `ErrorResponse[NOT_FOUND]` instead of pydantic's default that embeds the enum member `repr()` with angle brackets.
- `error_models()`: deduplicates repeats; one code shared by two distinct models → a clear `TypeError` (a discriminated union requires unique discriminator values).
- **No `install()`-style helpers** — the user wires everything explicitly, the FastAPI way (`app.add_exception_handler(BaseError, handle_base_error)`), same as `app.add_middleware(...)`. Starlette resolves handlers by walking `__mro__`, so the `BaseError` handler overrides the default `HTTPException` one without touching plain `HTTPException`.
- `handle_base_error` is typed `(Request, Exception)` to match Starlette's `ExceptionHandler` contract: parameters are contravariant, so a narrower `BaseError` parameter would force a suppression onto every user's registration line (verified with ty; dropping the generic parameter does not help). Misregistration is caught at runtime instead — a non-`BaseError` argument raises a `TypeError` naming the offending type.
- `BaseErrorMeta` is public so users can resolve metaclass conflicts (mixing `BaseError` with `ABC` etc.) via a combined metaclass, but it is deliberately NOT re-exported from any `__init__` — import from `fastapi_typed_errors.core.base`. Documented in README.
- Rule for the future decorator layer: an explicit user `responses={}` wins over `Support` errors with the same status.

## Conventions

- This file and all code artifacts (docstrings, comments) are in English; communication with the user is in Russian.
- Commits: Conventional Commits with English descriptions (`feat(core): ...`, `chore: ...`, `docs: ...`).
- Member ordering, both at module level and inside classes: public first, then protected (`_name`), then private. Deviate only when definition-time dependencies force it — e.g. in `core/base.py` `_model_title` must precede `ErrorResponse` (referenced in its class body), and `ErrorResponse` -> `BaseErrorMeta` -> `BaseError` is a hard dependency chain (annotations evaluate eagerly on Python < 3.14).
- Docstrings: **Google style** (Args/Returns/Raises/Attributes/Example).
- `Returns:` must state the return type: `type: Description` (e.g. `str | None: The declared code...`).
- Type checker: **ty**, max strictness (`[tool.ty.rules] all = "error"`). Suppressions use ty-style comments (`# ty: ignore[rule]`); ty does not recognize mypy rule codes inside `# type: ignore[...]`.
- Linter/formatter: **ruff** with `select = ["ALL"]` + `preview = true`, ignoring only the `TC` and `CPY` modules and `missing-trailing-comma` (COM812, formatter conflict); pydocstyle convention = google. Formatter: double quotes, `line-length = 120`. Import order: ruff isort defaults (stdlib `import` then `from` imports, third-party, local) — exactly the preferred style, no extra config needed.
- Ruff suppressions use the new `# ruff:ignore[rule-name]` syntax — the preview rule `noqa-comments` forbids legacy `# noqa` comments. Single-rule entries in `lint.ignore` must use rule *names*, not codes (preview rule `rule-codes-in-selectors`).
- Both tools are pinned exactly (`==`) in the `dev` dependency group; bump deliberately (`uv add --dev --bounds exact ty ruff`).
- Lint everything: `just lint` (ruff format --check, ruff check, ty check). Run `uv run ruff format` to apply formatting.
- Environment and build: uv (`uv sync`, `uv run python ...`), build backend `uv_build`.
- Run smoke checks against a live FastAPI app: `uv run --with httpx python <script>` (httpx is needed by `TestClient` and is not a package dependency).
