"""Core primitives: ``ErrorResponse``, the metaclass and ``BaseError``."""

from http import HTTPStatus
from typing import Any, ClassVar, Literal, TypeVar, get_args, get_origin

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict


# Exception to the public-first ordering: referenced in the ErrorResponse class
# body below, so it must be defined first.
def _model_title(model_cls: type) -> str:
    """Build a clean OpenAPI title for parametrized response models.

    Pydantic's default title for ``ErrorResponse[Literal[Code.X]]`` embeds the
    enum member ``repr()`` — angle brackets included — into user-facing API
    docs; this generator renders ``ErrorResponse[X]`` instead.

    The parameter is a plain ``type`` because ``ConfigDict`` types the
    generator as ``(type, /) -> str`` and parameters are contravariant.

    Args:
        model_cls: The (possibly parametrized) response model class.

    Returns:
        str: ``Origin[CODE]`` for parametrized models, the plain class name
            otherwise.
    """
    metadata = getattr(model_cls, "__pydantic_generic_metadata__", None)
    if metadata is None or metadata["origin"] is None:
        return model_cls.__name__
    codes = ", ".join(str(value) for arg in metadata["args"] for value in get_args(arg))
    return f"{metadata['origin'].__name__}[{codes}]"


class ErrorResponse[T: str](BaseModel):
    """Error response body.

    ``T`` is the ``Literal`` type of the error code — a ``StrEnum`` member or
    a plain string — so OpenAPI renders the exact value instead of the whole
    enum.

    Attributes:
        code: Machine-readable error code, narrowed to a ``Literal`` type.
        detail: Human-readable explanation of the error.
    """

    model_config = ConfigDict(model_title_generator=_model_title)

    code: T
    detail: str


class BaseErrorMeta(type):
    """Metaclass deriving ``error_code`` and ``model`` for ``BaseError`` subclasses.

    When a concrete subclass is parametrized with a ``Literal`` code, the code
    is extracted from ``__orig_bases__`` and written into the class namespace
    together with the parametrized response model — before ``type.__new__``,
    so the metaclass properties below never shadow the stored values.

    Public so that mixing ``BaseError`` with ``ABC`` (or another
    custom-metaclass base) can be resolved with a combined metaclass;
    deliberately not re-exported from the package root.
    """

    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: object,
    ) -> type:
        """Create the class, deriving ``error_code`` and ``model`` when declared.

        Args:
            name: Name of the class being created.
            bases: Base classes.
            namespace: Class namespace; mutated in place when a code is found.
            **kwargs: Extra keyword arguments forwarded to ``type.__new__``.

        Returns:
            type: The newly created class.
        """
        code = mcs._extract_code(namespace)
        if code is not None:
            response_base = mcs._resolve_response_base(namespace, bases)
            namespace["error_code"] = code
            # Runtime parametrization: not expressible for static checkers.
            namespace["model"] = response_base[Literal[code]]  # ty: ignore[invalid-type-form]
        return super().__new__(mcs, name, bases, namespace, **kwargs)

    @property
    def error_code(cls) -> str:
        """Error code extracted from the generic parameter at class creation.

        Returns:
            str: The code declared via ``BaseError[Literal[<code>]]``.

        Raises:
            AttributeError: If no class in the MRO declares a code.
        """
        for klass in cls.__mro__:
            if "error_code" in vars(klass):
                return vars(klass)["error_code"]
        msg = f"{cls.__name__}.error_code is not defined; subclass BaseError[Literal[<code>]]"
        raise AttributeError(msg)

    @property
    def model(cls) -> type[ErrorResponse[Any]]:
        """Pydantic response model parametrized with the error code.

        Returns:
            type[ErrorResponse[Any]]: The parametrized subclass of
                ``response_base``.

        Raises:
            AttributeError: If no class in the MRO declares a code.
        """
        for klass in cls.__mro__:
            if "model" in vars(klass):
                return vars(klass)["model"]
        msg = f"{cls.__name__}.model is not defined; subclass BaseError[Literal[<code>]]"
        raise AttributeError(msg)

    @classmethod
    def _extract_code(cls, namespace: dict[str, Any]) -> str | None:
        """Pull the error code out of the ``BaseError[Literal[...]]`` generic parameter.

        Args:
            namespace: Namespace of the class being created.

        Returns:
            str | None: The declared code, or ``None`` when the class is an
                intermediate generic base parametrized with a ``TypeVar``.

        Raises:
            TypeError: If the generic parameter is anything but a ``TypeVar``
                or a ``Literal`` holding exactly one string code.
        """
        for orig_base in namespace.get("__orig_bases__", ()):
            if not isinstance(get_origin(orig_base), cls):
                continue
            type_args = get_args(orig_base)
            if len(type_args) != 1:
                continue
            arg = type_args[0]
            if isinstance(arg, TypeVar):
                # An intermediate generic base: class AppError[T: str](BaseError[T]).
                continue
            literal_args = get_args(arg) if get_origin(arg) is Literal else ()
            if len(literal_args) != 1 or not isinstance(literal_args[0], str):
                # Fail at class definition time: a mistake like BaseError[str] would
                # otherwise surface only at request time as an opaque 500.
                msg = (
                    "BaseError expects Literal with exactly one string code "
                    f"(a StrEnum member or a plain str), got {arg!r}"
                )
                raise TypeError(msg)
            return literal_args[0]
        return None

    @staticmethod
    def _resolve_response_base(
        namespace: dict[str, Any],
        bases: tuple[type, ...],
    ) -> type[ErrorResponse[Any]]:
        """Find the ``response_base`` this subclass should parametrize.

        Args:
            namespace: Namespace of the class being created; wins when it
                declares ``response_base`` itself.
            bases: Base classes searched (via their MRO) otherwise.

        Returns:
            type[ErrorResponse[Any]]: The response model class to parametrize
                with the error code.
        """
        if "response_base" in namespace:
            return namespace["response_base"]
        for base in bases:
            found = getattr(base, "response_base", None)
            if found is not None:
                return found
        return ErrorResponse


