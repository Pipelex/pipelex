"""Documentation-only models and shared `responses=` declarations for the API's problem documents.

Every failure this server emits is an `application/problem+json` document built
by the global handlers in `pipelex_api.exception_handlers`: the problem of a
pipelex error (`PipelexError.to_problem`, in the view of the request's reader),
the runner's own refusals included, which it raises as the classes of
`pipelex_api.exceptions`. Every document carries a registry `code`. The models
here exist **only** so the committed OpenAPI artifact can publish that shape with
a real schema instead of an untyped `additionalProperties: true` blob — nothing in
the request path imports them, and adding a field here does not change a single
response byte. Keep them in step with `docs/api-server/error-responses.md`, which
is the prose contract.

The members of a problem reuse the problem's own models (its next step,
parameters, location, items and diagnostics), so the shapes published here are
the ones the problem is validated with.

The response dicts below are attached two ways:

- `COMMON_PROBLEM_RESPONSES` goes on the composite router in `pipelex_api.routes`, so
  every auth-wrapped `/v1` operation documents the four failures any of them can
  produce. Declaring a `422` there also suppresses FastAPI's automatic
  `HTTPValidationError` response, which advertised the wrong media type and the
  wrong schema on nearly every route.
- The single-status constants go on the routes that can additionally produce
  them (`responses=` on the decorator merges over the router-level set).

A path no route serves (404 `request.not_found`) and a method a route does not
accept (405 `request.method_not_allowed`) answer the same document, but belong to
no operation, so no operation declares them.

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

    Every failure answers its problem document: the RFC's members (`type`, `title`, `status`, `detail`), the MTHDS
    core's (`code`, `domain`, `retry`, `next_step`, always present, and `retry_after`, `params`, `location`, `errors`,
    `pipeline_run_id` when they hold a value) and Pipelex's (`request_id`, always present on a response of this server,
    and `diagnostics` in the operator view alone). No member is ever written as `null`: a member with no value is
    absent. `extra="allow"` mirrors RFC 9457's open-ended extension-member rule.
    """

    model_config = ConfigDict(extra="allow")

    type: str = Field(
        ...,
        description=(
            "Stable URI of the documentation page of the error's `code`: `https://mthds.ai/errors/<code>` for a core code, "
            "`https://docs.pipelex.com/errors/<code>` for a Pipelex code."
        ),
    )
    title: str = Field(..., description="Short, human-readable summary: the title of the error's `code`.")
    status: int = Field(..., description="HTTP status code, repeated in the body per RFC 9457: the status its `code` declares.")
    detail: str = Field(
        ...,
        description=(
            "Human-readable explanation of this specific failure, rendered from its code's template and parameters. "
            "Never parsed: a program branches on `code`."
        ),
    )
    code: str = Field(
        ...,
        description=(
            "Registry code of the error, what a client branches on: a core code of the MTHDS standard (e.g. `request.invalid`) "
            "or a Pipelex code (e.g. `pipelex.config.invalid`)."
        ),
    )
    domain: str = Field(..., description="Who must act, the code's domain: `input`, `method`, `account`, `operator` or `runtime`.")
    retry: str = Field(..., description="Whether repeating the request can succeed, the code's verdict: `yes`, `no` or `outcome_unknown`.")
    retry_after: float | None = Field(default=None, description="Seconds to wait before a retry, when known, on a code whose verdict is `yes`.")
    next_step: NextStep = Field(
        ...,
        description="What the reader should do next: a kind and a sentence, aimed at the caller, or at the operator in the operator view.",
    )
    params: ProblemParams | None = Field(default=None, description="The code's typed parameters, the ones its templates are rendered with.")
    location: ProblemLocation | None = Field(
        default=None, description="Where the failure happened: the failing pipe and its path from the entry pipe, an input, a field, a file."
    )
    errors: list[ProblemItem] | None = Field(
        default=None,
        description=(
            "One item per fault, for a refusal with several, such as a request whose fields the route refuses. "
            "On `/validate`, `/resolve`, `/codegen` and `/pipe-io` an invalid bundle is a **200** verdict instead, "
            "whose `errors` are items of this same shape."
        ),
    )
    pipeline_run_id: str | None = Field(default=None, description="The run the failure belongs to.")
    request_id: str | None = Field(
        default=None,
        description="Correlation id, echoed in the `X-Request-ID` response header: the caller's own when valid, else one the runner mints.",
    )
    diagnostics: ProblemDiagnostics | None = Field(
        default=None,
        description=(
            "What only the operator reads: the error's class and message, its causes, the provider's answer, the model. "
            "Present only when the request was authenticated as the operator's (`AUTH_MODE=api_key`, or a trusted proxy)."
        ),
    )


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


