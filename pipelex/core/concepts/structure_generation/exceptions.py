from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import ErrorCodeSet


class ConceptStructureGeneratorError(PipelexError):
    """A concept structure whose Python class cannot be built; ``runtime.unexpected`` for an invariant of the generator."""

    error_code = ErrorCodeSet(default=CoreCode.METHOD_CONCEPT_INVALID, others=(CoreCode.RUNTIME_UNEXPECTED,))


class ConceptStructureValidationError(PipelexError):
    """A structure class that does not hold, such as one naming a base class that is not registered."""

    error_code = CoreCode.METHOD_CONCEPT_INVALID
