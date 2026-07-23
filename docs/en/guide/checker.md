---
title: CI checker
---

# CI checker: check_raises

`Raises[...]` annotations are a declaration. `check_raises` statically verifies that the declaration **matches** what a route can actually raise — in the endpoint itself, its helpers and its whole dependency tree. This closes the gap that annotations leave open: a forgotten declaration, or a dead one you no longer raise.

## Library usage

It fits perfectly into a test:

```python
from fastapi_typed_errors import check_raises


def test_error_contracts() -> None:
    report = check_raises(app)  # a FastAPI app or an APIRouter
    assert report.ok, report.routes
```

`check_raises` returns a [`RaisesReport`](../reference/analysis.md) with an `.ok` property and a list of discrepancies `.routes`.

## Two discrepancy categories

Each `RouteDiscrepancy` holds two **independent** buckets:

| Category | What it means | Default |
|---|---|---|
| `undeclared` | raised in code but absent from `Raises` | **always a failure** |
| `overdeclared` | declared but its raise is not found | a failure (toggleable) |

```python
report = check_raises(app)
for route in report.routes:
    print(route.path, route.methods)
    print("  undeclared:", [e.__name__ for e in route.undeclared])
    print("  overdeclared:", [e.__name__ for e in route.overdeclared])
```

Since AST analysis is conservative (it may not see dynamic `raise`s), `overdeclared` sometimes gives a false positive. In that case turn that bucket off:

```python
report = check_raises(app, allow_overdeclared=True)  # ignore extra declarations
```

!!! tip "Keep overdeclared on if you can"

    It catches dead declarations that pile up in OpenAPI. Reach for `allow_overdeclared=True` only for code with dynamic `raise`s the walker can't see.

## CLI

The same check as a command — handy in a CI pipeline. It needs the `cli` extra:

```bash
pip install "fastapi-typed-errors[cli]"
```

You point it at an app path in `module:attribute` form:

```bash
fastapi-typed-errors check app.main:app
```

=== "Match (exit 0)"

    ```console
    $ fastapi-typed-errors check app.main:app
    All 12 route(s) match their Raises declarations.
    ```

=== "Discrepancies (exit 1)"

    ```console
    $ fastapi-typed-errors check app.main:app
    ┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┓
    ┃ Route           ┃ Undeclared     ┃ Overdeclared  ┃
    ┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━┩
    │ GET /items      │ ForbiddenError │ -             │
    └─────────────────┴────────────────┴───────────────┘
    1 of 12 route(s) have discrepancies.
    ```

Flags: `--allow-overdeclared`, `--max-depth N`.

Exit codes:

| Code | Meaning |
|---|---|
| `0` | all declarations match |
| `1` | discrepancies found (a table) |
| `2` | a usage/loading error (bad path, not an app, unresolvable `Raises`) |

## What exactly is compared

- **Declared** — the union of `Raises[...]` markers from the endpoint's return annotation. It is read straight from the annotations, so it works **regardless** of whether the router was wrapped with `with_errors`.
- **Raised** — `raise` statements from the endpoint's source **plus** every node of the `Depends` tree (security schemes are skipped).

The walker understands the `get_or_404(error=NotFoundError)` factory pattern (the error class arrives as a call argument), closures, cross-module helpers and `functools.partial`. It runs in one process and **never executes** your code. For the false negatives (local variables, `self.method()` chains, dynamics) see [Limitations](limitations.md#walker).

!!! example "GitHub Actions"

    ```yaml
    - run: uv run fastapi-typed-errors check app.main:app
    ```

    Or run it via a test — `assert check_raises(app).ok` — and you won't need the separate CLI dependency.

---

**Next:** [Customization](customization.md) — your own response model, codes, `ABC` compatibility.
