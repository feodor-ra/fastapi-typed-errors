"""``with_errors()``: teach a router's ``add_api_route`` to understand ``Raises``."""

import functools
import inspect
from collections.abc import Callable, Iterator, Sequence
from http import HTTPStatus
from types import UnionType
from typing import Annotated, Any, Final, TypeAliasType, Union, cast, get_args, get_origin, get_type_hints

from fastapi import APIRouter, Response
from fastapi.datastructures import DefaultPlaceholder
from fastapi.dependencies.models import Dependant
from fastapi.params import Depends
from fastapi.security.base import SecurityBase

from ..core.base import BaseError
from ..core.models import error_models
from .raises import Raises

_ALREADY_WRAPPED: Final[str] = "_fastapi_typed_errors_wrapped"


def with_errors[R: APIRouter](router: R, /, *, auto: bool = False) -> R:
    """Enable ``Raises`` handling on the router and return the same router.

    The router's ``add_api_route`` is replaced (on the instance) with a wrapper
    that reads ``Raises`` markers from the endpoint's return annotation and
    fills ``responses={}`` accordingly. Every registration path — the 8 HTTP
    verb decorators, ``api_route`` and imperative ``add_api_route`` calls, on
    the router or on the application — funnels into that single method, so
    nothing else needs patching. The object identity is preserved:
    ``include_router``, websockets and OpenAPI work exactly as without the
    patch. Idempotent: wrapping twice is a no-op.

    For an application, wrap its router: ``with_errors(app.router)``.

    Args:
        router: The router to enable ``Raises`` handling on.
        auto: When ``True``, also fill ``responses`` from errors discovered by
            statically walking each endpoint and its whole dependency tree — no
            ``Raises[...]`` needed; discovered errors are merged with any that
            are declared. Set it on the first ``with_errors`` call; because
            wrapping is idempotent, a later call does not change it.

    Returns:
        R: The same router instance, for chaining and assignment.
    """
    if not getattr(router.add_api_route, _ALREADY_WRAPPED, False):
        router.add_api_route = _wrap_add_api_route(router.add_api_route, router, auto=auto)  # ty: ignore[invalid-assignment]
    return router


def _wrap_add_api_route[**P, R](add_api_route: Callable[P, R], router: APIRouter, /, *, auto: bool) -> Callable[P, R]:
    """Build the ``add_api_route`` replacement enriching ``responses`` from ``Raises``.

    The wrapper only manipulates call arguments and delegates: without markers
    (and without ``auto``) the call passes through byte-for-byte, so FastAPI's
    ``DefaultPlaceholder`` sentinels and inference behavior stay intact.

    Args:
        add_api_route: The original bound ``APIRouter.add_api_route``.
        router: The wrapped router (its ``dependencies`` feed the ``auto`` walk).
        auto: Whether to also derive errors from the endpoint and dependencies.

    Returns:
        Callable[P, R]: The replacement, preserving the original signature.
    """

    @functools.wraps(add_api_route)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        path = args[0] if args else kwargs.get("path", "")
        endpoint = args[1] if len(args) > 1 else kwargs.get("endpoint")
        if not callable(endpoint):
            # Let the original signature produce the natural error.
            return add_api_route(*args, **kwargs)
        annotation = _return_annotation(_unwrap_endpoint(endpoint), path)
        errors = dict.fromkeys(error for marker in _find_raises(annotation) for error in marker.errors)
        if auto:
            route_dependencies = cast(Sequence[Depends] | None, kwargs.get("dependencies"))
            errors = dict.fromkeys([*errors, *_auto_raised(endpoint, path, route_dependencies, router)])
        if errors:
            # Mutating P.kwargs violates the ParamSpec guarantee formally, but the keys
            # belong to the wrapped signature — localize the lie in one cast alias.
            raw_kwargs = cast(dict[str, Any], kwargs)
            raw_kwargs["responses"] = {**_build_responses(tuple(errors)), **(raw_kwargs.get("responses") or {})}
            if (model := raw_kwargs.get("response_model")) is None or isinstance(model, DefaultPlaceholder):
                base = _annotated_base(annotation)
                if base is type(None) or (isinstance(base, type) and issubclass(base, Response)):
                    # Replicate FastAPI's own `-> Response` / `-> None` inference, which cannot
                    # see through the Annotated wrapper and would treat it as a model.
                    raw_kwargs["response_model"] = None
        return add_api_route(*args, **kwargs)

    setattr(wrapper, _ALREADY_WRAPPED, True)
    return wrapper


