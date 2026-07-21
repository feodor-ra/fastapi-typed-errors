"""Tests for the AST walker ``collect_raised``."""

from collections.abc import Callable
from typing import Any

import walker_helpers
from walker_helpers import (
    AppError,
    ConflictError,
    ForbiddenError,
    GoneError,
    NotFoundError,
    make_empty_cell,
)

from fastapi_typed_errors import BaseError
from fastapi_typed_errors.analysis.visitor import _collect, _ScanCache, collect_raised

raising_noop = lambda: None  # ruff:ignore[lambda-assignment] — parses to no function def when scanned


def raise_direct() -> None:
    """Raise an error directly (call form).

    Raises:
        NotFoundError: Always.
    """
    raise NotFoundError("x")


def raise_bare_name() -> None:
    """Raise an error class without calling it (name form).

    Raises:
        GoneError: Always.
    """
    raise GoneError


def reraise_bare() -> None:
    """Re-raise the active exception (bare raise carries no type).

    Raises:
        NotFoundError: Always.
    """
    try:
        raise NotFoundError("x")  # ruff:ignore[raise-within-try]
    except NotFoundError:  # ruff:ignore[useless-try-except]
        raise


def raise_in_branches(x: int) -> None:
    """Raise from within if / except / match constructs.

    Args:
        x: Selector.

    Raises:
        NotFoundError: From an if branch.
        ForbiddenError: From an except branch.
        ConflictError: From a match branch.
    """
    if x == 0:
        raise NotFoundError("if")
    try:
        _ = 1 / x
    except ZeroDivisionError:
        raise ForbiddenError("except") from None
    match x:
        case 1:
            raise ConflictError("match")
        case _:
            return


def helper_raises() -> None:
    """Raise from a helper one level down.

    Raises:
        GoneError: Always.
    """
    raise GoneError("x")


def calls_helper() -> None:
    """Call a module-global helper that raises."""
    helper_raises()


def get_or_404(value: object, error: type[BaseError[Any]]) -> object:
    """Raise the given error class when the value is missing (factory pattern).

    Args:
        value: The value to guard.
        error: The error class to raise.

    Returns:
        object: The value when present (raises the given class otherwise).
    """
    if value is None:
        raise error("missing")
    return value


def uses_factory_keyword() -> None:
    """Pass the error class to a factory as a keyword argument."""
    get_or_404(None, error=NotFoundError)


def uses_factory_positional() -> None:
    """Pass the error class to a factory positionally."""
    get_or_404(None, ConflictError)


def make_closure(error: type[BaseError[Any]]) -> Callable[[], None]:
    """Return a closure that raises the captured error class.

    Args:
        error: The error class to raise.

    Returns:
        Callable[[], None]: The closure over ``error``.
    """

    def inner() -> None:
        raise error("x")

    return inner


def self_recur() -> None:
    """Call itself before raising (the visited-set must terminate).

    Raises:
        NotFoundError: Always.
    """
    self_recur()
    raise NotFoundError("x")


def mutual_a() -> None:
    """Call ``mutual_b`` before raising.

    Raises:
        NotFoundError: Always.
    """
    mutual_b()
    raise NotFoundError("x")


def mutual_b() -> None:
    """Call ``mutual_a`` before raising.

    Raises:
        ForbiddenError: Always.
    """
    mutual_a()
    raise ForbiddenError("x")


def level0() -> None:
    """Call level1 (call depth 0)."""
    level1()


def level1() -> None:
    """Call level2 (call depth 1)."""
    level2()


def level2() -> None:
    """Raise at call depth 2.

    Raises:
        GoneError: Always.
    """
    raise GoneError("x")


def uses_builtin() -> None:
    """Call a builtin (resolves to nothing) before raising.

    Raises:
        NotFoundError: Always.
    """
    len([])
    raise NotFoundError("x")


def uses_isinstance(value: object) -> None:
    """Guard with isinstance, whose class argument must not count as raised.

    Args:
        value: Probed value.

    Raises:
        ForbiddenError: When value is a NotFoundError instance.
    """
    if isinstance(value, NotFoundError):
        raise ForbiddenError("x")


def raises_codeless() -> None:
    """Raise a codeless intermediate base, which the probe must exclude.

    Raises:
        AppError: Statically only; never executed.
    """
    raise AppError("x")


def uses_lambda() -> None:
    """Call a module-level lambda before raising.

    Raises:
        NotFoundError: Always.
    """
    raising_noop()
    raise NotFoundError("x")


def chained_call() -> None:
    """Call a method on a call/literal result (attribute head is not a name).

    Raises:
        NotFoundError: Always.
    """
    "".join([]).strip()
    raise NotFoundError("x")


def uses_cross_module() -> None:
    """Call a helper in another module (cross-module attribute resolution)."""
    walker_helpers.cross_raiser()


class CallEndpoint:
    """Callable-instance endpoint referencing ``self`` and raising."""

    def __call__(self) -> None:
        """Call a self-attribute and raise.

        Raises:
            ConflictError: Always.
        """
        self.helper()
        raise ConflictError("x")

    def helper(self) -> None:
        """Serve as the (unresolvable) target of the self-attribute call."""


