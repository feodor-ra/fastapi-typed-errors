"""Tests for the analysis CLI (launcher and typer application)."""

import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner
from walker_helpers import ConflictError, NotFoundError

from fastapi_typed_errors.analysis._cli import _render, cli
from fastapi_typed_errors.analysis.checker import RaisesReport, RouteDiscrepancy
from fastapi_typed_errors.analysis.cli import main

runner = CliRunner()


@pytest.fixture
def in_test_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run with the working directory at the test package (for ``cli_apps``).

    Args:
        monkeypatch: The pytest monkeypatch fixture.
    """
    monkeypatch.chdir(Path(__file__).parent)


@pytest.mark.usefixtures("in_test_dir")
def test_matching_app_exits_zero() -> None:
    """A matching app prints the success line and exits 0."""
    result = runner.invoke(cli, ["check", "cli_apps:app_ok"])

    assert result.exit_code == 0
    assert "match" in result.stdout


@pytest.mark.usefixtures("in_test_dir")
def test_discrepant_app_exits_one() -> None:
    """A discrepant app renders the table and exits 1."""
    result = runner.invoke(cli, ["check", "cli_apps:app_bad"])

    assert result.exit_code == 1
    assert "discrepancies" in result.stdout


@pytest.mark.usefixtures("in_test_dir")
def test_overdeclared_app_exits_one() -> None:
    """An overdeclared app fails by default."""
    result = runner.invoke(cli, ["check", "cli_apps:app_over"])

    assert result.exit_code == 1


@pytest.mark.usefixtures("in_test_dir")
def test_allow_overdeclared_flag_passes() -> None:
    """The ``--allow-overdeclared`` flag turns the overdeclared app green."""
    result = runner.invoke(cli, ["check", "cli_apps:app_over", "--allow-overdeclared"])

    assert result.exit_code == 0


@pytest.mark.usefixtures("in_test_dir")
def test_max_depth_option_accepted() -> None:
    """The ``--max-depth`` option is forwarded to the checker."""
    result = runner.invoke(cli, ["check", "cli_apps:app_ok", "--max-depth", "3"])

    assert result.exit_code == 0


@pytest.mark.usefixtures("in_test_dir")
def test_unresolvable_declaration_exits_two() -> None:
    """A propagated ``TypeError`` from bad hints exits 2."""
    result = runner.invoke(cli, ["check", "cli_apps:app_typeerror"])

    assert result.exit_code == 2


@pytest.mark.usefixtures("in_test_dir")
def test_missing_colon_exits_two() -> None:
    """A path without a colon is a usage error."""
    result = runner.invoke(cli, ["check", "justmodule"])

    assert result.exit_code == 2


def test_unimportable_module_exits_two() -> None:
    """An unimportable module is a usage error."""
    result = runner.invoke(cli, ["check", "no_such_module_xyz:app"])

    assert result.exit_code == 2


@pytest.mark.usefixtures("in_test_dir")
def test_wrong_type_attribute_exits_two() -> None:
    """An attribute that is not an app or router is a usage error."""
    result = runner.invoke(cli, ["check", "cli_apps:not_an_app"])

    assert result.exit_code == 2


def test_render_handles_empty_fields() -> None:
    """The table renders empty methods and empty error columns as placeholders."""
    report = RaisesReport(
        routes=(
            RouteDiscrepancy(path="/a", methods=frozenset(), undeclared=(NotFoundError,), overdeclared=()),
            RouteDiscrepancy(path="/b", methods=frozenset({"GET"}), undeclared=(), overdeclared=(ConflictError,)),
        ),
        checked=2,
    )

    _render(report)


def test_main_delegates_to_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """``main`` imports and runs the typer app when the extra is installed."""
    calls: list[bool] = []
    monkeypatch.setattr("fastapi_typed_errors.analysis._cli.cli", lambda: calls.append(True))

    main()

    assert calls == [True]


def test_main_without_typer_exits_two(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """``main`` explains how to install the extra when ``typer`` is missing."""
    monkeypatch.setitem(sys.modules, "typer", None)
    monkeypatch.delitem(sys.modules, "fastapi_typed_errors.analysis._cli", raising=False)

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 2
    assert "cli" in capsys.readouterr().err
