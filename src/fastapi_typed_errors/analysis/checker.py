"""CI checker: compare declared ``Raises`` against the errors found in code."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, Protocol, cast

import fastapi.routing
from fastapi import APIRouter, FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from ..core.base import BaseError
from ..decorator.wrapper import (
    _dependency_calls,
    _find_raises,
    _return_annotation,
    _unwrap_endpoint,
)
from .visitor import _collect, _ScanCache


class _RouteLike(Protocol):
    """The route attributes the checker reads, shared by ``APIRoute`` and ``RouteContext``."""

    path: str
    methods: set[str] | None
    endpoint: Callable[..., Any]
    dependant: Dependant


@dataclass(frozen=True, slots=True)
class RouteDiscrepancy:
    """One route whose declared errors disagree with the errors found in code.

    Attributes:
        path: The full (prefixed) route path.
        methods: The route's HTTP methods.
        undeclared: Errors raised in code but absent from ``Raises`` — always wrong.
        overdeclared: Errors declared via ``Raises`` but never found raised.
    """

    path: str
    methods: frozenset[str]
    undeclared: tuple[type[BaseError[Any]], ...]
    overdeclared: tuple[type[BaseError[Any]], ...]


@dataclass(frozen=True, slots=True)
class RaisesReport:
    """Result of checking a whole application or router.

    Attributes:
        routes: The discrepant routes, in registration order.
        checked: How many API routes were examined.
    """

    routes: tuple[RouteDiscrepancy, ...]
    checked: int

    @property
    def ok(self) -> bool:
        """Whether every checked route matched its declarations.

        Returns:
            bool: ``True`` when there are no discrepancies.
        """
        return not self.routes


def check_raises(
    target: FastAPI | APIRouter,
    *,
    allow_overdeclared: bool = False,
    max_depth: int = 10,
) -> RaisesReport:
    """Check that every route's ``Raises`` declarations match the errors it can raise.

    For each API route the declared set is read from the endpoint's return
    annotation and the raised set is collected from the endpoint plus every
    dependency (security schemes excluded). Discrepancies are reported in two
    directions: ``undeclared`` (raised but not declared) and ``overdeclared``
    (declared but not found raised).

    Args:
        target: The FastAPI application or router to check.
        allow_overdeclared: When ``True``, ignore declared-but-not-raised errors
            (useful for code with raises the static walker cannot see).
        max_depth: How many call levels below each body to expand.

    Returns:
        RaisesReport: The discrepant routes and the number of routes checked.
    """
    cache: _ScanCache = {}
    discrepancies: list[RouteDiscrepancy] = []
    checked = 0
    for route in _api_routes(target):
        checked += 1
        declared = _declared(route)
        raised = _raised(route, max_depth=max_depth, cache=cache)
        undeclared = _sorted(raised - declared)
        overdeclared = () if allow_overdeclared else _sorted(declared - raised)
        if undeclared or overdeclared:
            discrepancies.append(
                RouteDiscrepancy(
                    path=route.path,
                    methods=frozenset(route.methods or ()),
                    undeclared=undeclared,
                    overdeclared=overdeclared,
                ),
            )
    return RaisesReport(routes=tuple(discrepancies), checked=checked)


def _api_routes(target: FastAPI | APIRouter) -> Iterator[_RouteLike]:
    """Yield each unique API route of the target, expanding lazy includes.

    Uses ``iter_route_contexts`` when present (FastAPI ≥ 0.139, lazy includes);
    otherwise falls back to a flat ``routes`` walk (≤ 0.136, eager includes).

    Args:
        target: The application or router to enumerate.

    Yields:
        _RouteLike: A route context (or ``APIRoute``) exposing ``path``/
            ``methods``/``endpoint``/``dependant``.
    """
    iter_contexts = getattr(fastapi.routing, "iter_route_contexts", None)
    items = iter_contexts(target.routes) if iter_contexts is not None else target.routes
    seen: set[int] = set()
    for item in items:
        original = getattr(item, "original_route", item)
        if not isinstance(original, APIRoute) or id(original) in seen:
            continue
        seen.add(id(original))
        yield cast(_RouteLike, item)


def _declared(route: _RouteLike) -> frozenset[type[BaseError[Any]]]:
    """Read the errors declared via ``Raises[...]`` in the endpoint's return annotation.

    Args:
        route: The route (or route context) being checked.

    Returns:
        frozenset[type[BaseError[Any]]]: The declared error classes.
    """
    annotation = _return_annotation(_unwrap_endpoint(route.endpoint), route.path)
    markers = _find_raises(annotation)
    return frozenset(error for marker in markers for error in marker.errors)


def _raised(route: _RouteLike, *, max_depth: int, cache: _ScanCache) -> frozenset[type[BaseError[Any]]]:
    """Collect the errors raised by the endpoint and all of its dependencies.

    Args:
        route: The route (or route context) being checked.
        max_depth: How many call levels below each body to expand.
        cache: Parse cache shared across the whole run.

    Returns:
        frozenset[type[BaseError[Any]]]: The raised error classes.
    """
    raised: set[type[BaseError[Any]]] = set(_collect(route.endpoint, max_depth=max_depth, cache=cache))
    for call in _dependency_calls(route.dependant):
        raised |= _collect(call, max_depth=max_depth, cache=cache)
    return frozenset(raised)


def _sorted(errors: frozenset[type[BaseError[Any]]]) -> tuple[type[BaseError[Any]], ...]:
    """Order error classes by name for deterministic output.

    Args:
        errors: The error classes to order.

    Returns:
        tuple[type[BaseError[Any]], ...]: The classes sorted by ``__name__``.
    """
    return tuple(sorted(errors, key=lambda error: error.__name__))
