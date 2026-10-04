"""Shared request/response models for API routes.

These are API-server-only models. As of the MTHDS Protocol unification the
protocol itself defines no request model (the SDK runners take the basic args
as named parameters), so a server that wants a typed request body — like this
one — owns it. `RunRequest` / `StartRequest` are defined here, not imported.
"""

from __future__ import annotations

from ipaddress import ip_address
from typing import Annotated, Any, Self
from urllib.parse import urlparse

from mthds.protocol.exceptions import PipelineRequestError
from mthds.protocol.pipe_output import VariableMultiplicity
from mthds.protocol.pipeline_inputs import PipelineInputs
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.methods.fetching import MethodProvenance
from pipelex.pipeline.pipeline_response import PipelexRunResultExecute, PipelexRunResultStart
from pipelex.reporting.usage_records import TokensUsageRecord
from pipelex.system.run_extras import validate_run_extras
from pipelex.system.storage_scope import validate_read_scope, validate_storage_scope
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.functional_validators import SkipValidation

from pipelex_api.limits import (
    MAX_CALLBACK_URL_LEN,
    MAX_CALLBACK_URLS,
    MAX_METHOD_REF_LEN,
    MAX_MTHDS_FILE_BYTES,
    MAX_MTHDS_FILES_PER_REQUEST,
    MAX_PIPE_CODE_LEN,
)


def _ensure_mthds_file_within_bytes_limit(content: str) -> None:
    """Enforce the per-file size bound shared by every route that accepts inline MTHDS content."""
    if len(content.encode("utf-8")) > MAX_MTHDS_FILE_BYTES:
        msg = f"MTHDS file exceeds {MAX_MTHDS_FILE_BYTES // 1024} KiB limit"
        raise ValueError(msg)


