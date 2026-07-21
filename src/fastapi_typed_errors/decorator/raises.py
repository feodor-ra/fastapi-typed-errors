"""The ``Raises`` marker: declares raisable errors inside a return annotation."""

from typing import Any, Self, override

from ..core.base import BaseError


class Raises:
    """Marker listing the errors a route can raise, for ``Annotated`` return metadata.

    The wrapper created by ``with_errors()`` reads this marker at registration
    time and fills the route's ``responses={}`` accordingly. The marker itself
    is inert: pydantic and FastAPI ignore it, so the success schema stays clean.

    Both spellings are equivalent; the constructor form is handy for shared
    tuples of errors::

        def get_item(item_id: int) -> Annotated[Item, Raises[NotFoundError, ForbiddenError]]: ...
        def get_user(user_id: int) -> Annotated[User, Raises(*TOKEN_ERRORS)]: ...

    Attributes:
        errors: The declared error classes, in declaration order.
    """

    __slots__ = ("errors",)

    errors: tuple[type[BaseError[Any]], ...]

    def __init__(self, *errors: type[BaseError[Any]]) -> None:
        """Validate and store the declared error classes.

        Args:
            *errors: ``BaseError`` subclasses with a declared code and status.

        Raises:
            TypeError: If no classes are given, a member is not a ``BaseError``
                subclass, or a member lacks a declared ``error_code`` /
                ``http_status``.
        """
        if not errors:
            msg = "Raises requires at least one error class"
            raise TypeError(msg)
        for error in errors:
            if not (isinstance(error, type) and issubclass(error, BaseError)):
                msg = f"Raises accepts only BaseError subclasses, got {error!r}"
                raise TypeError(msg)
            try:
                # Probe: the metaclass property raises on codeless classes, http_status may be undeclared.
                _ = (error.error_code, error.http_status)
            except AttributeError as exc:
                msg = f"{error.__name__} cannot be used in Raises: {exc}"
                raise TypeError(msg) from exc
        self.errors = errors

    def __class_getitem__(cls, errors: type[BaseError[Any]] | tuple[type[BaseError[Any]], ...]) -> Self:
        """Build a marker instance from subscription syntax.

        ``Raises[ErrA, ErrB]`` and ``Raises[*SHARED_ERRORS]`` are sugar for
        ``Raises(ErrA, ErrB)``.

        Args:
            errors: A single error class or a tuple of them.

        Returns:
            Self: The validated marker instance.
        """
        items = errors if isinstance(errors, tuple) else (errors,)
        return cls(*items)

    @override
    def __repr__(self) -> str:
        """Render the marker as its subscription form.

        Returns:
            str: E.g. ``Raises[NotFoundError, ForbiddenError]``.
        """
        names = ", ".join(error.__name__ for error in self.errors)
        return f"Raises[{names}]"
