"""GraphSpec-specific exceptions."""

from typing import ClassVar

from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import ABSTRACT_ERROR, ErrorCodeDeclaration, ErrorCodeSet


class GraphSpecError(PipelexError):
    """Base exception for GraphSpec-related errors."""

    error_code: ClassVar[ErrorCodeDeclaration] = ABSTRACT_ERROR


class GraphSpecValidationError(GraphSpecError):
    """Exception raised when GraphSpec validation fails.

    This includes invariant violations such as:
    - Missing nodes referenced by edges
    - Duplicate node IDs
    - Duplicate edge IDs
    - Failed status without error specification

    Those are invariants of the graph we assemble, so a violation is ours (`runtime.unexpected`, the
    default); a graph spec file a caller hands back in a shape this version no longer accepts is
    `request.invalid`, which the raise site chooses.
    """

    error_code = ErrorCodeSet(default=CoreCode.RUNTIME_UNEXPECTED, others=(CoreCode.REQUEST_INVALID,))
