"""Documentation-only models and shared `responses=` declarations for the API's problem documents.

Every failure this server emits is an `application/problem+json` document built
by the global handlers in `pipelex_api.exception_handlers` — the problem of a
pipelex error (`PipelexError.to_problem`, in the view of the request's reader)
or the document of an API-authored `ApiError`
(`build_problem_document_from_api_error`). The models here exist **only** so the
committed OpenAPI artifact can publish that shape with a real schema instead of
an untyped `additionalProperties: true` blob — nothing in the request path
imports them, and adding a field here does not change a single response byte.
Keep them in step with `docs/api-server/error-responses.md`, which is the prose contract.

The members of a pipelex error's problem reuse the problem's own models (its next
step, parameters, location, items and diagnostics), so the shapes published here
are the ones the problem is validated with.

The response dicts below are attached two ways:

- `COMMON_PROBLEM_RESPONSES` goes on the composite router in `pipelex_api.routes`, so
  every auth-wrapped `/v1` operation documents the four failures any of them can
  produce. Declaring a `422` there also suppresses FastAPI's automatic
  `HTTPValidationError` response, which advertised the wrong media type and the
  wrong schema on nearly every route.
- The single-status constants go on the routes that can additionally produce
  them (`responses=` on the decorator merges over the router-level set).

The media type is NOT set here. FastAPI renders a `responses` entry's `model`
under the route's own response-class media type (`application/json`), with no
per-response override; `PipelexFastAPI.openapi()` in `pipelex_api.openapi_schema`
re-keys every 4xx/5xx response onto `application/problem+json` (via
`use_problem_json_media_type`) after the schema is generated.
"""

from typing import Any

from mthds.protocol.problem.models import NextStep, ProblemItem, ProblemLocation, ProblemParams
from pipelex.errors.problem import ProblemDiagnostics
from pydantic import BaseModel, ConfigDict, Field


class ProblemDocument(BaseModel):
    """An RFC 9457 `application/problem+json` error body — the shape of every failure response.

    A pipelex error answers its problem document: the RFC's members (`type`, `title`, `status`, `detail`), the MTHDS
    core's (`code`, `domain`, `retry`, `next_step`, always present, and `retry_after`, `params`, `location`, `errors`,
    `pipeline_run_id` when they hold a value) and Pipelex's (`request_id`, and `diagnostics` in the operator view
    alone). An API-authored error carries no `code` yet, and is classified by `error_type`, `error_domain` and
    `retryable` instead, with its request path as `instance`. No member is ever written as `null`: a member with no
    value is absent. `extra="allow"` mirrors RFC 9457's open-ended extension-member rule.
    """

    model_config = ConfigDict(extra="allow")

    type: str = Field(
        ...,
        description=(
            "Stable URI of the error's documentation page: the page of its `code` (`https://mthds.ai/errors/<code>` for a core code, "
            "`https://docs.pipelex.com/errors/<code>` for a Pipelex code), or `https://docs.pipelex.com/latest/errors/<kebab-error-type>/` "
            "for an API-authored error, which carries no `code` yet."
        ),
    )
    title: str = Field(
        ..., description="Short, human-readable summary: the title of the error's `code`, or of its `error_type` when it carries none."
    )
    status: int = Field(..., description="HTTP status code, repeated in the body per RFC 9457: the status its `code` declares.")
    detail: str = Field(
        ...,
        description=(
            "Human-readable explanation of this specific failure, rendered from its code's template and parameters. "
            "Never parsed: a program branches on `code`."
        ),
    )
    code: str | None = Field(
        default=None,
        description=(
            "Registry code of the error, what a client branches on: a core code of the MTHDS standard (e.g. `request.invalid`) "
            "or a Pipelex code (e.g. `pipelex.config.invalid`). Present on every error the runtime raises; absent on an "
            "API-authored error."
        ),
    )
    domain: str | None = Field(default=None, description="Who must act, the code's domain: `input`, `method`, `account`, `operator` or `runtime`.")
    retry: str | None = Field(
        default=None, description="Whether repeating the request can succeed, the code's verdict: `yes`, `no` or `outcome_unknown`."
    )
    retry_after: float | None = Field(default=None, description="Seconds to wait before a retry, when known, on a code whose verdict is `yes`.")
    next_step: NextStep | None = Field(
        default=None,
        description="What the reader should do next: a kind and a sentence, aimed at the caller, or at the operator in the operator view.",
    )
    params: ProblemParams | None = Field(default=None, description="The code's typed parameters, the ones its templates are rendered with.")
    location: ProblemLocation | None = Field(
        default=None, description="Where the failure happened: the failing pipe and its path from the entry pipe, an input, a field, a file."
    )
    errors: list[ProblemItem] | None = Field(
        default=None,
        description=(
            "One item per fault, for a refusal with several, such as a method that does not validate. "
            "On `/validate`, `/resolve`, `/codegen` and `/pipe-io` an invalid bundle is a **200** verdict instead."
        ),
    )
    pipeline_run_id: str | None = Field(default=None, description="The run the failure belongs to.")
    request_id: str | None = Field(default=None, description="Correlation id, echoed in the `X-Request-ID` response header.")
    diagnostics: ProblemDiagnostics | None = Field(
        default=None,
        description=(
            "What only the operator reads: the error's class and message, its causes, the provider's answer, the model. "
            "Present only when the request was authenticated as the operator's (`AUTH_MODE=api_key`, or a trusted proxy)."
        ),
    )
    instance: str | None = Field(default=None, description="Path of the request that failed, on an API-authored error.")
    error_type: str | None = Field(default=None, description="Stable name of an API-authored error (e.g. `Unauthenticated`).")
    error_domain: str | None = Field(
        default=None,
        description="On an API-authored error: `input` (caller can fix it → 4xx) or `config` (deployment must fix it → 5xx).",
    )
    retryable: bool | None = Field(default=None, description="On an API-authored error: whether retrying the same request can plausibly succeed.")


