---
title: Limitations
---

# Limitations and internals

An honest list of what is out of scope and why — plus a little about the internals.

## FastAPI versions { #fastapi }

The dependency is `fastapi >=0.115,!=0.137.*,!=0.138.*`.

FastAPI **0.137** introduced the lazy routing model (an `_IncludedRouter` tree instead of copying routes), but the supported `iter_route_contexts` iterator only appeared in **0.139**. In the `0.137`–`0.138` gap nested `include_router`s cannot be walked correctly, so those versions are excluded at the dependency level. Two working regimes remain:

- `≤ 0.136` — the old eager `include_router` (a flat `routes` walk);
- `≥ 0.139` — lazy routing with `iter_route_contexts`.

The CI checker picks the right regime automatically (a call-time `getattr` plus a fallback to the flat walk).

## Walker limitations { #walker }

`auto=True` and `check_raises` share one AST walker. It is conservative and **never executes** your code — hence its scope.

**It understands:**

- `raise X(...)`, `raise X`, `raise X(...) from e`;
- `raise` inside `if`/`try-except`/`match`;
- helpers called by name (cross-module too), down to a given depth;
- the `get_or_404(error=X)` factory pattern (the error class as a call argument);
- errors captured in a closure;
- `partial` endpoints, `functools.wraps` chains, callable instances, class dependencies (via `__init__`);
- the whole `Depends` tree (security schemes are skipped).

**It does not see** (documented false negatives):

- local dataflow: `err = NotFoundError; raise err(...)`;
- method chains on objects: `self.service.raise_it()`;
- dynamic dispatch (a `raise` from a dict value, etc.);
- bare stream returns `-> Annotated[AsyncIterator[X], Raises[...]]`.

!!! tip "False negatives are safe for CI"

    Because of them, `overdeclared` stays a failure by default. If you have dynamic `raise`s the walker can't see — declare them explicitly with `Raises`, or use `check_raises(app, allow_overdeclared=True)`.

## Flat response bodies

Your own response model extends **flat** only (fields next to `code`/`detail`). Nested envelopes (`data: ErrorResponse[T]`) are not supported — pydantic can't discriminate a union on a nested field. See [Customization](customization.md) for details.

## Semi-internal FastAPI functions

`auto=True` rebuilds the dependency tree at registration via `fastapi.dependencies.utils.get_dependant` / `get_parameterless_sub_dependant`. These are public (no leading underscore) functions that FastAPI itself imports in `routing.py`, but they are not documented as a stable API. The import is wrapped in `try/except ImportError` — if the internal API changes, the walk **degrades gracefully** to "endpoint only" (dependency errors won't reach `auto`, but the package keeps working).

## Scope of Raises on a route

- A `Raises` marker on a router **not** passed through `with_errors` is inert: nothing is injected and nothing fails. The CI checker reads annotations directly, so it still catches such drift.
- Wrap the router **before** registering routes — otherwise they are not retrofitted.

---

**Next:** the [API Reference](../reference/core.md) — signatures from the docstrings.
