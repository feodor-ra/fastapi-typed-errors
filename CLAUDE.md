# fastapi-typed-errors

Public PyPI package: typed HTTP errors for FastAPI — exact `Literal` error codes in OpenAPI, discriminated `oneOf` unions on the `code` field, single source of truth (the error class itself).

**Keep this file up to date**: when adding features or making changes, extend and correct the relevant sections.

## Status

Draft. The `core` and `decorator` layers are implemented. Linters/type checker and pytest are configured (see Conventions). Licensed under MIT (`LICENSE` + PEP 639 metadata in `pyproject.toml`).

## Architecture — three independent layers

Each layer is usable without the next one:

1. **`core`** (done) — `BaseError`, the `BaseErrorMeta` metaclass, `ErrorResponse`, `error_models()`, `handle_base_error`.
2. **`decorator`** (done) — `with_errors(router)` + `Raises[...]` in the return annotation (Annotated syntax). An instance patch of `add_api_route` as the single interception point; subclassing `APIRouter` AND a wrapper object were both rejected (see decorator-layer decisions).
3. **`analysis`** (planned) — AST walk over `raise` statements: a CI checker (declared vs actually raised) and `auto=True` (auto-populating `responses`). Study fastapi-docx before implementing.

## Layout

src-layout, package `src/fastapi_typed_errors/`:

- `core/base.py` — `_model_title`, `ErrorResponse`, `BaseErrorMeta`, `BaseError` (hard dependency order, see the ordering convention).
- `core/models.py` — `error_models()` with 8 `@overload`s (typeshed pattern) + catch-all.
- `core/handlers.py` — `handle_base_error`.
- `decorator/raises.py` — the `Raises` marker (validated at construction).
- `decorator/wrapper.py` — `with_errors()` + the `add_api_route` patch and private helpers.
- `__init__.py` / subpackage `__init__.py` — public API re-exports.
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
- Rule for the future decorator layer: an explicit user `responses={}` wins over `Raises` errors with the same status.

## Key decorator-layer decisions

