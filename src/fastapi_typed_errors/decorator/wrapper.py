"""``with_errors()``: teach a router's ``add_api_route`` to understand ``Raises``."""

import functools
import inspect
from collections.abc import Callable
from http import HTTPStatus
from types import UnionType
from typing import Annotated, Any, Final, TypeAliasType, Union, cast, get_args, get_origin, get_type_hints

from fastapi import APIRouter, Response
from fastapi.datastructures import DefaultPlaceholder

from ..core.base import BaseError
from ..core.models import error_models
from .raises import Raises

_ALREADY_WRAPPED: Final[str] = "_fastapi_typed_errors_wrapped"


def with_errors[R: APIRouter](router: R, /) -> R:
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
    Future options will be keyword-only (e.g. ``with_errors(router, auto=...)``).

    Args:
        router: The router to enable ``Raises`` handling on.

    Returns:
        R: The same router instance, for chaining and assignment.
    """
    if not getattr(router.add_api_route, _ALREADY_WRAPPED, False):
        router.add_api_route = _wrap_add_api_route(router.add_api_route)  # ty: ignore[invalid-assignment]
    return router


def _wrap_add_api_route[**P, R](add_api_route: Callable[P, R], /) -> Callable[P, R]:
    """Build the ``add_api_route`` replacement enriching ``responses`` from ``Raises``.

    The wrapper only manipulates call arguments and delegates: without markers
    the call passes through byte-for-byte, so FastAPI's ``DefaultPlaceholder``
    sentinels and inference behavior stay intact.

    Args:
        add_api_route: The original bound ``APIRouter.add_api_route``.

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
        markers = _find_raises(annotation)
        if markers:
            # Mutating P.kwargs violates the ParamSpec guarantee formally, but the keys
            # belong to the wrapped signature — localize the lie in one cast alias.
            raw_kwargs = cast(dict[str, Any], kwargs)
            errors = tuple(dict.fromkeys(error for marker in markers for error in marker.errors))
            raw_kwargs["responses"] = {**_build_responses(errors), **(raw_kwargs.get("responses") or {})}
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
