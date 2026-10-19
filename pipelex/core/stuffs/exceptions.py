from typing import ClassVar

from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import ABSTRACT_ERROR, ErrorCodeDeclaration, ErrorCodeSet


class StuffError(PipelexError):
    error_code: ClassVar[ErrorCodeDeclaration] = ABSTRACT_ERROR


class StuffFactoryError(StuffError):
    """A stuff that cannot be built from what it is given.

    The default ``input.invalid`` is an input of a malformed shape; a raise site chooses ``input.wrong_concept`` for
    an input whose concept is not the one declared, and ``pipe.output_invalid`` or ``pipe.output_multiplicity`` for
    a pipe's output that does not hold what it combines.
    """

    error_code = ErrorCodeSet(
        default=CoreCode.INPUT_INVALID,
        others=(CoreCode.INPUT_WRONG_CONCEPT, CoreCode.PIPE_OUTPUT_INVALID, CoreCode.PIPE_OUTPUT_MULTIPLICITY),
    )


class StuffContentFactoryError(StuffError):
    """A content that cannot be built from a value, such as a date that is not ISO; ``runtime.unexpected`` for a class that is no content."""

    error_code = ErrorCodeSet(default=CoreCode.INPUT_INVALID, others=(CoreCode.RUNTIME_UNEXPECTED,))


class StuffContentTypeError(StuffError):
    """A typed accessor read a content of another type than the one the method expects."""

    error_code = CoreCode.METHOD_WIRING_INVALID

    def __init__(self, message: str, expected_type: str, actual_type: str):
        self.expected_type = expected_type
        self.actual_type = actual_type
        super().__init__(message)


class DateContentError(StuffError):
    """Raised when a DateContent operation needs a time of day the value does not carry.

    The only such operation today is ``to_datetime()`` on a date-only value: converting it
    would invent a time, which the Date concept refuses to do (no silent midnight). It is reached only from a
    PipeFunc's own code, so its reader sees the function's failure.
    """

    error_code = CoreCode.PIPE_FUNCTION_RAISED


class StuffContentValidationError(StuffError):
    """Raised when content validation fails during type conversion."""

    error_code = CoreCode.METHOD_WIRING_INVALID

    def __init__(self, original_type: str, target_type: str, validation_error: str):
        self.original_type = original_type
        self.target_type = target_type
        self.validation_error = validation_error
        super().__init__(f"Failed to validate content from {original_type} to {target_type}: {validation_error}")