- **Instance patch, not a wrapper object** (user decision 2026-07-22, supersedes the concept doc): `with_errors[R: APIRouter](router: R, /) -> R` replaces `router.add_api_route` with a `functools.wraps` decorator on the *instance* and returns the *same* router. Reason: FastAPI 0.139's lazy `include_router` keeps the included object and `APIRouter.matches` does an **identity check** (`included_router.original_router is self`) — any duck-typed wrapper passes OpenAPI generation but silently 404s at runtime. Identity preservation makes `include_router`, websockets, app-level decorators and imperative registration work natively on every FastAPI version.
- Single funnel: all 8 verb decorators + `api_route` + all `app.*` methods delegate into `router.add_api_route` (verified in 0.139 sources), so one patch covers everything. For an application: `with_errors(app.router)`.
- The patch is idempotent (flag attribute `_fastapi_typed_errors_wrapped` on the replacement).
- FastAPI's decorators pass `response_model` explicitly as a `DefaultPlaceholder` sentinel — "user set response_model" means the kwarg is present AND not a `DefaultPlaceholder`. Never inject `response_model=None` otherwise: it would disable return-annotation inference.
- `Raises` is an inert `Annotated` metadata instance (`__class_getitem__` returns an instance; no `__get_pydantic_core_schema__`); pydantic ignores it, the 200 schema stays clean. Validation (BaseError subclass, declared code + status, non-empty) happens eagerly at `Raises[...]` evaluation, i.e. import time.
- Normalization: `-> Annotated[Response-subclass | None, Raises[...]]` → `response_model=None` (FastAPI's `lenient_issubclass` cannot see through `Annotated`; without this the route dies with `FastAPIError` / grows a spurious `null` schema). Bare stream returns (`AsyncIterator` + Raises) are unsupported — documented limitation.
- Merge semantics: derived entries lose to explicit per-route `responses` wholesale per status; router-level `responses` are merged by FastAPI itself and lose to per-route ones.
- Endpoint unwrapping for annotation reading only: `functools.partial` chain → `inspect.unwrap` → callable-instance `type(obj).__call__`; the original endpoint object is always what gets registered.
- `_find_raises` is recursive: unwraps PEP 695 `TypeAliasType`, descends into `Annotated` bases and union arms — a declared marker must never be dropped silently (adversarial review caught all three as silent-drop bugs). `_annotated_base` applies the same unwrapping for the Response/None normalization.
- Unresolvable type hints (NameError/TypeError from `get_type_hints`): if the raw return annotation does not mention `Raises` → silent passthrough (stock FastAPI tolerates the `TYPE_CHECKING` pattern and never resolves return hints under an explicit `response_model`); if it does → fail fast with a clear `TypeError`. Never resolve stricter than stock for marker-free endpoints.
- Follow-up idea (not implemented): PEP 692 `Unpack[TypedDict]` typing for registration kwargs.

## Conventions

- This file and all code artifacts (docstrings, comments) are in English; communication with the user is in Russian.
- Commits: Conventional Commits with English descriptions (`feat(core): ...`, `chore: ...`, `docs: ...`).
- Member ordering, both at module level and inside classes: public first, then protected (`_name`), then private. Deviate only when definition-time dependencies force it — e.g. in `core/base.py` `_model_title` must precede `ErrorResponse` (referenced in its class body), and `ErrorResponse` -> `BaseErrorMeta` -> `BaseError` is a hard dependency chain (annotations evaluate eagerly on Python < 3.14).
- Docstrings: **Google style** (Args/Returns/Raises/Attributes/Example).
- Prefer PEP 695 generics (`[**P, R]`, `[R]`) over `Callable[..., Any]` in decorator/pass-through helpers; when P.kwargs must be mutated, localize the lie in a single `cast(dict[str, Any], kwargs)` alias instead of suppressions. Module-level constants are annotated `Final`.
- Relative imports inside the package are welcome (`from ..core.base import ...`) — TID252 (`relative-imports`) is in the ignore list.
- `Returns:` must state the return type: `type: Description` (e.g. `str | None: The declared code...`).
- Type checker: **ty**, max strictness (`[tool.ty.rules] all = "error"`). Suppressions use ty-style comments (`# ty: ignore[rule]`); ty does not recognize mypy rule codes inside `# type: ignore[...]`.
- Linter/formatter: **ruff** with `select = ["ALL"]` + `preview = true`, ignoring only the `TC` and `CPY` modules and `missing-trailing-comma` (COM812, formatter conflict); pydocstyle convention = google. Formatter: double quotes, `line-length = 120`. Import order: ruff isort defaults (stdlib `import` then `from` imports, third-party, local) — exactly the preferred style, no extra config needed.
- Ruff suppressions use the new `# ruff:ignore[rule-name]` syntax — the preview rule `noqa-comments` forbids legacy `# noqa` comments. Single-rule entries in `lint.ignore` must use rule *names*, not codes (preview rule `rule-codes-in-selectors`).
- ruff and ty are pinned exactly (`==`) in the `dev` dependency group; bump deliberately (`uv add --dev --bounds exact ty ruff`). Test tooling (`pytest`, `pytest-cov`, `httpx2` for `TestClient`) uses compatible-release pins (`~=`).
- Tests live in `tests/`, mirroring the package structure (`tests/core/test_base.py` ↔ `src/.../core/base.py`); the directory is not a package (INP001 ignored, S101 too: pytest asserts; EM101 ignored — literal details in `raise` are the package's own user-facing pattern). Run: `just test` (`uv run pytest --cov`); pytest config and coverage live in `pyproject.toml`. **Coverage bar: `fail_under = 100`** (branch coverage on). Test-writing rules are introduced incrementally by the user — check recent test files for the current style before writing new ones.
- Async tests are plain `async def` — the anyio pytest plugin picks them up via `tests/conftest.py` (an `anyio_backend` fixture + a `pytest_collection_modifyitems` hook auto-marking coroutine tests; anyio has no pytest-asyncio-style "auto" mode).
- Registration-only stub endpoints in tests end with `raise NotImplementedError` (ty `all = "error"` rejects `...` bodies with non-`None` return annotations outside stubs/protocols).
- Test structure: **AAA** (Arrange / Act / Assert), the blocks separated by blank lines; single-expression tests may collapse to one line (e.g. `assert error_models(X) is X.model`). Every test opens with a short one-line docstring describing the case; test functions are annotated `-> None`.
- Prefer pytest **fixtures** for reusable arrange values (request objects, configured apps, built artifacts) — typed, with a docstring and a `Returns:` section. Module level is only for error classes/enums that must exist at import time (they are used in type positions). Don't name a fixture `request` — it clashes with pytest's built-in.
- Lint everything: `just lint` (ruff format --check, ruff check, ty check). Run `uv run ruff format` to apply formatting.
- Environment and build: uv (`uv sync`, `uv run python ...`), build backend `uv_build`.
- Run smoke checks against a live FastAPI app: `uv run python <script>` (`httpx2` for `TestClient` is in the dev group, so no `--with` is needed anymore).