def _unwrap_endpoint[R](endpoint: Callable[..., R]) -> Callable[..., R]:
    """Peel wrappers off the endpoint to reach the callable carrying annotations.

    Handles ``functools.partial`` (possibly nested), ``functools.wraps`` chains
    and callable instances (annotations live on ``type(obj).__call__``).

    Args:
        endpoint: The endpoint as passed to ``add_api_route``.

    Returns:
        Callable[..., R]: The unwrapped callable to read type hints from.
    """
    fn: Callable[..., Any] = endpoint
    while isinstance(fn, functools.partial):
        fn = fn.func
    fn = inspect.unwrap(fn)
    if not inspect.isroutine(fn) and not isinstance(fn, type) and callable(fn):
        fn = inspect.unwrap(type(fn).__call__)
    return cast(Callable[..., R], fn)


def _return_annotation(fn: Callable[..., Any], path: object) -> object:
    """Resolve the endpoint's return annotation with ``Annotated`` extras preserved.

    Args:
        fn: The unwrapped endpoint callable.
        path: Route path, used in error messages only.

    Returns:
        object: The resolved return annotation; ``None`` when absent or when
            hints are unresolvable and no ``Raises`` is involved (stock
            FastAPI tolerates the ``TYPE_CHECKING`` pattern — so do we).

    Raises:
        TypeError: If hints cannot be resolved while the raw return annotation
            mentions ``Raises`` — an unresolvable forward reference or a bare
            ``-> Raises[...]`` used outside ``Annotated``.
    """
    try:
        hints = get_type_hints(fn, include_extras=True)
    except (NameError, TypeError) as exc:
        raw = getattr(fn, "__annotations__", {}).get("return")
        if raw is None or "Raises" not in str(raw):
            # No Raises involved: pass through and let FastAPI apply its own
            # tolerance (or raise its own error if it really needs the hints).
            return None
        qualname = getattr(fn, "__qualname__", repr(fn))
        hint = (
            "Raises must appear inside Annotated: -> Annotated[Model, Raises[...]]"
            if isinstance(raw, Raises)
            else "forward references must be resolvable at registration time when Raises is declared"
        )
        msg = f"cannot resolve type hints of endpoint {qualname!r} for route {path!r}: {exc} ({hint})"
        raise TypeError(msg) from exc
    return hints.get("return")


def _find_raises(annotation: object) -> tuple[Raises, ...]:
    """Extract ``Raises`` markers from a return annotation, recursively.

    Sees through PEP 695 ``type`` aliases, nested ``Annotated`` bases and
    union arms (``Annotated[Model, Raises[...]] | None``) — a declared marker
    must never be dropped silently.

    Args:
        annotation: The resolved return annotation (``None`` when absent).

    Returns:
        tuple[Raises, ...]: Markers in inner-to-outer metadata order; empty
            when the annotation is absent or carries none.

    Raises:
        TypeError: On a bare ``Raises`` instance used as the whole annotation,
            or an unparametrized ``Raises`` class inside ``Annotated``.
    """
    while isinstance(annotation, TypeAliasType):
        annotation = annotation.__value__
    if annotation is None:
        return ()
    if isinstance(annotation, Raises):
        msg = "Raises must appear inside Annotated: -> Annotated[Model, Raises[...]]"
        raise TypeError(msg)
    origin = get_origin(annotation)
    if origin is Annotated:
        base, *metadata = get_args(annotation)
        if any(meta is Raises for meta in metadata):
            msg = "Raises must be parametrized: Annotated[Model, Raises[Error, ...]]"
            raise TypeError(msg)
        found = tuple(meta for meta in metadata if isinstance(meta, Raises))
        return (*_find_raises(base), *found)
    if origin is Union or origin is UnionType:
        return tuple(support for arm in get_args(annotation) for support in _find_raises(arm))
    return ()


