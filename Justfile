# Show available recipes.
help:
    @just --list --unsorted

# Check formatting, lint rules and types.
lint:
    uv run ruff format --check
    uv run ruff check
    uv run ty check
