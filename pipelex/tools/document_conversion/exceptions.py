"""The errors of an Office file's conversion to PDF, each carrying a code the error-handling contract already has.

The conversion adds no code to the MTHDS registry: a file the converter could not read is ``input.file_unreadable``,
a file too large, or too slow to convert, ``input.too_large``, a converter busy or unreachable ``runtime.unavailable``,
and a backend named but unusable ``runtime.misconfigured``. The converter does not know which input the file came
from; the step that converts names it with :meth:`DocumentConversionError.with_input`.
"""

from enum import StrEnum
from typing import Any, ClassVar, Self

from mthds.protocol.problem.registry import CoreCode
from typing_extensions import override

from pipelex.errors.error_code_declaration import ABSTRACT_ERROR, ErrorCodeDeclaration
from pipelex.errors.problem import ProblemLocation, make_location
from pipelex.system.exceptions import ToolError

# The `component` a misconfigured converter names, read by whoever runs the runtime: the configuration's table.
DOCUMENT_CONVERSION_COMPONENT = "runtime.document_conversion"
# The `dependency` an unavailable converter names, read by whoever runs the runtime.
DOCUMENT_CONVERTER_DEPENDENCY = "document_converter"
# Why the converter could not read a file, the `reason` of `input.file_unreadable`.
CONVERSION_FAILED_REASON = "conversion_failed"


class ConversionLimitKind(StrEnum):
    """What a conversion outgrew: the source's size in bytes, or the time the converter is given, in seconds.

    Both are `input.too_large` (decision box 4 of the runtime seam's design): a file that cannot convert in the time
    the converter gives it is, for this converter, too big, and the remedy is the same, a smaller or simpler file.
    """

    BYTES = "bytes"
    SECONDS = "seconds"


class DocumentConversionError(ToolError):
    """The base of the errors a conversion refuses a file with, which name the input the step gives them."""

    error_code: ClassVar[ErrorCodeDeclaration] = ABSTRACT_ERROR

    def __init__(self, message: str, *, format_key: str):
        super().__init__(message)
        # The format of the file the converter was given, such as `docx`.
        self.format_key = format_key
        # The input the file came from, as a caller writes it, which the step that converts gives.
        self.input_name: str | None = None

    def with_input(self, *, input_name: str) -> Self:
        """Name, where it is caught, the input whose file could not be converted.

        Returns:
            This error, so that the catch site can re-raise it.
        """
        self.input_name = input_name
        return self

    @override
    def problem_location(self) -> ProblemLocation | None:
        return make_location(input_name=self.input_name)


class DocumentUnreadableByConverterError(DocumentConversionError):
    """The converter could not read the file: damaged, protected by a password, or not what its format says.

    Gotenberg answers it with a `400`, `422`, `500` or `504` given twice, since a LibreOffice engine dying
    mid-conversion answers a first one exactly as a damaged file does, and `soffice` by producing no PDF.
    """

    error_code = CoreCode.INPUT_FILE_UNREADABLE

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"input": self.input_name, "file_type": self.format_key, "reason": CONVERSION_FAILED_REASON}


class DocumentTooLargeToConvertError(DocumentConversionError):
    """The file is past what the converter takes, in bytes, or took longer to convert than the converter allows.

    The source past `max_source_bytes`, or Gotenberg's `413`, is a size in bytes. Gotenberg's `503`, a connection the
    converter dropped after its budget, or `soffice` killed at its timeout is a time in seconds, which the message
    names as the limit, and the problem's `limit` and `size` are then seconds.
    """

    error_code = CoreCode.INPUT_TOO_LARGE

    def __init__(self, message: str, *, format_key: str, limit_kind: ConversionLimitKind, limit: int, size: int):
        super().__init__(message, format_key=format_key)
        self.limit_kind = limit_kind
        # The bound the file passed, in bytes or in seconds as `limit_kind` says.
        self.limit = limit
        # How far the file went, in the same unit: its size, or how long the conversion ran before it was stopped.
        self.size = size

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"input": self.input_name, "limit": self.limit, "size": self.size}


class DocumentConverterUnavailableError(ToolError):
    """The converter is busy or cannot be reached, after the backend's own short retries.

    Gotenberg's `429`, a connection refused or dropped before the converter's budget, or a status that says nothing
    about the file. It is not the input's fault, so the orchestrator may retry the step as it retries this code.
    """

    error_code = CoreCode.RUNTIME_UNAVAILABLE

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"dependency": DOCUMENT_CONVERTER_DEPENDENCY}


class DocumentConverterAnswerError(ToolError):
    """The converter said it converted the file but answered something that is not a PDF: a fault of the converter."""

    error_code = CoreCode.RUNTIME_UNEXPECTED


class DocumentFormatNotConvertibleError(ToolError):
    """A converter was asked to convert a format the runtime does not convert: a fault of the caller, which checks first."""

    error_code = CoreCode.RUNTIME_UNEXPECTED


class DocumentConverterMisconfiguredError(ToolError):
    """The configured conversion backend cannot be used: a Gotenberg URL missing, or a `soffice` binary not found.

    Raised at boot, so the operator learns it when the runtime starts rather than at the first Office file.
    """

    error_code = CoreCode.RUNTIME_MISCONFIGURED

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"component": DOCUMENT_CONVERSION_COMPONENT}
