"""Console-script launcher that degrades gracefully without the ``cli`` extra."""

import sys


def main() -> None:
    """Run the CLI, or explain how to install it when ``typer`` is missing.

    Raises:
        SystemExit: With code 2 when the ``cli`` extra is not installed.
    """
    try:
        from ._cli import cli  # ruff:ignore[import-outside-top-level]
    except ImportError:
        sys.stderr.write("The CLI needs the 'cli' extra: pip install 'fastapi-typed-errors[cli]'\n")
        raise SystemExit(2) from None
    cli()