def _annotated_base(annotation: object) -> object:
    """Return the real base type under PEP 695 aliases and ``Annotated`` wrappers.

    Args:
        annotation: The resolved return annotation.

    Returns:
        object: The underlying type the route actually returns (used for the
            ``Response`` / ``None`` normalization check).
    """
    while True:
        while isinstance(annotation, TypeAliasType):
            annotation = annotation.__value__
        if get_origin(annotation) is not Annotated:
            return annotation
        annotation = get_args(annotation)[0]


def _build_responses(errors: tuple[type[BaseError[Any]], ...]) -> dict[int | str, dict[str, Any]]:
    """Build ``responses`` entries from error classes, grouped by HTTP status.

    Args:
        errors: Deduplicated error classes in declaration order.

    Returns:
        dict[int | str, dict[str, Any]]: Per-status entries with a ``model``
            (single or discriminated union via ``error_models``) and a
            ``description`` (joined class descriptions, or the status phrase).
    """
    by_status: dict[int, list[type[BaseError[Any]]]] = {}
    for error in errors:
        by_status.setdefault(int(error.http_status), []).append(error)
    responses: dict[int | str, dict[str, Any]] = {}
    for status, classes in by_status.items():
        descriptions = dict.fromkeys(cls.description for cls in classes if cls.description)
        responses[status] = {
            "model": error_models(*classes),
            "description": "; ".join(descriptions) or HTTPStatus(status).phrase,
        }
    return responses


def _auto_raised(
    endpoint: Callable[..., Any],
    path: object,
    route_dependencies: Sequence[Depends] | None,
    router: APIRouter,
) -> frozenset[type[BaseError[Any]]]:
    """Discover the errors an endpoint and its dependency tree can raise.

    Walks the endpoint's source with the analysis layer's ``collect_raised``
    and does the same for every dependency callable, rebuilding the ``Dependant``
    tree at registration time (the route does not exist yet). ``collect_raised``
    is imported lazily to break the ``decorator`` ↔ ``analysis`` import cycle;
    if FastAPI's dependency helpers move, the walk degrades to the endpoint only.

    Args:
        endpoint: The endpoint callable being registered.
        path: The route path (only used for FastAPI's path-param detection,
            irrelevant to which dependencies are found).
        route_dependencies: The route-level ``dependencies=[Depends(...)]``.
        router: The router (its router-level ``dependencies`` are folded in).

    Returns:
        frozenset[type[BaseError[Any]]]: Every ``BaseError`` subclass found.
    """
    from ..analysis.visitor import collect_raised  # ruff:ignore[import-outside-top-level] — breaks the import cycle

    raised = set(collect_raised(endpoint))
    try:
        from fastapi.dependencies.utils import (  # ruff:ignore[import-outside-top-level] — enables the fallback below
            get_dependant,
            get_parameterless_sub_dependant,
        )
    except ImportError:
        return frozenset(raised)
    path_str = cast("str", path)
    dependant = get_dependant(path=path_str, call=endpoint)
    for depends in reversed([*router.dependencies, *(route_dependencies or [])]):
        dependant.dependencies.insert(0, get_parameterless_sub_dependant(depends=depends, path=path_str))
    for call in _dependency_calls(dependant):
        raised |= collect_raised(call)
    return frozenset(raised)


def _dependency_calls(dependant: Dependant) -> Iterator[Callable[..., Any]]:
    """Yield every dependency callable in the tree, skipping security schemes.

    Shared with the analysis checker (which imports it from here).

    Args:
        dependant: The dependency tree root.

    Yields:
        Callable[..., Any]: Each sub-dependency's callable.
    """
    for sub in dependant.dependencies:
        if sub.call is not None and not _is_security_scheme(sub.call):
            yield sub.call
        yield from _dependency_calls(sub)


def _is_security_scheme(call: Callable[..., Any]) -> bool:
    """Report whether a dependency callable is a security scheme.

    Args:
        call: The dependency callable.

    Returns:
        bool: ``True`` for ``SecurityBase`` instances (they raise stock
            ``HTTPException``, never ``BaseError``).
    """
    unwrapped = call
    while isinstance(unwrapped, functools.partial):
        unwrapped = unwrapped.func
    return isinstance(inspect.unwrap(unwrapped), SecurityBase)
