"""AST walker: which ``BaseError`` subclasses a callable can raise."""

import ast
import inspect
import textwrap
from collections import deque
from collections.abc import Callable
from types import CodeType
from typing import Any, NamedTuple, TypeGuard, override

from ..core.base import BaseError
from ..decorator.wrapper import _unwrap_endpoint

type _NameSpec = tuple[str, str] | tuple[str, tuple[str, ...]]
type _ScanCache = dict[CodeType, "_Parsed"]


class _Parsed(NamedTuple):
    """AST-derived name references of one function body — depth-independent, cacheable by code.

    Attributes:
        candidate_specs: Name references that might resolve to a raised error class.
        callee_specs: Name references of called callables to recurse into.
    """

    candidate_specs: tuple[_NameSpec, ...]
    callee_specs: tuple[_NameSpec, ...]


def collect_raised(fn: Callable[..., Any], *, max_depth: int = 10) -> frozenset[type[BaseError[Any]]]:
    """Find every ``BaseError`` subclass a callable can raise, directly or via helpers.

    The body is parsed with ``ast``; ``raise`` sites and error classes passed as
    call arguments (the ``get_or_404(error=NotFoundError)`` pattern) are collected,
    and called module-level helpers are followed up to ``max_depth`` levels deep.
    Names are resolved against the function's globals and closure; unresolvable or
    unsourceable callables (builtins, C extensions, lambdas) are silently skipped.

    Args:
        fn: The callable to analyze (function, method, ``functools.partial``,
            class or callable instance).
        max_depth: How many call levels below the body to expand (0 = body only).

    Returns:
        frozenset[type[BaseError[Any]]]: The concrete error classes found.
    """
    return _collect(fn, max_depth=max_depth, cache={})


def _collect(
    fn: Callable[..., Any],
    *,
    max_depth: int,
    cache: _ScanCache,
) -> frozenset[type[BaseError[Any]]]:
    """Breadth-first worklist over the call graph, sharing one parse cache.

    Args:
        fn: The root callable to analyze.
        max_depth: How many call levels below the body to expand.
        cache: Parse cache keyed by code object, shared across a whole run.

    Returns:
        frozenset[type[BaseError[Any]]]: The concrete error classes found.
    """
    queue: deque[tuple[Callable[..., Any], int]] = deque([(fn, 0)])
    seen: set[Callable[..., Any]] = set()
    result: set[type[BaseError[Any]]] = set()
    while queue:
        current, depth = queue.popleft()
        target = _normalize(current)
        if target in seen:
            continue
        seen.add(target)
        parsed = _parsed(target, cache)
        namespace = _namespace(target)
        for spec in parsed.candidate_specs:
            resolved = _resolve(spec, namespace)
            if _is_concrete_error(resolved):
                result.add(resolved)
        if depth < max_depth:
            for spec in parsed.callee_specs:
                resolved = _resolve(spec, namespace)
                if callable(resolved) and not _is_concrete_error(resolved):
                    queue.append((resolved, depth + 1))
    return frozenset(result)


def _normalize(obj: Callable[..., Any]) -> Callable[..., Any]:
    """Reduce a callable to the function object whose source carries the raises.

    Args:
        obj: The callable as enqueued.

    Returns:
        Callable[..., Any]: The unwrapped function; a class becomes its ``__init__``.
    """
    fn = _unwrap_endpoint(obj)
    if isinstance(fn, type):
        return fn.__init__
    return fn


def _parsed(fn: Callable[..., Any], cache: _ScanCache) -> _Parsed:
    """Return the cached parse of a function body, computing it on first sight.

    Args:
        fn: The normalized callable to parse.
        cache: Parse cache keyed by code object.

    Returns:
        _Parsed: The name references found in the body (empty if unsourceable).
    """
    code = getattr(fn, "__code__", None)
    if code is not None and code in cache:
        return cache[code]
    parsed = _scan(fn)
    if code is not None:
        cache[code] = parsed
    return parsed


def _scan(fn: Callable[..., Any]) -> _Parsed:
    """Parse one function body into candidate and callee name references.

    Args:
        fn: The normalized callable to scan.

    Returns:
        _Parsed: The name references; empty when the source cannot be parsed.
    """
    try:
        source = textwrap.dedent(inspect.getsource(fn))
        tree = ast.parse(source)
    except (OSError, TypeError, SyntaxError):
        return _Parsed((), ())
    func = next(
        (node for node in tree.body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)),
        None,
    )
    if func is None:
        return _Parsed((), ())
    visitor = _BodyVisitor()
    visitor.visit(func)
    return _Parsed(tuple(visitor.candidate_specs), tuple(visitor.callee_specs))


