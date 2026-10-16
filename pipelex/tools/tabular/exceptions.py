from typing import ClassVar

from mthds.protocol.problem.registry import CoreCode

from pipelex.errors.error_code_declaration import ErrorCodeDeclaration, ErrorCodeSet
from pipelex.system.exceptions import ToolError


class CsvError(ToolError):
    """Base for CSV codec errors, also raised directly.

    CSV problems are mostly caller-fixable input issues (a missing/unreadable file, a header
    that does not match the row concept, a cell that cannot be coerced), so the default is
    ``input.invalid``. Writing a table the CLI's ``--save-csv`` asked for is
    ``request.invalid``, and a delimiter or a row the codec was handed by its own caller is
    ``runtime.unexpected``.
    """

    error_code: ClassVar[ErrorCodeDeclaration] = ErrorCodeSet(
        default=CoreCode.INPUT_INVALID, others=(CoreCode.REQUEST_INVALID, CoreCode.RUNTIME_UNEXPECTED)
    )
    # The whole family describes faults in the caller's OWN CSV input (a missing file, a header that
    # does not match the concept, a cell that will not coerce), so the message is safe and useful to
    # expose. Opt in so STRICT disclosure keeps it instead of redacting it to a generic placeholder.
    _authors_caller_facing_message = True


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
