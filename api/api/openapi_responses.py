"""Documentation-only models and shared `responses=` declarations for the API's RFC 7807 errors.

Every failure this server emits is an `application/problem+json` document built
by the global handlers in `api.exception_handlers` — from a pipelex
`ErrorReport` (`build_problem_document`) or from an API-authored `ApiError`
(`build_problem_document_from_api_error`). Neither path validates through a
Pydantic model: they build plain dicts. The models here exist **only** so the
committed OpenAPI artifact can publish that shape with a real schema instead of
an untyped `additionalProperties: true` blob — nothing in the request path
imports them, and adding a field here does not change a single response byte.
Keep them in step with `docs/error-responses.md`, which is the prose contract.

`ProblemDocument.validation_errors` reuses pipelex's own `ValidationErrorItem`,
so the item shape published on the error wire is the same one `/validate`'s 200
invalid arm publishes — including `suggested_fix`, which rides along for free.

The response dicts below are attached two ways:

- `COMMON_PROBLEM_RESPONSES` goes on the composite router in `api.routes`, so
  every auth-wrapped `/v1` operation documents the four failures any of them can
  produce. Declaring a `422` there also suppresses FastAPI's automatic
  `HTTPValidationError` response, which advertised the wrong media type and the
  wrong schema on nearly every route.
- The single-status constants go on the routes that can additionally produce
  them (`responses=` on the decorator merges over the router-level set).

The media type is NOT set here. FastAPI renders a `responses` entry's `model`
under the route's own response-class media type (`application/json`), with no
per-response override; `PipelexFastAPI.openapi()` in `api.openapi_schema`
re-keys every 4xx/5xx response onto `application/problem+json` (via
`use_problem_json_media_type`) after the schema is generated.
"""

from typing import Any

from pipelex.base_exceptions import ValidationErrorItem
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserAction
from pydantic import BaseModel, ConfigDict, Field


class ProblemDocument(BaseModel):
    """An RFC 7807 `application/problem+json` error body — the shape of every failure response.

    Standard RFC 7807 members (`type`, `title`, `status`, `detail`, `instance`)
    plus the extension members pipelex's classification adds. Only `type`,
    `title`, `status`, `detail`, and `error_type` are always present: the rest
    ride along when the originating error populates them, so a consumer must
    treat them as optional. `extra="allow"` mirrors RFC 7807's open-ended
    extension-member rule.
    """

    model_config = ConfigDict(extra="allow")

    type: str = Field(..., description="Stable URI for the error class: `https://docs.pipelex.com/latest/errors/<kebab-class-name>/`.")
    title: str = Field(..., description="Short, human-readable summary of the error class.")
    status: int = Field(..., description="HTTP status code, repeated in the body per RFC 7807.")
    detail: str = Field(..., description="Human-readable explanation of this specific failure. Redacted under `ERROR_DISCLOSURE=strict`.")
    instance: str | None = Field(default=None, description="Path of the request that failed.")
    request_id: str | None = Field(default=None, description="Correlation id, echoed in the `X-Request-ID` response header.")
    error_type: str = Field(..., description="Stable class name of the originating error (e.g. `ValidateBundleError`, `Unauthenticated`).")
    error_domain: str | None = Field(
        default=None,
        description="`input` (caller can fix it → 422), `config` or `runtime` (deployment must fix it → 500). Absent for domain-less errors.",
    )
    retryable: bool | None = Field(
        default=None,
        description=(
            "Whether retrying the same request can plausibly succeed. Always present on API-authored errors; "
            "on pipelex errors only when the originating error classifies it."
        ),
    )
    error_category: str | None = Field(default=None, description="Finer classification, when the originating error provides one (inference errors).")
    user_action: UserAction | None = Field(default=None, description="Structured suggestion of what the caller should do next, when available.")
    model: str | None = Field(default=None, description="Inference model that failed. Stripped under `ERROR_DISCLOSURE=strict`.")
    provider: str | None = Field(default=None, description="Inference provider that failed. Stripped under `ERROR_DISCLOSURE=strict`.")
    provider_metadata: ProviderErrorMetadata | None = Field(
        default=None,
        description="Upstream provider error metadata. Stripped (bar a curated slice) under `ERROR_DISCLOSURE=strict`.",
    )
    validation_errors: list[ValidationErrorItem] | None = Field(
        default=None,
        description=(
            "Structured per-error diagnostics, carried by a `ValidateBundleError`. Each item may carry a `suggested_fix`. "
            "Retained under `ERROR_DISCLOSURE=strict` — it describes the caller's own bundle, not server internals. "
            "On `/validate`, `/resolve`, `/codegen` and `/build/*` an invalid bundle is a **200** verdict instead, so the "
            "items ride the response body there rather than a problem document."
        ),
    )