def _namespace(fn: Callable[..., Any]) -> dict[str, Any]:
    """Build the name-resolution namespace: closure variables over module globals.

    Args:
        fn: The callable whose scope to reconstruct.

    Returns:
        dict[str, Any]: Global names updated with (shadowed by) closure variables.
    """
    namespace: dict[str, Any] = dict(getattr(fn, "__globals__", {}))
    code = getattr(fn, "__code__", None)
    closure = getattr(fn, "__closure__", None)
    if code is not None and closure is not None:
        for name, cell in zip(code.co_freevars, closure, strict=False):
            try:
                namespace[name] = cell.cell_contents
            except ValueError:
                continue
    return namespace


def _resolve(spec: _NameSpec, namespace: dict[str, Any]) -> object:
    """Resolve a name reference against a namespace, following attribute chains.

    Args:
        spec: A ``("name", id)`` or ``("attr", (head, *attrs))`` reference.
        namespace: The name-resolution namespace.

    Returns:
        object: The resolved object, or ``None`` when any step is missing.
    """
    kind, payload = spec
    if kind == "name":
        return namespace.get(payload)
    head, *attrs = payload
    obj = namespace.get(head)
    for attr in attrs:
        if obj is None:
            return None
        obj = getattr(obj, attr, None)
    return obj


def _is_concrete_error(obj: object) -> TypeGuard[type[BaseError[Any]]]:
    """Report whether an object is a concrete ``BaseError`` subclass with a code.

    Args:
        obj: The resolved object to test.

    Returns:
        TypeGuard[type[BaseError[Any]]]: ``True`` only for subclasses declaring
            both ``error_code`` and ``http_status`` (excludes ``BaseError`` and
            codeless intermediate bases).
    """
    if not (isinstance(obj, type) and issubclass(obj, BaseError)):
        return False
    try:
        _ = (obj.error_code, obj.http_status)
    except AttributeError:
        return False
    return True


def _spec(node: ast.expr) -> _NameSpec | None:
    """Turn a ``Name`` or dotted ``Attribute`` node into a resolvable reference.

    Args:
        node: The AST expression to inspect.

    Returns:
        _NameSpec | None: The reference, or ``None`` when the head is not a plain
            name (e.g. ``self.svc.foo`` or ``factory().attr``).
    """
    if isinstance(node, ast.Name):
        return ("name", node.id)
    if isinstance(node, ast.Attribute):
        attrs: list[str] = []
        current: ast.expr = node
        while isinstance(current, ast.Attribute):
            attrs.append(current.attr)
            current = current.value
        if not isinstance(current, ast.Name):
            return None
        attrs.append(current.id)
        attrs.reverse()
        return ("attr", tuple(attrs))
    return None


class _BodyVisitor(ast.NodeVisitor):
    """Collect raised-error and callee name references from a function body.

    Descends into statement bodies only — annotations, decorators and argument
    defaults are skipped, so a route's own ``Raises[...]`` return annotation and
    its ``Depends(...)`` defaults never count as raised.

    Attributes:
        candidate_specs: References that might be raised error classes.
        callee_specs: References of called callables to recurse into.
    """

    def __init__(self) -> None:
        """Initialize empty reference lists."""
        self.candidate_specs: list[_NameSpec] = []
        self.callee_specs: list[_NameSpec] = []

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit only the statements of a (possibly nested) function body.

        Args:
            node: The function definition node.
        """
        for statement in node.body:
            self.visit(statement)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit only the statements of an async function body.

        Args:
            node: The async function definition node.
        """
        for statement in node.body:
            self.visit(statement)

    @override
    def visit_Raise(self, node: ast.Raise) -> None:
        """Record the raised type, whether ``raise X`` or ``raise X(...)``.

        Args:
            node: The raise statement node.
        """
        raised = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
        spec = _spec(raised) if raised is not None else None
        if spec is not None:
            self.candidate_specs.append(spec)
        self.generic_visit(node)

    @override
    def visit_Call(self, node: ast.Call) -> None:
        """Record the callee and every error class passed as an argument.

        Args:
            node: The call node.
        """
        callee = _spec(node.func)
        if callee is not None:
            self.callee_specs.append(callee)
        name = node.func.id if isinstance(node.func, ast.Name) else None
        if name not in {"isinstance", "issubclass"}:
            arguments = [*node.args, *(keyword.value for keyword in node.keywords)]
            self.candidate_specs.extend(spec for argument in arguments if (spec := _spec(argument)) is not None)
        self.generic_visit(node)