class InitRaiser:
    """Class dependency whose constructor raises."""

    def __init__(self) -> None:
        """Raise on construction.

        Raises:
            ForbiddenError: Always.
        """
        raise ForbiddenError("x")


async def async_raiser() -> None:  # ruff:ignore[unused-async]
    """Async endpoint whose body is walked like a sync one.

    Raises:
        NotFoundError: Always.
    """
    raise NotFoundError("x")


class NoInit:
    """Class without a constructor (scanned via ``object.__init__``)."""


def test_direct_call_raise() -> None:
    """A ``raise X(...)`` in the body is collected."""
    assert collect_raised(raise_direct) == frozenset({NotFoundError})


def test_bare_name_raise() -> None:
    """A ``raise X`` without a call is collected."""
    assert collect_raised(raise_bare_name) == frozenset({GoneError})


def test_bare_reraise_is_skipped() -> None:
    """A bare ``raise`` contributes no type, only the explicit one."""
    assert collect_raised(reraise_bare) == frozenset({NotFoundError})


def test_raises_in_branches() -> None:
    """Raises nested in if / except / match are all collected."""
    assert collect_raised(raise_in_branches) == frozenset({NotFoundError, ForbiddenError, ConflictError})


def test_module_helper_one_level_down() -> None:
    """A raise in a called module-global helper is collected."""
    assert collect_raised(calls_helper) == frozenset({GoneError})


def test_factory_keyword_argument() -> None:
    """An error class passed to a factory by keyword is collected."""
    assert collect_raised(uses_factory_keyword) == frozenset({NotFoundError})


def test_factory_positional_argument() -> None:
    """An error class passed to a factory positionally is collected."""
    assert collect_raised(uses_factory_positional) == frozenset({ConflictError})


def test_closure_captured_error() -> None:
    """An error class captured in a closure is resolved via ``__closure__``."""
    assert collect_raised(make_closure(NotFoundError)) == frozenset({NotFoundError})


def test_self_recursion_terminates() -> None:
    """Self-recursion is cut by the visited-set and still collects the raise."""
    assert collect_raised(self_recur) == frozenset({NotFoundError})


def test_mutual_recursion_terminates() -> None:
    """Mutual recursion terminates and collects both raises."""
    assert collect_raised(mutual_a) == frozenset({NotFoundError, ForbiddenError})


def test_depth_cap_reaches_deep_raise() -> None:
    """A raise two calls deep is found when the depth budget allows it."""
    assert collect_raised(level0, max_depth=2) == frozenset({GoneError})


def test_depth_cap_stops_early() -> None:
    """A raise beyond the depth budget is not found."""
    assert collect_raised(level0, max_depth=1) == frozenset()


def test_builtin_callee_skipped() -> None:
    """A builtin callee resolves to nothing and is skipped."""
    assert collect_raised(uses_builtin) == frozenset({NotFoundError})


def test_isinstance_argument_not_raised() -> None:
    """A class used as an isinstance argument is not treated as raised."""
    assert collect_raised(uses_isinstance) == frozenset({ForbiddenError})


def test_codeless_base_excluded() -> None:
    """A codeless intermediate base is excluded by the concreteness probe."""
    assert collect_raised(raises_codeless) == frozenset()


def test_lambda_body_yields_nothing() -> None:
    """A module-level lambda callee parses to no function def and is empty."""
    assert collect_raised(uses_lambda) == frozenset({NotFoundError})


def test_chained_call_head_ignored() -> None:
    """A method call on a call/literal result is not a resolvable reference."""
    assert collect_raised(chained_call) == frozenset({NotFoundError})


def test_cross_module_attribute_call() -> None:
    """A helper in another module is resolved through the attribute chain."""
    assert collect_raised(uses_cross_module) == frozenset({ForbiddenError})


def test_callable_instance_endpoint() -> None:
    """A callable instance is analyzed via ``type(obj).__call__``."""
    assert collect_raised(CallEndpoint()) == frozenset({ConflictError})


def test_class_dependency_constructor() -> None:
    """A class is analyzed via its ``__init__``."""
    assert collect_raised(InitRaiser) == frozenset({ForbiddenError})


def test_class_without_constructor() -> None:
    """A class with no constructor (``object.__init__``) yields nothing."""
    assert collect_raised(NoInit) == frozenset()


def test_async_function_body() -> None:
    """An async function body is walked the same as a sync one."""
    assert collect_raised(async_raiser) == frozenset({NotFoundError})


def test_empty_closure_cell_skipped() -> None:
    """An empty closure cell is skipped without error."""
    assert collect_raised(make_empty_cell()) == frozenset()


def test_shared_cache_reused_across_roots() -> None:
    """One parse cache serves two roots that share a helper."""
    cache: _ScanCache = {}

    first = _collect(uses_factory_keyword, max_depth=10, cache=cache)
    cached_after_first = get_or_404.__code__ in cache
    second = _collect(uses_factory_positional, max_depth=10, cache=cache)

    assert first == frozenset({NotFoundError})
    assert second == frozenset({ConflictError})
    assert cached_after_first
