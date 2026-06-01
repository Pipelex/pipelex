from pipelex.base_exceptions import ErrorDomain
from pipelex.system.exceptions import ToolError


class CsvError(ToolError):
    """Base for CSV codec errors.

    CSV problems are caller-fixable input issues (a missing/unreadable file, a header
    that does not match the row concept, a cell that cannot be coerced), so the whole
    family is classified under the ``INPUT`` error domain.
    """

    error_domain = ErrorDomain.INPUT
    _declared_title = "CSV error"


class CsvReadError(CsvError):
    """Raised when a CSV file cannot be opened, decoded, or parsed.

    Wraps the raw ``OSError`` (missing file, bad path), ``UnicodeDecodeError`` (wrong
    encoding), and ``csv.Error`` (malformed quoting) at the codec boundary so no raw
    third-party exception escapes into core/runner.
    """

    _declared_title = "CSV read error"


class CsvFlatnessError(CsvError):
    """Raised when a concept used with CSV is not flat.

    A CSV row concept must have scalar fields only (``text``/``integer``/``number``/
    ``boolean``/``date`` plus optionals and ``Literal``/choice-constrained scalars).
    A nested/list/dict/concept-typed/``Union``/``Any`` field is rejected, naming the
    offending field and telling the author to project to a flat concept first.
    """

    _declared_title = "CSV flatness error"


class CsvColumnError(CsvError):
    """Raised when CSV headers do not line up with the row concept's fields.

    Covers an unexpected extra column, a missing required column, and duplicate or
    blank header cells. A missing *optional* column is NOT an error (the field is set
    to ``None`` for all rows).
    """

    _declared_title = "CSV column error"


class CsvCoercionError(CsvError):
    """Raised when a CSV cell value cannot be coerced to its declared field type.

    Carries the 1-based row/column, the concept, and the field so the author can find
    the offending cell.
    """

    _declared_title = "CSV coercion error"