class RunRequest(BaseModel):
    """Body of `POST /execute` — this server's typed request model.

    The MTHDS Protocol has no request model (`mthds` deleted `RunRequest`: the
    request body is just the basic args the runner already takes as named
    parameters). pipelex-api keeps a typed model so it can publish the request
    schema in its OpenAPI artifact and parse the body once.

    The declared fields are the protocol's **basic** arguments. The model is
    deliberately open (`extra="allow"`): a caller may send extra request
    properties, and they are kept rather than silently dropped. Openness is not
    a waiver, though — an unknown key never satisfies the run-source
    precondition. Under the layered extension policy (the Pipelex workspace
    spec `docs/specs/pipelex-platform-api.md` → "Layered extension policy"), an
    extension-borne method selector is resolved by the layer that owns it
    BEFORE the request reaches this one, so a body arriving here with no source
    this server understands is an error whatever else it carries.

    Attributes:
        pipe_code: Code of the pipe to execute.
        mthds_contents: List of MTHDS bundle contents to load.
        inputs: Inputs in PipelineInputs format, as plain JSON — Pydantic validation is
            skipped to preserve the flexible format (strings, lists, objects); the runtime
            shapes each value against the entry pipe's declared input.
        output_name: Name of the output slot to write to.
        output_multiplicity: Output multiplicity setting.
        dynamic_output_concept_ref: Override for the dynamic output concept ref.
        bundle_b64: PIPELEX-API EXTENSION — base64-encoded zip of the whole method
            bundle (`.mthds` + `.py` + `structures/*.py` + `requirements.txt`). Lets a
            caller ship custom PipeFunc Python alongside the method; materialized into a
            temporary library directory before the run. Mutually exclusive with `files`.
        files: PIPELEX-API EXTENSION — the bundle as a `{relative_path: text}` map (the
            unzipped equivalent of `bundle_b64`). Mutually exclusive with `bundle_b64`.
        method_ref: PIPELEX-API EXTENSION — run a published method by address instead of
            inline source. Resolved by THIS runner (git fetch at the tag, package located
            by manifest identity); mutually exclusive with `mthds_contents` and with a
            method bundle. `pipe_code` may accompany it to override the manifest's
            `main_pipe`.
    """

    model_config = ConfigDict(extra="allow")

    pipe_code: str | None = None
    mthds_contents: list[str] | None = None
    inputs: Annotated[PipelineInputs | None, SkipValidation] = None
    output_name: str | None = None
    output_multiplicity: VariableMultiplicity | None = None
    dynamic_output_concept_ref: str | None = None
    bundle_b64: str | None = Field(
        default=None,
        description=(
            "PIPELEX-API EXTENSION (not part of the MTHDS Protocol) — base64-encoded zip of the whole "
            "method bundle (`.mthds` + `.py` + `structures/*.py` + `requirements.txt`), materialized into a "
            "temporary library directory before the run so custom PipeFunc Python travels with the method. "
            "Mutually exclusive with `files`. Custom `.py` is only honored on a sandbox-hosted deployment."
        ),
    )
    files: dict[str, str] | None = Field(
        default=None,
        description=(
            "PIPELEX-API EXTENSION (not part of the MTHDS Protocol) — the method bundle as a "
            "`{relative_path: text}` map (the unzipped equivalent of `bundle_b64`). Mutually exclusive with `bundle_b64`."
        ),
    )
    method_ref: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_METHOD_REF_LEN,
        description=(
            "PIPELEX-API EXTENSION (not part of the MTHDS Protocol) — run a published method by reference instead of "
            "inline source. Address form: `github.com/<owner>/<repo>[/<selector>][@<tag>]` (e.g. "
            "`github.com/Pipelex/methods/documents@v0.1.0`) — resolved by THIS runner: the repository is fetched at the "
            "tag (a bare address means the default branch at HEAD), the package is located by manifest identity, and "
            "the resolved commit SHA is recorded as `method_provenance` on the response. Mutually exclusive with "
            "`mthds_contents` and with a method bundle (`bundle_b64` / `files`); `pipe_code` may accompany it to "
            "override the manifest's `main_pipe`. A package shipping custom Python is only honored on a sandbox-hosted "
            "deployment, and a package declaring Python structure classes is always refused — hosted execution accepts "
            "MTHDS concepts and sandboxed PipeFuncs, not in-process Python."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def validate_request(cls, values: dict[str, Any]) -> dict[str, Any]:
        # The protocol requires at least one of pipe_code / mthds_contents. A method bundle
        # (`bundle_b64` / `files`) carries its own `.mthds` — so it satisfies the precondition
        # on its own (the pipe to run comes from the bundle's `main_pipe`). Extension args carry
        # NO waiver: see the class docstring and `_refuse_source_less_extension_body`, which
        # authors the better message for that case where the raw body is still in hand.
        has_bundle = values.get("bundle_b64") is not None or values.get("files") is not None
        has_method_ref = values.get("method_ref") is not None
        # A bundle carries its own `.mthds`; combining it with inline `mthds_contents` would load
        # both into one library with no dedup, so a shared domain collides deep in the run with an
        # opaque duplicate-domain error. Refuse the combination up front (a bundle + `pipe_code` — to
        # pick which pipe in the bundle to run — is still fine).
        if has_bundle and values.get("mthds_contents"):
            msg = "A method bundle (bundle_b64 / files) and inline mthds_contents are mutually exclusive; send one or the other."
            raise PipelineRequestError(msg)
        # `method_ref` is a complete run source of its own (the fetched package carries its
        # `.mthds` and its entry pipe): exactly one source per request, so it excludes both
        # inline contents and a bundle. `pipe_code` beside it is fine — it overrides the
        # manifest's `main_pipe` to pick which pipe in the fetched package to run.
        if has_method_ref and values.get("mthds_contents"):
            msg = "method_ref and inline mthds_contents are mutually exclusive; send one or the other."
            raise PipelineRequestError(msg)
        if has_method_ref and has_bundle:
            msg = "method_ref and a method bundle (bundle_b64 / files) are mutually exclusive; send one or the other."
            raise PipelineRequestError(msg)
        if values.get("pipe_code") is None and not values.get("mthds_contents") and not has_bundle and not has_method_ref:
            msg = (
                "pipe_code and mthds_contents cannot both be empty. Either: both are provided, or if there are no mthds_contents, "
                "then pipe_code must be provided and must reference a pipe already registered in the library. "
                "If mthds_contents is provided but no pipe_code, the first content must have a main_pipe property."
            )
            raise PipelineRequestError(msg)
        return values

    @classmethod
    def _refuse_source_less_extension_body(cls, *, request_body: dict[str, Any], mthds_contents: list[str] | None) -> None:
        """Diagnose "a hosted client was pointed at this runner" before the generic precondition fires.

        This lives here, and not in `validate_request`, because only the RAW body still
        holds the keys the message needs to name: the model copies the declared fields
        only, so by the time the validator runs the unknown keys are already gone.

        Fires only when the body carries NO run source this server understands AND at
        least one key it does not handle. A source-less body whose every key IS handled
        falls through to `validate_request`'s base guidance — there is no extension to
        name there. Wording stays deployment-neutral: the runner does not know whether
        it is hosted, so it reports what it handles, never what the caller "should have"
        deployed.

        Precedence: `_parse_request` validates `PipelineApiExtras` before calling
        `from_body`, so a body that is BOTH source-less and carries a malformed handled
        extra (a non-http(s) `callback_urls` entry, say) gets the extras 422 and never
        reaches this diagnostic. That ordering is deliberate — both are caller mistakes
        answered with the same status and error domain, and demoting a concrete malformed
        value to surface a second message would be the worse trade. The naming guarantee
        therefore covers the single-fault case.
        """
        has_bundle = request_body.get("bundle_b64") is not None or request_body.get("files") is not None
        if request_body.get("pipe_code") is not None or mthds_contents or has_bundle or request_body.get("method_ref") is not None:
            return
        # `PipelineApiExtras` is defined below in this module — resolved at call time, which is
        # always after import. Its fields are the API-server-only keys the routes DO handle —
        # `_validate_extras` validates the body against this very model — so naming one of them
        # as "not handled" would be a lie.
        handled_keys = set(cls.model_fields) | set(PipelineApiExtras.model_fields) | {"mthds_content"}
        unhandled_keys = sorted(key for key in request_body if key not in handled_keys)
        if not unhandled_keys:
            return
        named = ", ".join(f"`{key}`" for key in unhandled_keys)
        msg = (
            "This request carries no run source this server understands (pipe_code, mthds_contents, "
            f"or a method bundle). The extension args it does carry ({named}) are not handled by this "
            "deployment — a hosted-only selector such as `method_id` must be sent to the hosted API, "
            "which resolves it into a run source before any runner sees the request."
        )
        raise PipelineRequestError(msg)

    @classmethod
    def from_body(cls, request_body: dict[str, Any]) -> RunRequest:
        """Build a RunRequest from the raw request-body dictionary.

        Supports both the singular `mthds_content` (legacy) and plural
        `mthds_contents`. `inputs` defaults to `{}` so a body that omits it
        still parses.
        """
        mthds_contents = request_body.get("mthds_contents")
        if mthds_contents is None:
            mthds_content = request_body.get("mthds_content")
            if mthds_content is not None:
                mthds_contents = [mthds_content]
        cls._refuse_source_less_extension_body(request_body=request_body, mthds_contents=mthds_contents)
        return cls(
            pipe_code=request_body.get("pipe_code"),
            mthds_contents=mthds_contents,
            inputs=request_body.get("inputs", {}),
            output_name=request_body.get("output_name"),
            output_multiplicity=request_body.get("output_multiplicity"),
            dynamic_output_concept_ref=request_body.get("dynamic_output_concept_ref"),
            bundle_b64=request_body.get("bundle_b64"),
            files=request_body.get("files"),
            method_ref=request_body.get("method_ref"),
        )


class StartRequest(RunRequest):
    """Body of `POST /start` — `RunRequest` plus the optional `pipeline_run_id`.

    `pipeline_run_id` is the client-supplied run identifier; this source-available
    runner accepts it (the server-generated id echoed in the start ack is always
    authoritative). Extension args pass through `extra="allow"` exactly as on
    `RunRequest`.
    """

    pipeline_run_id: str | None = Field(default=None, max_length=128)


_STORAGE_SCOPE_DESCRIPTION = (
    "PIPELEX-API EXTENSION (not part of the MTHDS Protocol) — the host-supplied prefix every object "
    "this run writes lands under. One to three path-safe segments (e.g. `tenant/run` or "
    "`org/method/run`); the runtime composes its own leaves (`assets/`, `generated/`, `results/`, "
    "`payloads/`) onto "
    "it and never interprets the value. Omit it and the run is scoped to the caller's own id, which "
    "is correct for a single-tenant deployment and wrong for a multi-tenant one — a host serving many "
    "tenants MUST send this."
)

_READ_SCOPE_DESCRIPTION = (
    "PIPELEX-API EXTENSION (not part of the MTHDS Protocol) — the host-supplied prefix every stored object "
    "this run reads must lie under, and on a scoped run no local path is read at all. One to three "
    "path-safe segments, which must be the `storage_scope` or one of its leading segments, since a run "
    "reads back what it writes. Omit it and the run is scoped to the caller's own id when the deployment "
    "identifies callers, and unscoped when it is single-tenant — a host serving many tenants MUST send this."
)

_ANALYTICS_GROUPS_DESCRIPTION = (
    "PIPELEX-API EXTENSION (not part of the MTHDS Protocol) — the host-supplied groups this run's "
    'telemetry belongs to, as a mapping of group type to group key (e.g. `{"organization": "org_acme"}`). '
    "The runtime never reads a key by name: it carries the mapping on the run as its `extras` and stamps it on every span as "
    "`pipelex.run.extras`, so every OpenTelemetry exporter receives it, and the deployment's own "
    "PostHog stream, in `identified` mode, forwards it as the capture's groups. What Pipelex's own Gateway telemetry "
    "stream receives is the runtime's decision, not this server's: the pinned runtime attributes it the same way, "
    "with the run's `user_id` and these groups. Group types are lowercase snake_case starting with a letter, at most 32 characters; group keys "
    "are 1 to 128 characters from `[A-Za-z0-9_-]`; at most five entries. Omit it and the run belongs to no "
    "group, which is right for a single-tenant deployment."
)

_CALLER_ANALYTICS_GROUPS_DESCRIPTION = (
    "PIPELEX-API EXTENSION (not part of the MTHDS Protocol) — the host-supplied groups the caller of this request "
    'belongs to, as a mapping of group type to group key (e.g. `{"organization": "org_acme"}`), exactly as a run '
    "request states them. The work this request does is not a run, but it still emits telemetry — the validation "
    "sweep's `pipe_dry_run` event and its dry runs — and that telemetry is attributed to the caller: the "
    "authenticated user and these groups. Same rules and same 422 `InvalidAnalyticsGroups` refusal as on "
    "`/execute` and `/start`. Omit it and the caller belongs to no group."
)


class CallerAnalyticsGroupsMixin(BaseModel):
    """The optional `analytics_groups` of a request whose work is done for a caller without being a run.

    `/validate` dry-runs the submitted pipes, and the runtime attributes that
    telemetry to the caller it is handed (`pipelex.system.caller_identity.CallerIdentity`). The user
    comes from the trusted auth layer, as on a run; the groups come from the body, as on a run, and are
    refused at the wire with the runtime's own rules.
    """

    analytics_groups: dict[str, str] | None = Field(default=None, description=_CALLER_ANALYTICS_GROUPS_DESCRIPTION)

    @field_validator("analytics_groups")
    @classmethod
    def _validate_caller_analytics_groups(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is None:
            return None
        return validate_run_extras(value=value)


_ORCHESTRATION_MODE_DESCRIPTION = (
    "PIPELEX-API EXTENSION (not part of the MTHDS Protocol) — request the orchestration mode (the backend) "
    "for this run. An OPEN string token: `direct` (in-process, the base default), `temporal`, and any other "
    "plugin-provided token are accepted; an unregistered token is refused at dispatch. The delivery axis "
    "(blocking vs fire-and-forget) is endpoint-set, never requestable. Honored ONLY when the deployment sets "
    "`allow_request_orchestration_mode_override = true` in its `api.toml`; otherwise a token that differs from "
    "the deployment default is refused with a 403. Omit it to use the deployment default."
)


_ALLOWED_CALLBACK_SCHEMES = frozenset({"http", "https"})


def _is_disallowed_host(host: str) -> bool:
    """True if `host` looks like a private/loopback/link-local address.

    Used to harden /start callback_urls against SSRF — a malicious
    client could otherwise aim webhooks at internal services or cloud metadata
    endpoints (e.g. 169.254.169.254). Best-effort: hostnames that resolve to
    private addresses at fire time aren't blocked here, only literal IPs.
    """
    if not host:
        return True
    if host in {"localhost", "metadata.google.internal", "metadata"}:
        return True
    try:
        addr = ip_address(host)
    except ValueError:
        return False
    return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_reserved or addr.is_unspecified


class PipelineApiExtras(BaseModel):
    """Validates the API-server-only fields on `/execute` and `/start` requests.

    `pipeline_run_id` is the protocol's optional start arg; `callback_urls` is
    THIS server's extension (the MTHDS Protocol defines no completion channel —
    extension args are defined and handled by the implementation that owns
    them). The upstream protocol models don't know about `callback_urls`.

    `storage_scope`, `read_scope` and `analytics_groups` are the host-computed run
    context: data a multi-tenant host knows about its own tenancy and sends in the
    body, as opposed to the caller's identity, which arrives on a trusted header. The
    runtime carries them opaquely and validates them again at its own seam.
    """

    model_config = ConfigDict(extra="ignore")

    pipeline_run_id: str | None = Field(default=None, max_length=128)
    callback_urls: list[str] | None = Field(default=None, max_length=MAX_CALLBACK_URLS)
    orchestration_mode: str | None = Field(default=None, description=_ORCHESTRATION_MODE_DESCRIPTION)
    storage_scope: str | None = Field(default=None, description=_STORAGE_SCOPE_DESCRIPTION)
    read_scope: str | None = Field(default=None, description=_READ_SCOPE_DESCRIPTION)
    analytics_groups: dict[str, str] | None = Field(default=None, description=_ANALYTICS_GROUPS_DESCRIPTION)

    @field_validator("read_scope")
    @classmethod
    def _validate_read_scope(cls, value: str | None) -> str | None:
        """Refuse a malformed read scope at the WIRE, with the runtime's own segment rule.

        Its relation to the storage scope is checked once both are resolved, since either may
        fall back to the caller's id (`pipelex_api.routes.pipelex.pipeline._resolve_run_scopes`).
        """
        if value is None:
            return None
        return validate_read_scope(value=value)

    @field_validator("storage_scope")
    @classmethod
    def _validate_storage_scope(cls, value: str | None) -> str | None:
        """Reject a traversal at the WIRE, not just at `JobMetadata`.

        `validate_storage_scope` guards the runtime seam too, so this is a
        second gate rather than the only one — but it is the one that answers a
        bad request with a 422 naming the field, instead of a 500 from deep in
        the run. The value becomes a storage key prefix, so a `..` in it escapes
        the tenant it is supposed to confine.
        """
        if value is None:
            return None
        return validate_storage_scope(value=value)

    @field_validator("analytics_groups")
    @classmethod
    def _validate_analytics_groups(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        """Refuse a malformed mapping at the WIRE, with the runtime's own rules.

        The runtime validates the mapping again at the top of `pipeline_run_setup`
        and on `RunMetadata`, so this is not the only gate. It is the one that
        answers with a 422 naming the field before a method is fetched or a
        library loaded. The rules are imported rather than restated: a second
        spelling of the charset here would drift from the one the runtime
        enforces, and the drift would surface as a 500 from inside the run.
        """
        if value is None:
            return None
        return validate_run_extras(value=value)

    @field_validator("callback_urls")
    @classmethod
    def _validate_callback_urls(cls, value: list[str] | None) -> list[str] | None:
        if not value:
            return value
        for url in value:
            if not url:
                msg = "callback_urls must be non-empty strings"
                raise ValueError(msg)
            if len(url) > MAX_CALLBACK_URL_LEN:
                msg = f"callback URL exceeds {MAX_CALLBACK_URL_LEN} chars"
                raise ValueError(msg)
            parsed = urlparse(url)
            if parsed.scheme not in _ALLOWED_CALLBACK_SCHEMES:
                msg = f"callback URL scheme must be http or https (got {parsed.scheme!r})"
                raise ValueError(msg)
            if _is_disallowed_host(parsed.hostname or ""):
                msg = f"callback URL host {parsed.hostname!r} is not allowed (private/loopback/metadata addresses are blocked)"
                raise ValueError(msg)
        return value


class PipelexApiStartRequest(StartRequest):
    """Documented body of `POST /start` — the protocol's `StartRequest` plus THIS server's extensions.

    Used only to publish the OpenAPI request schema: the protocol model no
    longer advertises implementation extensions, so this server documents the
    ones it implements itself. Wire validation happens in `PipelineApiExtras`.
    """

    callback_urls: list[str] | None = Field(
        default=None,
        description=(
            "PIPELEX-API EXTENSION (not part of the MTHDS Protocol) — completion webhooks. "
            "When the run finishes, the runner POSTs a completion notice to each URL, with an "
            "X-Completion-Signature header holding the HMAC-SHA256 of the run id (not of the body). "
            "The body carries `pipeline_run_id`, `state` (with the legacy `status` alias), `result_url` "
            "(the storage key prefix of the stored results, when results were stored) and `error` on "
            "failure; it does not carry the run's output. http/https only; private, loopback, link-local "
            "and cloud-metadata hosts are rejected."
        ),
    )
    orchestration_mode: str | None = Field(default=None, description=_ORCHESTRATION_MODE_DESCRIPTION)
    storage_scope: str | None = Field(default=None, description=_STORAGE_SCOPE_DESCRIPTION)
    read_scope: str | None = Field(default=None, description=_READ_SCOPE_DESCRIPTION)
    analytics_groups: dict[str, str] | None = Field(default=None, description=_ANALYTICS_GROUPS_DESCRIPTION)


class PipelexApiExecuteRequest(RunRequest):
    """Documented body of `POST /execute` — the protocol's `RunRequest` plus THIS server's run extensions.

    Used only to publish the OpenAPI request schema: `/execute` reads the body through the raw
    `Request` (plain JSON, parsed by the route), so FastAPI cannot infer the body type; this model documents the
    extensions the route actually honors (`orchestration_mode`, `storage_scope`, `read_scope`, `analytics_groups`,
    all parsed by `PipelineApiExtras`).
    """

    orchestration_mode: str | None = Field(default=None, description=_ORCHESTRATION_MODE_DESCRIPTION)
    storage_scope: str | None = Field(default=None, description=_STORAGE_SCOPE_DESCRIPTION)
    read_scope: str | None = Field(default=None, description=_READ_SCOPE_DESCRIPTION)
    analytics_groups: dict[str, str] | None = Field(default=None, description=_ANALYTICS_GROUPS_DESCRIPTION)


class PipeOutputWire(PipeOutput):
    """`PipeOutput` as it crosses the client boundary: usages trimmed to wire records.

    The route applies pipelex's `apply_tokens_usage_wire_shape` to the response dump, so
    `tokens_usages` carries flat `TokensUsageRecord`s — not the internal usage models with
    their `job_metadata` plumbing and `unit_costs` rate table.
    """

    # Narrows the inherited `list[AnyTokensUsage] | None`. `list` is invariant, so neither
    # type checker accepts the override; this is a schema declaration, not an assignment a
    # `cast()` could carry.
    tokens_usages: list[TokensUsageRecord] | None = None  # type: ignore[assignment]


_METHOD_PROVENANCE_DESCRIPTION = (
    "PIPELEX-API EXTENSION (not part of the MTHDS Protocol) — provenance of a `method_ref` run: the package's "
    "resolved full address, the requested tag (null for a bare address), and the commit SHA that was actually "
    "fetched. The SHA is what keeps the run explainable when a tag moves. Absent (or null) for runs from inline "
    "source or a bundle."
)


class PipelexApiExecuteResponse(PipelexRunResultExecute):
    """Documented 200 body of `POST /execute` — the run result with the wire-shaped `pipe_output`.

    Used only to publish the OpenAPI response schema. `/execute` returns a `JSONResponse`
    built from the trimmed dump, so FastAPI never serializes through this model; declaring it
    is what keeps the published artifact honest about what the route actually emits
    (`method_provenance` is attached to the dump by the route for `method_ref` runs, and is
    absent otherwise).
    """

    pipe_output: PipeOutputWire  # type: ignore[assignment]
    method_provenance: MethodProvenance | None = Field(default=None, description=_METHOD_PROVENANCE_DESCRIPTION)


class PipelexApiStartResponse(PipelexRunResultStart):
    """The 202 body of `POST /start` — the protocol's start ack plus this server's `method_provenance` extension.

    Unlike its `/execute` counterpart this model IS what the route returns (FastAPI serializes
    through it): the ack is small, so wrapping it costs nothing and keeps the artifact and the
    wire in lockstep. `method_provenance` is populated for `method_ref` runs and null otherwise.
    """

    method_provenance: MethodProvenance | None = Field(default=None, description=_METHOD_PROVENANCE_DESCRIPTION)


class MthdsFileItem(BaseModel):
    """One inline MTHDS bundle: its content plus an optional logical source for diagnostics.

    The `files[]` envelope pairs each content with its source in one entry (the shape the codegen
    spec pins for the resolve/codegen routes), unlike the legacy parallel
    `mthds_contents[]`/`mthds_sources[]` lists on `/validate`.
    """

    content: str = Field(..., description="MTHDS bundle content.")
    source: str | None = Field(
        default=None,
        max_length=1024,
        description=(
            "Optional logical source for this bundle (e.g. its path relative to the submitted directory). "
            "Threaded onto the blueprint so server-side diagnostics carry a `source` pointing at the owning file."
        ),
    )

    @field_validator("content")
    @classmethod
    def _bound_content(cls, value: str) -> str:
        _ensure_mthds_file_within_bytes_limit(value)
        return value


class MthdsFilesRequest(BaseModel):
    """Shared closure selector for the resolve/codegen routes: inline `files[]` XOR a `method_ref`.

    Exactly one of the two must be provided (spec'd envelope) — both or neither is a request-shape
    422. An **address-form** `method_ref` (`github.com/<owner>/<repo>[/<selector>][@<tag>]`) is
    resolved by this server: the repository is fetched at the tag, the package is located by
    manifest identity, and its `.mthds` files feed the closure with their real relative paths as
    per-file sources. The **registry form** (any non-address reference) stays reserved and answers
    501 until server-side method-registry resolution exists.
    """

    files: list[MthdsFileItem] | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_MTHDS_FILES_PER_REQUEST,
        description="Inline MTHDS bundles forming the closure to resolve (content-passing — no server-side path reads).",
    )
    method_ref: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_METHOD_REF_LEN,
        description=(
            "Reference to a published method, resolving to its package's `.mthds` files. Address form "
            "(`github.com/<owner>/<repo>[/<selector>][@<tag>]`) is fetched and resolved server-side; the registry "
            "form stays reserved (501 until a method registry exists)."
        ),
    )

    @model_validator(mode="after")
    def _exactly_one_selector(self) -> Self:
        if (self.files is None) == (self.method_ref is None):
            msg = "provide exactly one of `files` or `method_ref`"
            raise ValueError(msg)
        return self


class MthdsPipeRequest(MthdsFilesRequest):
    """The base of a per-pipe route's request (`/pipe-io`): the closure selector plus a pipe selector.

    The pipe selector is the **qualified** ref `domain.pipe_code`, mirroring `pipelex codegen inputs
    --pipe`. It is optional, and an omitted selector defaults with the run routes' precedence: on a
    `method_ref` request, to the fetched package manifest's `main_pipe` (the package author's declared
    entry pipe); otherwise to the closure's declared `main_pipe`, which is what a single-bundle caller
    almost always wants. A closure that declares no `main_pipe` — or several, across domains — cannot
    be defaulted from its own declarations, so when no manifest `main_pipe` settles it a route that
    needs one pipe refuses the omitted selector with an input 422, `EntryPipeNotFoundError` or
    `EntryPipeAmbiguousError` (`crate_ops.resolve_requested_pipe`), never the request-shape
    `ValidationError` of a malformed body.
    """

    pipe_ref: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_PIPE_CODE_LEN,
        description=(
            "Qualified pipe ref (`domain.pipe_code`) to select. Optional — defaults to the fetched package manifest's "
            "`main_pipe` on a `method_ref` request, else to the closure's declared `main_pipe`; a closure declaring none, "
            "or several, with no manifest `main_pipe` to settle it, requires it unless `all_pipes` is set."
        ),
    )


