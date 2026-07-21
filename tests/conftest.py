"""Shared pytest configuration: anyio-powered ``async def`` tests."""

import inspect

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Run async tests on the asyncio backend.

    Returns:
        str: The anyio backend name.
    """
    return "asyncio"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every ``async def`` test with the anyio marker automatically.

    Args:
        items: Collected test items, mutated in place.
    """
    for item in items:
        if isinstance(item, pytest.Function) and inspect.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.anyio)
