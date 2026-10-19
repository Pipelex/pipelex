from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError


class QualifiedRefError(PipelexError, ValueError):
    """Raised when a qualified reference string is invalid.

    A ``ValueError`` too, since the guards that parse a reference inside pydantic validators catch it as one.
    """

    error_code = CoreCode.METHOD_SCHEMA_VIOLATION
