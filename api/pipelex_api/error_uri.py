"""RFC 7807 `type` URI and `title` for API-authored errors.

A pipelex `ErrorReport` always carries its own `type_uri` and `title`, both
required fields and both the registry code's (`ErrorReport.make_for_code`): the
code's documentation page and the code's title. The global exception handler
never needs these helpers for a `PipelexError`.

They exist for the *other* error source: the API's own 4xx responses
(`raise_validation_error` and friends in `pipelex_api.errors`), authored from the
static `pipelex_api.error_types.ErrorType` enum with no `ErrorReport` behind them.
`build_problem_document_from_api_error` uses these to give an API-authored
error an RFC 7807 `type` / `title` pair. Unlike a pipelex error's, that pair
is still derived from a class name (`URLs.error_docs_base`, `pascal_case_to_kebab`,
`pascal_case_to_sentence`) until every API-authored raise carries its own
registry code. Both functions are pure.
"""

from pipelex.tools.misc.string_utils import pascal_case_to_kebab, pascal_case_to_sentence
from pipelex.urls import URLs


def error_type_uri(error_type: str) -> str:
    """Return the RFC 7807 `type` URI for an error type name.

    `ValidationError` -> `https://docs.pipelex.com/latest/errors/validation-error/`.
    The URI is derived from the class name, trailing slash included. No page
    lives at it: the per-class error pages are retired, and the docs site's 404
    page sends such a URI to the Error Codes index. The type URI stays
    class-derived until every API-authored raise carries its code from the error
    registry, whose type URI names the code's page, as a pipelex error's already does.
    """
    return f"{URLs.error_docs_base}/{pascal_case_to_kebab(error_type)}/"


def error_type_title(error_type: str) -> str:
    """Return a human-readable RFC 7807 `title` for an error type name.

    `ValidationError` -> `Validation error`; `BadRequest` -> `Bad request`.
    Sentence case via `pascal_case_to_sentence`. It does NOT strip a trailing
    `Error`: an API `ErrorType` such as `ValidationError` must keep the suffix —
    `"Validation"` alone would be a worse label than `"Validation error"`.
    """
    return pascal_case_to_sentence(error_type)