ALLOW_SIGNATURES_DESCRIPTION = (
    "When true, the validation sweep tolerates unimplemented pipe signatures instead of rejecting the "
    "bundle (signatures dry-run trivially by minting a mock). Defaults to false (strict)."
)
"""Used by `/validate`, the one route that runs the dry-run sweep: the flag only parameterizes that sweep,
so the static crate routes do not accept it."""


class MthdsContentsRequest(BaseModel):
    """The `POST /validate` request envelope: `mthds_contents` XOR `method_ref`, plus the sweep's `allow_signatures`.

    This is the flat-list envelope. `/validate` uses it through this class (its `ValidateRequest`
    subclass adds a parallel `mthds_sources` for per-file source labels), and the run routes
    `/execute` and `/start` carry the same `mthds_contents` field independently on `RunRequest`.
    The newer Pipelex-API extension routes (`/resolve`, `/codegen`, `/pipe-io`) use
    `MthdsFilesRequest` instead (`files[]` pairing each content with its `source`, XOR a
    `method_ref`), which folds the source label into each entry. `/validate` keeps the flat-list
    shape deliberately: it is an MTHDS Protocol route, so changing its inline envelope is a
    protocol-level decision owned by the `mthds/` spec, not this server's to take. `method_ref` is
    this server's layer-2 extension beside that inline shape — an address is resolved by the
    runner, so validate-by-address belongs here (the hosted-only `method_id` does not).
    """

    mthds_contents: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_MTHDS_FILES_PER_REQUEST,
        description="MTHDS contents to load (always an array, even for a single file). Exactly one of `mthds_contents` / `method_ref`.",
    )
    method_ref: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_METHOD_REF_LEN,
        description=(
            "PIPELEX-API EXTENSION (not part of the MTHDS Protocol) — validate a published method by reference "
            "instead of inline contents. Address form: `github.com/<owner>/<repo>[/<selector>][@<tag>]`, resolved by "
            "THIS runner through the same fetch path as a `method_ref` run; the package's `.mthds` files feed the "
            "validation with their real relative paths as per-file sources. Exactly one of `mthds_contents` / "
            "`method_ref`. A resolution failure (fetch, package location, the custom-Python policy) is a non-2xx "
            "`problem+json` — never an `is_valid: false` verdict, which is reserved for actual MTHDS content."
        ),
    )
    allow_signatures: bool = Field(default=False, description=ALLOW_SIGNATURES_DESCRIPTION)

    @field_validator("mthds_contents")
    @classmethod
    def _bound_each_file(cls, value: list[str] | None) -> list[str] | None:
        for content in value or []:
            _ensure_mthds_file_within_bytes_limit(content)
        return value

    @model_validator(mode="after")
    def _exactly_one_content_selector(self) -> Self:
        # Strict XOR (the addressing design's tooling-route rule): a stateless diagnostic call
        # has no linkage slot, so a second selector could only be ignored — refuse it instead.
        if (self.mthds_contents is None) == (self.method_ref is None):
            msg = "provide exactly one of `mthds_contents` or `method_ref`"
            raise ValueError(msg)
        return self
