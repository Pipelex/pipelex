from mthds.protocol.problem.registry import CoreCode
from pydantic import BaseModel

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import ErrorCodeSet


class SyntaxErrorData(BaseModel):
    message: str
    lineno: int | None = None
    offset: int | None = None
    text: str | None = None
    end_lineno: int | None = None
    end_offset: int | None = None

    @classmethod
    def from_syntax_error(cls, syntax_error: SyntaxError) -> "SyntaxErrorData":
        return cls(
            message=syntax_error.msg,
            lineno=syntax_error.lineno,
            offset=syntax_error.offset,
            text=syntax_error.text,
            end_lineno=syntax_error.end_lineno,
            end_offset=syntax_error.end_offset,
        )


class ConceptStructureGeneratorError(PipelexError):
    """A concept structure whose Python class cannot be generated; ``runtime.unexpected`` for an invariant of the generator."""

    error_code = ErrorCodeSet(default=CoreCode.METHOD_CONCEPT_INVALID, others=(CoreCode.RUNTIME_UNEXPECTED,))

    def __init__(self, message: str, structure_class_python_code: str | None = None, syntax_error_data: SyntaxErrorData | None = None):
        self.structure_class_python_code = structure_class_python_code
        self.syntax_error_data = syntax_error_data
        super().__init__(message)


class ConceptStructureValidationError(PipelexError):
    """A generated structure class that does not hold, such as one naming a base class that is not registered."""

    error_code = CoreCode.METHOD_CONCEPT_INVALID
