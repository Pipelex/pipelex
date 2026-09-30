"""RFC 7807 problem-document construction.

A pure module — no FastAPI imports, no I/O. It turns the two error sources of
the API into the single `application/problem+json` body shape clients see:

- `build_problem_document` — for a pipelex `ErrorReport`. Delegates to
  `ErrorReport.to_problem_document(...)`: pipelex owns the field mapping
  (standard RFC 7807 slots plus classification extension members) and the
  `disclosure_mode` redaction. The API only chooses the disclosure mode and
  supplies the request context.
- `build_problem_document_from_api_error` — for an API-authored 4xx that has
  no `ErrorReport` behind it (`raise_validation_error` and friends in
  `api.errors`). Built from the static `ErrorType` enum; always `INPUT` domain.

Both return a plain `dict` the caller serializes as `application/problem+json`.
"""

from typing import Any

from pipelex.base_exceptions import DisclosureMode, ErrorDomain, ErrorReport

from api.error_types import ErrorType
from api.error_uri import error_type_title, error_type_uri

# Content type for every error response — RFC 7807 problem documents. Lives
# here, the module that builds them, so the FastAPI app, the middleware, and
# the error handlers can all reference one constant without a circular import.
PROBLEM_JSON_MEDIA_TYPE = "application/problem+json"


def build_problem_document(
    report: ErrorReport,
    *,
    instance: str | None,
    request_id: str | None,
    disclosure_mode: DisclosureMode,
) -> dict[str, Any]:
    """Build an RFC 7807 problem document from a pipelex `ErrorReport`.

    Thin wrapper over `ErrorReport.to_problem_document(...)`: the field mapping
    and the `disclosure_mode` redaction both live upstream in pipelex. The
    API's only responsibility is to choose the disclosure mode and pass the
    request context through.
    """
    return report.to_problem_document(
        instance=instance,
        request_id=request_id,
        disclosure_mode=disclosure_mode,
    )


def build_problem_document_from_api_error(
    error_type: ErrorType,
    message: str,
    status: int,
    *,
    instance: str | None,
    request_id: str | None,
    error_domain: ErrorDomain | None = ErrorDomain.INPUT,
    retryable: bool = False,
) -> dict[str, Any]:
    """Build an RFC 7807 problem document for an API-authored error.

    Used by the `api.errors` 4xx/5xx helpers, whose failures are the API's own
    request validation, auth, or configuration checks rather than a pipelex
    domain error — there is no `ErrorReport` to delegate to. The `type` URI and
    `title` are derived from the static `ErrorType` enum the same way pipelex
    derives them for its own classes, so the standard RFC 7807 slots and the
    `error_type` / `error_domain` members line up with what a pipelex error
    renders.

    Extension-member parity with a pipelex `ErrorReport` is by-field, not
    wholesale, with two distinct rules:

    - `retryable` is emitted unconditionally here (every API-authored error is
      non-retryable; see below). pipelex emits it only when the source error
      populated it, so a non-inference pipelex report (`PipelexConfigError`,
      `EnvVarNotFoundError`) renders with no `retryable`. Asymmetric by design:
      the API knows the answer for every error it authors, and clients can
      drive retry logic uniformly without branching on field presence.
    - Classification fields pipelex sets only on classifiable failures
      (`error_category`, `user_action`, `model`, `provider`, `provider_metadata`)
      are NOT manufactured here. The same omission rule pipelex applies to its
      own non-inference reports (`PipelexConfigError`, `EnvVarNotFoundError`
      carry no `error_category` either) — surfacing a fake category for an
      API-authored validation or auth failure would lie about what the API
      actually classified.

    `error_domain` defaults to `INPUT` — the caller can fix a 4xx. API-owned
    5xx (a missing secret, a misconfigured backend) pass `CONFIG`: an operator,
    not the caller, fixes those. `None` omits the member entirely, matching how
    a domain-less pipelex error renders.

    `retryable` defaults to `False`: every error this builder authors is a
    caller-input mistake or a server misconfiguration, neither of which a blind
    retry fixes. Carried as a positional contract member rather than dropped on
    `None`, so clients can drive retry logic uniformly without branching on
    field presence.

    `None`-valued context (`instance`, `request_id`) is dropped rather than
    emitted as `null`, matching `ErrorReport.to_problem_document` semantics.
    """
    document: dict[str, Any] = {
        "type": error_type_uri(error_type),
        "title": error_type_title(error_type),
        "status": status,
        "detail": message,
    }
    if instance is not None:
        document["instance"] = instance
    if request_id is not None:
        document["request_id"] = request_id
    document["error_type"] = error_type
    if error_domain is not None:
        document["error_domain"] = error_domain
    document["retryable"] = retryable
    return document


def with_request_context(document: dict[str, Any], *, instance: str | None, request_id: str | None) -> dict[str, Any]:
    """Return a copy of a problem document carrying the two request-scoped members.

    The `api.errors` helpers build their document where no `Request` is in hand — a validation
    check deep inside a route, an auth refusal — so `instance` and `request_id` are stamped later,
    by the handler that renders the response and does hold the request. A copy rather than an
    in-place edit, because the `ApiError` a caller catches and inspects must read exactly as it was
    raised. `None` is dropped rather than emitted as `null`, the rule every builder here follows.
    """
    stamped = dict(document)
    if instance is not None:
        stamped["instance"] = instance
    if request_id is not None:
        stamped["request_id"] = request_id
    return stamped