PROBLEM_401: dict[str, Any] = _problem(
    "`auth.missing_credential`, `auth.invalid_credential` or `auth.credential_expired` — a missing, refused or expired "
    "bearer token. Only reachable when the deployment enables auth (`AUTH_MODE=api_key` or `AUTH_MODE=jwt`), or trusts a "
    "proxy's forwarded identity and the proxy forwarded none or one that is not path-safe.",
    headers={
        "WWW-Authenticate": {
            "description": "Authentication challenge — always `Bearer`.",
            "schema": {"type": "string"},
        }
    },
)

PROBLEM_409_DUPLICATE_RUN: dict[str, Any] = _problem(
    "`pipelex.run.already_exists` — the submitted `pipeline_run_id` is still registered for an in-flight run. "
    "Completed and failed runs free their id, so this only fires for genuinely concurrent duplicates.",
)

PROBLEM_413: dict[str, Any] = _problem(
    "`request.too_large` — the request, or a part of it such as a file it sends, exceeds one of the deployment's byte "
    "limits (`MAX_REQUEST_BODY_MIB`, 100 MiB by default, for the body). `params.limit` and `params.size` give both in bytes.",
)

PROBLEM_422: dict[str, Any] = _problem(
    "The request could not be processed: a body that does not parse (`request.malformed`), fields the route refuses "
    "(`request.invalid`, one item in `errors` per refused field), a security rule's refusal (such as "
    "`pipelex.security.reserved_key` or `security.input_url_refused`), a method tree the runner cannot read "
    "(`method.package_invalid`), or a pipelex error whose code the caller fixes (a `.mthds` bundle that does not "
    "validate, a missing input). Note that on the diagnostic routes an *invalid bundle* is a **200** verdict, not a "
    "422 — see each route's response contract.",
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
    "A failure the caller cannot fix: the runner's own configuration (`runtime.misconfigured`, such as a missing env "
    "var), a bad TOML override, a backend fault, or an unexpected error answered as `runtime.unexpected`. Report the "
    "`request_id`.",
)

PROBLEM_501_RUN_POLICY: dict[str, Any] = _problem(
    "`pipelex.deployment.custom_code_requires_sandbox` — the method (a bundle, or a fetched `method_ref` package, as "
    "`params.origin` says) ships custom Python and this deployment is not sandbox-hosted. The refusal of a method whose "
    "Python declares structure classes, `pipelex.deployment.python_structures_refused`, is a 422 instead, since the "
    "method's author changes it.",
)

PROBLEM_501_START: dict[str, Any] = _problem(
    "`runtime.unsupported` — this deployment cannot honor fire-and-forget delivery: its orchestrator is blocking-only, or "
    "its async execution is not enabled. Permanent under the current deployment; use `POST /execute` instead. Or "
    "`pipelex.deployment.custom_code_requires_sandbox`, as on `POST /execute`.",
)

PROBLEM_404_METHOD_PACKAGE: dict[str, Any] = _problem(
    "`method.not_found` — the `method_ref` repository was fetched, but no package in it matches the requested address by manifest identity.",
)

PROBLEM_403_BLOB_UPLOAD: dict[str, Any] = _problem(
    "`auth.forbidden`, whose `params.requirement` is `signed_upload_target` — the upload does not carry the signed query "
    "an upload target of `POST /v1/blobs/missing` names, its signature does not hold for this hash and scope, or it has "
    "expired. Ask `POST /v1/blobs/missing` again for a fresh target.",
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
