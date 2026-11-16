from typing import Any, ClassVar, Self

from mthds.protocol.problem.models import ProblemLocation
from mthds.protocol.problem.registry import CoreCode
from typing_extensions import override

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import ABSTRACT_ERROR, ErrorCodeDeclaration, ErrorCodeSet
from pipelex.errors.problem import make_location
from pipelex.tools.uri.exceptions import StoredTextUnreadableReason


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


class StoredValueNotLoadedError(StuffError):
    """A text, HTML or JSON value held in storage was read before it was loaded.

    A content past the inline threshold carries a URL to its value instead of the value. The code that reads it must
    load it first, with ``load_stored_value``, which only code allowed to perform IO can do; a synchronous render that meets a
    reference never loaded raises this rather than printing nothing. It is always the runtime's own fault: a reader
    that forgot to load.
    """

    error_code = CoreCode.RUNTIME_UNEXPECTED


class StoredValueUnreadableError(StuffError):
    """The stored value of a content could be read but is not a value of its kind, such as a JSON value that is not an object.

    The runtime stores only values it holds, which are always of their kind, so a stored value that is not is a URL a
    caller or a method pointed at the wrong file: ``input.file_unreadable``, naming the kind the value was read as and
    why it failed, and the input whose value it is once the reader that knows it names it (`with_input`).
    """

    error_code = CoreCode.INPUT_FILE_UNREADABLE

    def __init__(self, message: str, *, file_type: str, reason: StoredTextUnreadableReason):
        super().__init__(message)
        # The kind of value it was read as, the `file_type` of `input.file_unreadable`: "json".
        self.file_type = file_type
        self.reason = reason
        self.input_name: str | None = None

    def with_input(self, *, input_name: str | None) -> Self:
        """Name, where it is caught, the input whose stored value could not be read; ``None`` names nothing.

        Returns:
            This error, so that the catch site can re-raise it.
        """
        if input_name is not None:
            self.input_name = input_name
        return self

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"input": self.input_name, "file_type": self.file_type, "reason": self.reason}

    @override
    def problem_location(self) -> ProblemLocation | None:
        return make_location(input_name=self.input_name, field=None)
