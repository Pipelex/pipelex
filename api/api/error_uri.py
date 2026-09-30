"""RFC 7807 `type` URI and `title` for API-authored errors.

A pipelex `ErrorReport` always carries its own `type_uri` and `title` (set
upstream by `PipelexError.type_uri()` / `PipelexError.title()`, both required
fields), so the global exception handler never needs these helpers for a
`PipelexError`.

They exist for the *other* error source: the API's own 4xx responses
(`raise_validation_error` and friends in `api.errors`), authored from the
static `api.error_types.ErrorType` enum with no `ErrorReport` behind them.
`build_problem_document_from_api_error` uses these to give an API-authored
error the same RFC 7807 `type` / `title` shape as a pipelex one. They also
serve as a defensive backstop should a future pipelex ever hand back a report
with an absent identity pair.

The URI namespace and the kebab / humanize transforms are deliberately the
same ones pipelex uses (`URLs.error_docs_base`, `pascal_case_to_kebab`,
`pascal_case_to_sentence`), so an API-authored error and a pipelex error are
indistinguishable in shape on the wire. Both functions are pure.
"""

from pipelex.tools.misc.string_utils import pascal_case_to_kebab, pascal_case_to_sentence
from pipelex.urls import URLs


def error_type_uri(error_type: str) -> str:
    """Return the RFC 7807 `type` URI for an error type name.

    `EnvVarNotFoundError` -> `https://docs.pipelex.com/latest/errors/env-var-not-found-error/`.
    The trailing slash matches the canonical docs URL form, exactly as
    `PipelexError.type_uri()` produces it upstream.
    """
    return f"{URLs.error_docs_base}/{pascal_case_to_kebab(error_type)}/"


def error_type_title(error_type: str) -> str:
    """Return a human-readable RFC 7807 `title` for an error type name.

    `ValidationError` -> `Validation error`; `BadRequest` -> `Bad request`.
    Sentence case via the same `pascal_case_to_sentence` transform pipelex uses
    in `PipelexError.title()`. Unlike `PipelexError.title()` it does NOT strip a
    trailing `Error`: an API `ErrorType` such as `ValidationError` must keep the
    suffix — `"Validation"` alone would be a worse label than `"Validation error"`.
    """
    return pascal_case_to_sentence(error_type)
