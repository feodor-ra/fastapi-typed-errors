"""Layer 2 — declare raisable errors in return annotations via ``with_errors`` + ``Raises``."""

from .raises import Raises
from .wrapper import with_errors

__all__ = (
    "Raises",
    "with_errors",
)
