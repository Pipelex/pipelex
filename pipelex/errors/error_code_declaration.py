"""How a ``PipelexError`` subclass declares the code it raises.

Every subclass of :class:`~pipelex.base_exceptions.PipelexError` sets ``error_code`` in its own class body,
and a test fails the build on one that does not (``tests/unit/pipelex/errors/test_error_code_gate.py``).
The declaration is one of four:

- **A code**, a :class:`~mthds.protocol.problem.registry.CoreCode` or a
  :class:`~pipelex.errors.registry.pipelex_codes.PipelexErrorCode`: every instance raises that code.
- **A set**, :class:`ErrorCodeSet`: the raise site chooses one of its codes with
  :meth:`~pipelex.base_exceptions.PipelexError.with_error_code`, and an instance whose raise site chose none
  carries the set's default. A class whose raise sites need different verdicts declares a set rather than
  letting a raise site set a domain or a verdict of its own, since a verdict belongs to a code.
- **Its cause's code**, :class:`InheritsCause`: a wrapper that adds no fact deciding the code takes the code
  of its cause, and carries its fallback when the cause is not a coded error. A raise site that knows the
  code itself may still choose its fallback or one of its ``others`` with ``with_error_code``, and the walk
  then stops there.
- **An abstract base**, :data:`ABSTRACT_ERROR`: a base class that is never raised directly. The gate also
  refuses a ``raise`` of such a class anywhere in the package.

The code of a raised error is resolved by walking its ``__cause__`` chain: the walk descends through every
error that takes its cause's code and stops at the first that declares one, so that a wrapper which adds
the fact that decides the code keeps its own over a coded cause.
"""

from __future__ import annotations

from typing import Self, TypeAlias

from pydantic import ConfigDict, model_validator
from pydantic.dataclasses import dataclass

from pipelex.errors.error_codes import ErrorCode


@dataclass(frozen=True, config=ConfigDict(arbitrary_types_allowed=True))
class ErrorCodeSet:
    """The codes a class's raise sites choose from, the first being the default.

    Attributes:
        default: The code an instance carries when its raise site chose none.
        others: The other codes a raise site may choose.
    """

    default: ErrorCode
    others: tuple[ErrorCode, ...]

    @model_validator(mode="after")
    def _validate_codes(self) -> Self:
        if not self.others:
            msg = "A set of codes holds more than one code; a class raising one code declares that code."
            raise ValueError(msg)
        if len(set(self.codes)) != len(self.codes):
            msg = f"A set of codes names a code twice: {', '.join(self.codes)}."
            raise ValueError(msg)
        return self

    @property
    def codes(self) -> tuple[ErrorCode, ...]:
        """Every code of the set, the default first."""
        return (self.default, *self.others)


@dataclass(frozen=True, config=ConfigDict(arbitrary_types_allowed=True))
class InheritsCause:
    """The class takes the code of its cause, or its fallback when the cause carries none.

    Attributes:
        fallback: The code an instance carries when no error along its ``__cause__`` chain declares one.
        others: The codes a raise site that knows the code itself may choose, besides the fallback.
    """

    fallback: ErrorCode
    others: tuple[ErrorCode, ...] = ()

    @model_validator(mode="after")
    def _validate_codes(self) -> Self:
        if len(set(self.codes)) != len(self.codes):
            msg = f"A cause's fallback and the codes a raise site may choose name a code twice: {', '.join(self.codes)}."
            raise ValueError(msg)
        return self

    @property
    def codes(self) -> tuple[ErrorCode, ...]:
        """The fallback, then the codes a raise site may choose."""
        return (self.fallback, *self.others)


@dataclass(frozen=True)
class AbstractError:
    """The declaration of a base class that is never raised directly."""


ABSTRACT_ERROR = AbstractError()
"""The declaration of a base class that is never raised directly."""

ErrorCodeDeclaration: TypeAlias = ErrorCode | ErrorCodeSet | InheritsCause | AbstractError
"""What a ``PipelexError`` subclass declares about the code it raises."""


def describe_error_code_declaration(declaration: ErrorCodeDeclaration) -> str:
    """A one-line reading of a declaration, as the error identity snapshot records it.

    Args:
        declaration: A class's declaration.

    Returns:
        The code; ``one of`` the codes of a set, the default first; ``inherits cause, else`` the fallback;
        or ``abstract``.
    """
    if isinstance(declaration, ErrorCodeSet):
        return "one of " + ", ".join(declaration.codes)
    if isinstance(declaration, InheritsCause):
        described = f"inherits cause, else {declaration.fallback}"
        if declaration.others:
            described += "; or chosen: " + ", ".join(declaration.others)
        return described
    if isinstance(declaration, AbstractError):
        return "abstract"
    return str(declaration)


def declared_error_codes(declaration: ErrorCodeDeclaration) -> tuple[ErrorCode, ...]:
    """Every code a declaration names, which are the codes a raise site may choose.

    A code alone; a set's codes; a cause's fallback and the codes a raise site may choose besides it; or none
    for an abstract base.
    """
    if isinstance(declaration, (ErrorCodeSet, InheritsCause)):
        return declaration.codes
    if isinstance(declaration, AbstractError):
        return ()
    return (declaration,)