class BaseError[T: str](HTTPException, metaclass=BaseErrorMeta):
    """Base class for typed HTTP errors.

    A concrete subclass declares ``http_status`` and passes its error code as
    the generic parameter — everything else is derived by the metaclass.
    Plain string codes work too: ``BaseError[Literal["NOT_FOUND"]]``.

    Example:
        ::

            class ErrorCode(StrEnum):
                NOT_FOUND = "NOT_FOUND"

            class NotFoundError(BaseError[Literal[ErrorCode.NOT_FOUND]]):
                http_status = HTTPStatus.NOT_FOUND
                description = "Requested entity does not exist"

    Attributes:
        http_status: HTTP status the error responds with — the only required
            declaration in a subclass.
        description: Optional human-readable summary; used for OpenAPI status
            descriptions and as the default ``detail``.
        response_base: Generic response model the metaclass parametrizes;
            override to customize the response body.
        error_code: Error code extracted from the generic parameter; set by
            the metaclass.
        model: Response model parametrized with the error code; set by the
            metaclass.
    """

    http_status: ClassVar[HTTPStatus]
    description: ClassVar[str | None] = None
    response_base: ClassVar[type[ErrorResponse[Any]]] = ErrorResponse

    # Duplicated as annotations to bind T; actual values are set by the metaclass.
    error_code: T
    model: type[ErrorResponse[T]]

    def __init__(
        self,
        detail: str | None = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Initialize the error.

        Args:
            detail: Human-readable explanation; defaults to ``description``
                or the ``http_status`` phrase.
            headers: Extra HTTP headers for the response
                (e.g. ``WWW-Authenticate``).
        """
        if detail is None:
            detail = self.description or self.http_status.phrase
        super().__init__(status_code=self.http_status.value, detail=detail, headers=headers)

    def to_response(self) -> ErrorResponse[T]:
        """Build the response body for this error instance.

        Returns:
            ErrorResponse[T]: An instance of ``model`` carrying ``error_code``
                and ``detail``.
        """
        return self.model(code=self.error_code, detail=str(self.detail))
