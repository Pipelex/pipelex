"""The rendering of a problem document as the HTTP response that carries it.

A pure module: no logging and no request state of its own. Every failure the runner answers is a problem
(`pipelex.errors.problem.PipelexProblem`) built in the operator's view, and this module renders it as the response a
reader receives: the view of that reader, the status its code declares, and the headers the status calls for. The
global handlers in `pipelex_api.exception_handlers` log the failure and then render it here, and so does the body-size
middleware in `pipelex_api.middleware`, which answers before any handler runs. Keeping the rendering here lets both
share it while the handlers import the middleware's request-id reader, with no import cycle between them.
"""

import math

from fastapi.responses import JSONResponse
from pipelex.errors.error_codes import error_code_spec, parse_error_code
from pipelex.errors.problem import PipelexProblem, ProblemView, caller_view_of

# Content type for every error response, an RFC 9457 problem document. Lives here, the module that renders them, so the
# FastAPI app, the middleware and the error handlers all reference one constant.
PROBLEM_JSON_MEDIA_TYPE = "application/problem+json"

# The HTTP status of a problem whose code the registry gives none, which only a client's own failure has.
_FALLBACK_PROBLEM_STATUS = 500

# The challenge every 401 carries (RFC 9110, section 15.5.2): this runner authenticates with a bearer credential.
_BEARER_CHALLENGE = {"WWW-Authenticate": "Bearer"}


def problem_status(problem: PipelexProblem) -> int:
    """The HTTP status of the response a problem is the body of: its code's, from the error registry."""
    code = parse_error_code(problem.code)
    if code is None:
        return _FALLBACK_PROBLEM_STATUS
    return error_code_spec(code).status or _FALLBACK_PROBLEM_STATUS


def _retry_after_header(problem: PipelexProblem, *, status: int) -> dict[str, str]:
    """Return a `Retry-After` header dict when a retry hint applies to this response.

    Emitted only when the response is itself a retry invitation, a 429 such as a provider's rate limit passed through,
    so a hint never rides a 500 or a 422, where `Retry-After` is meaningless. The problem's `retry_after`, which only a
    code inviting a retry carries and which is always finite, is rounded up to an integer. Empty when no hint applies.
    """
    if status != 429:
        return {}
    seconds = problem.retry_after
    if seconds is None or not math.isfinite(seconds):
        return {}
    return {"Retry-After": str(max(0, math.ceil(seconds)))}


def problem_json_response(problem: PipelexProblem, *, view: ProblemView, headers: dict[str, str] | None = None) -> JSONResponse:
    """Render a problem built in the operator's view as the `application/problem+json` response a reader of `view` receives.

    The status is the one the problem's code declares, and the body's `status` member repeats it, as RFC 9457 asks. The
    caller's view leaves the operator's `diagnostics` out and aims the step at the caller. A 401 carries the bearer
    challenge, and a 429 the `Retry-After` its problem gives. `headers` are added to those, such as the `Allow` header of a
    405.

    Args:
        problem: The problem, in the operator's view.
        view: The view of whoever receives the response.
        headers: Further headers of the response.

    Returns:
        The response.
    """
    status = problem_status(problem)
    match view:
        case ProblemView.OPERATOR:
            reader_problem = problem
        case ProblemView.CALLER:
            reader_problem = caller_view_of(problem=problem)
    response_headers = {**(headers or {}), **_retry_after_header(problem, status=status)}
    if status == 401:
        response_headers.update(_BEARER_CHALLENGE)
    return JSONResponse(
        status_code=status,
        content=reader_problem.model_copy(update={"status": status}).to_wire(),
        media_type=PROBLEM_JSON_MEDIA_TYPE,
        headers=response_headers,
    )
