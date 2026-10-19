from typing import Any, ClassVar, Self

from mthds.protocol.problem.registry import CoreCode
from typing_extensions import override

from pipelex.errors.error_code_declaration import ErrorCodeDeclaration, ErrorCodeSet
from pipelex.errors.problem import ProblemLocation, make_location
from pipelex.system.exceptions import ToolError


class CsvError(ToolError):
    """Base for CSV codec errors, also raised directly.

    CSV problems are mostly caller-fixable input issues (a missing/unreadable file, a header
    that does not match the row concept, a cell that cannot be coerced), so the default is
    ``input.invalid``. Writing a table the CLI's ``--save-csv`` asked for is
    ``request.invalid``, and a delimiter or a row the codec was handed by its own caller is
    ``runtime.unexpected``. A table input refused before the codec reads it says what happened instead: a URL that
    does not parse is ``input.file_unreadable``, a URL that is not a local path, which this runtime does not read a
    table from, ``request.unsupported``, and a concept with no structure class to read rows into
    ``method.concept_invalid``.

    The codec reads a file and does not know the run input it was given as: the site that does names it with
    :meth:`with_input`, which gives the problem its ``location.input`` and, for a code declaring it, its ``input``.
    """

    error_code: ClassVar[ErrorCodeDeclaration] = ErrorCodeSet(
        default=CoreCode.INPUT_INVALID,
        others=(
            CoreCode.REQUEST_INVALID,
            CoreCode.RUNTIME_UNEXPECTED,
            CoreCode.INPUT_FILE_UNREADABLE,
            CoreCode.REQUEST_UNSUPPORTED,
            CoreCode.METHOD_CONCEPT_INVALID,
        ),
    )

    def __init__(self, message: str):
        super().__init__(message)
        # The run input the table was given as, which the site that knows it gives.
        self.input_name: str | None = None

    def with_input(self, *, input_name: str | None) -> Self:
        """Name the run input the table was given as, where the site raising or catching the error knows it.

        Returns:
            This error, so that the site can raise it.
        """
        self.input_name = input_name
        return self

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"input": self.input_name}

    @override
    def problem_location(self) -> ProblemLocation | None:
        return make_location(input_name=self.input_name)


class CsvReadError(CsvError):
    """Raised when a CSV file cannot be opened, decoded, or parsed.

    Wraps the raw ``OSError`` (missing file, bad path), ``UnicodeDecodeError`` (wrong
    encoding), and ``csv.Error`` (malformed quoting) at the codec boundary so no raw
    third-party exception escapes into core/runner.
    """

    error_code = CoreCode.INPUT_FILE_UNREADABLE


class CsvFlatnessError(CsvError):
    """Raised when a concept used with CSV is not flat.

    A CSV row concept must have scalar fields only (``text``/``integer``/``number``/
    ``boolean``/``date`` plus optionals and ``Literal``/choice-constrained scalars).
    A nested/list/dict/concept-typed/``Union``/``Any`` field is rejected, naming the
    offending field and telling the author to project to a flat concept first.
    """

    error_code = CoreCode.INPUT_INVALID


class CsvColumnError(CsvError):
    """Raised when CSV headers do not line up with the row concept's fields.

    Covers an unexpected extra column, a missing required column, and duplicate or
    blank header cells. A missing *optional* column is NOT an error: a nullable field
    is set to ``None`` for all rows, while a non-nullable field with a default keeps
    that default.
    """

    error_code = CoreCode.INPUT_INVALID


class CsvCoercionError(CsvError):
    """Raised when a CSV cell value cannot be coerced to its declared field type.

    Carries the 1-based row/column, the concept, and the field so the author can find
    the offending cell.
    """

    error_code = CoreCode.INPUT_INVALID
