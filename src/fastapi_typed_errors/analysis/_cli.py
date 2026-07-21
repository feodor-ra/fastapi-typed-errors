"""The typer application behind the ``fastapi-typed-errors`` command."""

import importlib
import sys
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from fastapi import APIRouter, FastAPI
from rich.console import Console
from rich.table import Table

from .checker import RaisesReport, check_raises

cli = typer.Typer(add_completion=False, help="Typed error tools for FastAPI.")
_out = Console()
_err = Console(stderr=True)


@cli.callback()
def _root() -> None:
    """Group the subcommands so ``check`` must be named explicitly."""


@cli.command()
def check(
    app_path: Annotated[str, typer.Argument(help="Application as 'module:attribute', e.g. app.main:app.")],
    *,
    allow_overdeclared: Annotated[bool, typer.Option(help="Ignore declared-but-not-raised errors.")] = False,
    max_depth: Annotated[int, typer.Option(help="Call levels to expand below each endpoint.")] = 10,
) -> None:
    """Check that every route's ``Raises`` declarations match the errors it can raise.

    Args:
        app_path: The application import path, ``module:attribute``.
        allow_overdeclared: Ignore declared-but-not-raised errors.
        max_depth: How many call levels below each endpoint to expand.

    Raises:
        Exit: Code 0 when declarations match, 1 on discrepancies, 2 on usage
            or loading errors.
    """
    target = _load_target(app_path)
    try:
        report = check_raises(target, allow_overdeclared=allow_overdeclared, max_depth=max_depth)
    except TypeError as exc:
        _fail(str(exc))
    if report.ok:
        _out.print(f"[green]All {report.checked} route(s) match their Raises declarations.[/green]")
        raise typer.Exit(0)
    _render(report)
    raise typer.Exit(1)


def _load_target(app_path: str) -> FastAPI | APIRouter:
    """Import ``module:attribute`` and return the application or router it names.

    Args:
        app_path: The import path in ``module:attribute`` form.

    Returns:
        FastAPI | APIRouter: The loaded target (or exits 2 via ``_fail``).
    """
    sys.path.insert(0, str(Path.cwd()))
    if ":" not in app_path:
        _fail(f"Expected 'module:attribute', got {app_path!r}.")
    module_name, _, attribute = app_path.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        _fail(f"Cannot import {module_name!r}: {exc}.")
    target = getattr(module, attribute, None)
    if not isinstance(target, FastAPI | APIRouter):
        _fail(f"{app_path!r} is not a FastAPI app or APIRouter.")
    return target


def _render(report: RaisesReport) -> None:
    """Print the discrepancy table and a summary line.

    Args:
        report: The report to render.
    """
    table = Table("Route", "Undeclared", "Overdeclared")
    for route in report.routes:
        methods = " ".join(sorted(route.methods)) or "?"
        table.add_row(
            f"{methods} {route.path}",
            "\n".join(error.__name__ for error in route.undeclared) or "-",
            "\n".join(error.__name__ for error in route.overdeclared) or "-",
        )
    _out.print(table)
    _out.print(f"[yellow]{len(report.routes)} of {report.checked} route(s) have discrepancies.[/yellow]")


def _fail(message: str) -> NoReturn:
    """Print an error message and exit with the usage-error code.

    Args:
        message: The message to show.

    Raises:
        Exit: Always, with code 2.
    """
    _err.print(f"[red]{message}[/red]")
    raise typer.Exit(2)