def _problem(description: str, *, headers: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build one `responses=` entry documenting a `ProblemDocument` failure.

    `model` registers `ProblemDocument` in the artifact's components and emits a
    `$ref` to it; `PipelexFastAPI.openapi()` (`pipelex_api.openapi_schema`) then moves
    the schema onto the `application/problem+json` media type.
    """
    response: dict[str, Any] = {"description": description, "model": ProblemDocument}
    if headers is not None:
        response["headers"] = headers
    return response


PROBLEM_400_START_REQUIRES_ASYNC: dict[str, Any] = _problem(
    "`StartRequiresAsyncOrchestration` — this deployment's orchestrator is blocking-only and cannot honor "
    "fire-and-forget delivery. Use `POST /execute` instead.",
)

PROBLEM_401: dict[str, Any] = _problem(
    "Missing or invalid bearer token. Only reachable when the deployment enables auth (`AUTH_MODE=api_key` or `AUTH_MODE=jwt`).",
    headers={
        "WWW-Authenticate": {
            "description": "Authentication challenge — always `Bearer`.",
            "schema": {"type": "string"},
        }
    },
)

PROBLEM_403_RUN_POLICY: dict[str, Any] = _problem(
    "A deployment-policy refusal: `OrchestrationModeOverrideForbidden` — the request asked for an "
    "`orchestration_mode` this deployment does not allow overriding per request "
    "(`allow_request_orchestration_mode_override = false`); `CustomCodeRequiresSandbox` — the method (a bundle, or a "
    "fetched `method_ref` package) ships custom Python and this deployment is not sandbox-hosted; or "
    "`ReadScopeForbidden` — on a `jwt` deployment, the request sent a `read_scope` that does not lie under the caller's "
    "own `user_id`. The refusal of a method whose Python declares structure classes, "
    "`pipelex.deployment.python_structures_refused`, is a 422 instead, since the method's author changes it.",
)

PROBLEM_403_METHOD_PYTHON_POLICY: dict[str, Any] = _problem(
    "The run routes' Python policy, applied to the method's tree: `CustomCodeRequiresSandbox` — the method (sent in "
    "`files`, or a fetched `method_ref` package) ships custom Python and this deployment is not sandbox-hosted. "
    "Also `ReadScopeForbidden` — on a `jwt` deployment, the request sent a `read_scope` that does not lie under the "
    "caller's own `user_id`. The refusal of a method whose Python declares structure classes, "
    "`pipelex.deployment.python_structures_refused`, is a 422 instead, since the method's author changes it.",
)

PROBLEM_403_READ_SCOPE: dict[str, Any] = _problem(
    "`ReadScopeForbidden` — on a `jwt` deployment, the request sent a `read_scope` that does not lie under the caller's "
    "own `user_id`, the only scope its token may read.",
)

PROBLEM_409_DUPLICATE_RUN: dict[str, Any] = _problem(
    "`pipelex.run.already_exists` — the submitted `pipeline_run_id` is still registered for an in-flight run. "
    "Completed and failed runs free their id, so this only fires for genuinely concurrent duplicates.",
)

PROBLEM_413: dict[str, Any] = _problem(
    "Request body exceeds the deployment's size limit (`MAX_REQUEST_BODY_MIB`, 100 MiB by default).",
)

PROBLEM_422: dict[str, Any] = _problem(
    "The request could not be processed: a malformed body, a field failing validation, or a pipelex error whose code "
    "the caller fixes (a `.mthds` bundle that does not validate, a missing input). Note that on the diagnostic routes "
    "an *invalid bundle* is a **200** verdict, not a 422 — see each route's response contract.",
)

PROBLEM_429: dict[str, Any] = _problem(
    "An upstream inference provider rate-limited the run. Passed through from the provider; `Retry-After` is set when the provider supplied a hint.",
    headers={
        "Retry-After": {
            "description": "Seconds to wait before retrying, when the upstream provider supplied a hint.",
            "schema": {"type": "integer"},
        }
    },
)

PROBLEM_500: dict[str, Any] = _problem(
    "A failure the caller cannot fix (a missing env var, a bad TOML override, a backend fault), or an unexpected "
    "error answered as `runtime.unexpected`. Report the `request_id`.",
)

PROBLEM_501_ASYNC_NOT_ENABLED: dict[str, Any] = _problem(
    "`runtime.unsupported` — this deployment does not provide async pipeline execution. Permanent under the current deployment; do not retry.",
)

PROBLEM_404_METHOD_PACKAGE: dict[str, Any] = _problem(
    "`method.not_found` — the `method_ref` repository was fetched, but no package in it matches the requested address by manifest identity.",
)

PROBLEM_403_BLOB_UPLOAD: dict[str, Any] = _problem(
    "`BlobUploadNotAuthorized` — the upload does not carry the signed query an upload target of `POST /v1/blobs/missing` "
    "names, its signature does not hold for this hash and scope, or it has expired. Ask `POST /v1/blobs/missing` again "
    "for a fresh target.",
)

PROBLEM_501_METHOD_REF: dict[str, Any] = _problem(
    "`MethodRefNotSupported` — the request selected its method by a **registry-form** `method_ref` (not a "
    "`github.com/...` address), and no server-side method registry resolves those yet. Use an address-form reference "
    "or send the method's tree in `files` instead.",
)


# Attached to the composite `/v1` router (`pipelex_api.routes`), so every auth-wrapped operation documents
# the failures any of them can produce: the router-level auth check (401), the body-size middleware
# (413), request-shape and input-domain rejections (422), and the server-fault floor (500). Declaring
# the 422 here is also what suppresses FastAPI's automatic `HTTPValidationError` response.
COMMON_PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: PROBLEM_401,
    413: PROBLEM_413,
    422: PROBLEM_422,
    500: PROBLEM_500,
}