def _problem(description: str, *, headers: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build one `responses=` entry documenting a `ProblemDocument` failure.

    `model` registers `ProblemDocument` in the artifact's components and emits a
    `$ref` to it; `PipelexFastAPI.openapi()` (`api.openapi_schema`) then moves
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
    "`MethodStructuresRefusedError` — the method's Python declares structure classes (`StructuredContent` "
    "subclasses), whether it arrived as a bundle (`files` or `bundle_b64`) or as a fetched `method_ref` package: "
    "a sandbox-hosted deployment imports no caller Python into its own process, so it refuses them before "
    "loading anything (express the types as MTHDS concepts instead).",
)

PROBLEM_409_DUPLICATE_RUN: dict[str, Any] = _problem(
    "`PipelineManagerAlreadyExistsError` — the submitted `pipeline_run_id` is still registered for an in-flight run. "
    "Completed and failed runs free their id, so this only fires for genuinely concurrent duplicates.",
)

PROBLEM_413: dict[str, Any] = _problem(
    "Request body exceeds the deployment's size limit (`MAX_REQUEST_BODY_MIB`, 100 MiB by default).",
)

PROBLEM_422: dict[str, Any] = _problem(
    "The request could not be processed: a malformed body, a field failing validation, or an `input`-domain pipelex "
    "error (a `.mthds` bundle the caller must fix). Note that on the diagnostic routes an *invalid bundle* is a **200** "
    "verdict, not a 422 — see each route's response contract.",
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
    "A `config`-domain or `runtime`-domain failure the caller cannot fix (a missing env var, a bad TOML override, a "
    "backend fault), or an unclassified error sanitized by the catch-all handler. Report the `request_id`.",
)

PROBLEM_501_ASYNC_NOT_ENABLED: dict[str, Any] = _problem(
    "`AsyncExecutionNotEnabledError` — this deployment does not provide async pipeline execution. Permanent under the "
    "current deployment; do not retry.",
)

PROBLEM_404_METHOD_PACKAGE: dict[str, Any] = _problem(
    "`MethodPackageNotFoundError` — the `method_ref` repository was fetched, but no package in it matches the "
    "requested address by manifest identity. The message lists the packages the repository does contain.",
)

PROBLEM_501_METHOD_REF: dict[str, Any] = _problem(
    "`MethodRefNotSupported` — the request selected its closure by a **registry-form** `method_ref` (not a "
    "`github.com/...` address), and no server-side method registry resolves those yet. Use an address-form reference "
    "or submit inline `files[]` instead.",
)


# Attached to the composite `/v1` router (`api.routes`), so every auth-wrapped operation documents
# the failures any of them can produce: the router-level auth check (401), the body-size middleware
# (413), request-shape and input-domain rejections (422), and the server-fault floor (500). Declaring
# the 422 here is also what suppresses FastAPI's automatic `HTTPValidationError` response.
COMMON_PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: PROBLEM_401,
    413: PROBLEM_413,
    422: PROBLEM_422,
    500: PROBLEM_500,
}
