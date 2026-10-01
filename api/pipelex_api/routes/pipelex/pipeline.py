from __future__ import annotations

import hashlib
import hmac
import json
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Annotated, Any, NamedTuple, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from mthds.protocol.exceptions import PipelineRequestError
from pipelex.config import get_config, is_pipe_func_sandbox_hosted
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, StorageTarget, WebhookTarget
from pipelex.pipe_run.pipe_run_protocol import PipeRunProtocol
from pipelex.pipeline.pipeline_response import PipelexRunResultExecute, PipelexRunResultStart, RunState
from pipelex.pipeline.pipeline_run_setup import pipeline_run_setup
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.reporting.usage_records import apply_tokens_usage_wire_shape
from pipelex.runtime_bridge.exceptions import MissingBundleValidatorError, MissingOrchestratorError
from pipelex.runtime_bridge.primitives.hydration import hydrate_working_memory
from pipelex.runtime_hub import get_bundle_validator_registry, get_orchestrator_registry
from pipelex.system.environment import get_required_env
from pipelex.system.storage_scope import LOCAL_STORAGE_SCOPE, SINGLE_TENANT_USER_ID, validate_storage_scope_within_read_scope
from pydantic import ValidationError
from typing_extensions import override

from pipelex_api.api_config import get_api_config, resolve_orchestration_mode
from pipelex_api.bundle import ParsedBundle, materialize_parsed, parse_bundle
from pipelex_api.error_types import ErrorType
from pipelex_api.errors import raise_bad_request, raise_forbidden, raise_validation_error
from pipelex_api.method_source import fetched_method_source
from pipelex_api.middleware import request_id_of
from pipelex_api.openapi_responses import (
    PROBLEM_400_START_REQUIRES_ASYNC,
    PROBLEM_403_RUN_POLICY,
    PROBLEM_404_METHOD_PACKAGE,
    PROBLEM_409_DUPLICATE_RUN,
    PROBLEM_429,
    PROBLEM_501_ASYNC_NOT_ENABLED,
)
from pipelex_api.routes.pipelex.utils import get_current_iso_timestamp
from pipelex_api.schemas.models import (
    PipelexApiExecuteRequest,
    PipelexApiExecuteResponse,
    PipelexApiStartRequest,
    PipelexApiStartResponse,
    PipelineApiExtras,
    RunRequest,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from mthds.protocol.pipe_output import VariableMultiplicity
    from mthds.protocol.pipeline_inputs import PipelineInputs
    from mthds.protocol.working_memory import WorkingMemoryAbstract
    from pipelex.base_exceptions import ErrorReport
    from pipelex.core.memory.working_memory import WorkingMemory
    from pipelex.methods.fetching import MethodProvenance
    from pipelex.pipe_run.pipe_job import PipeJob
    from pipelex.pipeline.validation_report import PipelexValidationReport
    from pipelex.plugins.orchestrator_registry import OrchestratorProtocol
    from pipelex.runtime_bridge.payloads import PipelexPipeRunOutput

    from pipelex_api.security import RequestUser


router = APIRouter(tags=["run"])


def get_request_user_id(request: Request) -> str:
    """The caller this run is attributed to, and the owner its storage is keyed by.

    **There is no `anonymous` fallback any more, and its removal is the point.**
    This used to return the literal `"anonymous"` whenever `request.state.user`
    was unset, which is reached on every auth path that establishes no
    per-caller identity. That string then became the first segment of every
    storage key the run wrote, so a deployment serving many callers put all of
    them in one namespace where each could read the others' outputs — and it
    looked like a working request the whole way through.

    An identity-bearing deployment cannot get here without a user: `verify_jwt`
    and `verify_api_key` raise on a bad token, and `no_auth` now raises when
    `TRUST_FORWARDED_IDENTITY_HEADERS` is on and no id was forwarded. So a
    missing user means the deployment declared it has no user model
    (`AUTH_MODE=none` with no trusted proxy, or the shared static key), which is
    a single tenant by configuration rather than an unknown caller.
    """
    user: RequestUser | None = getattr(request.state, "user", None)
    return user.user_id if user else SINGLE_TENANT_USER_ID


def _resolve_storage_scope(request: Request, *, requested: str | None) -> str:
    """Where this run's bytes go — the host's value, or the caller's own id.

    **Scope is data, not identity**, which is why it arrives in the BODY while
    `user_id` arrives on a trusted header. The runtime needs to know where to
    write, not who to trust, so a multi-tenant host computes this where it knows
    its own tenancy (`<org>/<method>/<run>` on hosted Pipelex) and sends it.

    The fallback is the CALLER'S OWN ID, deliberately, and not a shared constant.
    This runner used to derive the prefix from `user_id` internally; removing
    that coupling is the point of the change, but the safe default when a
    deployment says nothing is still one namespace per caller. A shared literal
    here would recreate the `anonymous/` bug in a new spelling — every caller of
    an identity-bearing deployment writing into one namespace, each able to read
    the others' outputs, and looking like a working request throughout.

    A single-tenant deployment therefore gets `single-tenant/…` by configuration
    rather than by accident, and a multi-tenant one that forgets to send a scope
    still isolates its callers.
    """
    return requested or get_request_user_id(request)


def _resolve_read_scope(request: Request, *, requested: str | None) -> str | None:
    """What this run may read — the host's value, the caller's own id, or everything.

    A sent value is the host's and is taken as it is. The fallback mirrors the storage
    scope's (design DR2 of the read-scope campaign): when the field is omitted, a deployment
    that identifies its callers scopes the run to the caller's own id, which is also where
    their writes land by default, and a single-tenant deployment runs unscoped. That default
    bounds a caller only where the host writes the body: a caller reaching a `jwt`
    deployment directly can send any read scope, as it can send any storage scope. On a
    multi-tenant host that forgets the field, the fallback fails closed: the host's own
    storage scope lies under no caller's id, so the run is refused rather than reading
    across tenants.
    """
    if requested is not None:
        return requested
    user: RequestUser | None = getattr(request.state, "user", None)
    return user.user_id if user else None


class _RunScopes(NamedTuple):
    storage_scope: str
    read_scope: str | None


def _resolve_run_scopes(request: Request, *, extras: PipelineApiExtras) -> _RunScopes:
    """Resolve the run's storage and read scopes, and refuse a pair the run could not work under.

    The runtime refuses a storage scope outside the read scope, and the local storage
    sentinel beside any read scope, with a bare `ValueError` from inside the run, which
    would answer 500. Checking the resolved pair here answers the caller's mistake with a
    422 naming the field, before any method is fetched or library loaded.
    """
    storage_scope = _resolve_storage_scope(request, requested=extras.storage_scope)
    read_scope = _resolve_read_scope(request, requested=extras.read_scope)
    if read_scope is not None:
        if storage_scope == LOCAL_STORAGE_SCOPE:
            raise_validation_error(
                message=f"A run with a read_scope must pass its own storage_scope, not the local sentinel {LOCAL_STORAGE_SCOPE!r}.",
                error_type=ErrorType.INVALID_READ_SCOPE,
            )
        try:
            validate_storage_scope_within_read_scope(storage_scope=storage_scope, read_scope=read_scope)
        except ValueError as exc:
            origin = "sent" if extras.read_scope is not None else "defaulted to the caller's id"
            raise_validation_error(
                message=f"{exc} The read_scope {read_scope!r} was {origin}, and the storage_scope is {storage_scope!r}.",
                error_type=ErrorType.INVALID_READ_SCOPE,
            )
    return _RunScopes(storage_scope=storage_scope, read_scope=read_scope)


def _completion_signature(pipeline_run_id: str) -> str:
    """Compute the HMAC-SHA256 signature for an async completion callback.

    The signer (this server) and the verifier (your callback receiver) must
    share the same `COMPLETION_CALLBACK_SECRET`. The signature is per-run and
    the secret never travels — only the one-way hash does.
    """
    secret = get_required_env("COMPLETION_CALLBACK_SECRET")
    return hmac.new(
        secret.encode("utf-8"),
        pipeline_run_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _pipe_output_from_run_output(run_output: PipelexPipeRunOutput) -> PipeOutput:
    """Rehydrate an orchestrator's JSON-safe `PipelexPipeRunOutput` into a typed `PipeOutput`.

    The `OrchestratorRegistry` answers with the JSON-safe boundary payload (the same shape
    that crosses the Temporal worker boundary), produced by `serialize_completed_output`.
    `/execute` returns the FULL output, so the synchronous path reverses that serialization
    here, restoring the rich `PipeOutput` the base `execute` then wraps in
    `PipelexRunResultExecute`:

      - `working_memory` is rebuilt via `hydrate_working_memory` — the same routine the
        Temporal workers use — so it must run while the run library (hence the scoped
        `ClassRegistry`) is still open; the base `execute` keeps it open until after the run
        returns, which is exactly this call site.
      - `graph_spec` / `pipe_io_artifacts` / `tokens_usages` are validated back from their
        `model_dump(mode="json")` dumps with `strict=False`: the orchestrator dumped them in JSON mode (e.g.
        `GraphSpec.created_at` became an ISO string), and those models are `strict=True`, so a
        strict re-validation would reject the string. `strict=False` is the correct tool for
        reversing our own trusted JSON dump — it is a round-trip, not untrusted ingest.

    Routing DIRECT through this serialize→rehydrate round-trip is intentional: it keeps
    `/execute` on the SAME per-call dispatch seam as `/start` and `/validate` (no per-mode
    branch), at the cost of one in-process re-serialization of the working memory.
    """
    return PipeOutput.model_validate(
        {
            "working_memory": hydrate_working_memory(run_output.output_dict),
            "pipeline_run_id": run_output.pipeline_run_id,
            "graph_spec": run_output.graph_spec_dump,
            "graph_assembly_error": run_output.graph_assembly_error,
            "pipe_io_artifacts": run_output.pipe_io_artifacts_dump,
            "pipe_io_artifacts_error": run_output.pipe_io_artifacts_error,
            "tokens_usages": run_output.tokens_usages_dump,
            "usage_assembly_error": run_output.usage_assembly_error,
        },
        strict=False,
    )


class _OrchestratorPipeRun(PipeRunProtocol):
    """Adapts a mode-selected orchestrator to the `PipeRunProtocol` the base `execute` drives.

    `ApiRunner.execute` injects one of these as `self._pipe_run` so the base `execute` retains
    ALL of its run lifecycle (library setup/teardown, tracer close, pipeline-manager cleanup,
    telemetry, error mapping) while the actual dispatch goes through the per-request
    `orchestration_mode`'s orchestrator instead of the boot-global pipe-run slot. The
    orchestrator's JSON-safe output is rehydrated back into the rich `PipeOutput` the base expects.

    The blocking wait-semantics is intrinsic to `orchestrator.execute` (the protocol's BLOCKING arm —
    it awaits completion and returns the completed-run `PipelexPipeRunOutput`); `/execute` is
    synchronous and always drives this arm, so there is no delivery axis to thread here.
    """

    def __init__(self, *, orchestrator: OrchestratorProtocol) -> None:
        self._orchestrator = orchestrator

    @override
    async def run(self, pipe_job: PipeJob, *, delivery_assignment: DeliveryAssignment | None = None) -> PipeOutput:
        run_output = await self._orchestrator.execute(pipe_job=pipe_job, delivery_assignment=delivery_assignment)
        return _pipe_output_from_run_output(run_output)


class ApiRunner(PipelexMTHDSProtocol):
    """API runner that dispatches `execute`, `start`, and `validate` through the per-call plugin registries.

    Every surface resolves the deployment's `orchestration_mode` (config default + optional
    per-request override) and dispatches through a per-call hub registry: `execute` runs a
    top-level pipe through the `OrchestratorRegistry`'s blocking `execute` arm and returns the
    full output, `start` enqueues one through the same registry's fire-and-forget `start` arm,
    `validate_verdict` produces a validation verdict through the `BundleValidatorRegistry`. On the
    orchestrator-agnostic base that means `direct` in-process; a `temporal` mode dispatches to a
    worker when `pipelex-temporal` is installed and selected. The base names no orchestrator and
    imports no orchestrator SDK; a mode with no registered arm fails loud with the matching
    `Missing*Error` (carrying the install hint). Delivery is endpoint-intrinsic — the caller never
    chooses it; only the backend is resolved per request. Dispatch changes the BACKEND, never the
    artifact shapes — every operation answers with the same canonical models as the local runtime.
    """

    @override
    async def execute(
        self,
        pipe_code: str | None = None,
        mthds_contents: list[str] | None = None,
        inputs: PipelineInputs | WorkingMemoryAbstract[Any] | None = None,
        output_name: str | None = None,
        output_multiplicity: VariableMultiplicity | None = None,
        dynamic_output_concept_ref: str | None = None,
        extra: dict[str, Any] | None = None,
        delivery_assignment: DeliveryAssignment | None = None,
        request_id: str | None = None,
        requested_orchestration_mode: str | None = None,
    ) -> PipelexRunResultExecute:
        """Execute a method synchronously, dispatching by the resolved `orchestration_mode`.

        Symmetric with `start`: the effective `orchestration_mode` is resolved FIRST (config default
        + optional per-request override, so a forbidden override is refused with a 403 before any
        library load), then the run is dispatched through the hub's `OrchestratorRegistry` instead
        of the boot-global pipe-run slot. `direct` runs in-process on this agnostic base; a
        `temporal` mode dispatches the whole job to a worker and awaits it. A mode with no registered
        orchestrator fails loud with `MissingOrchestratorError` (carrying the install hint).

        `/execute` is synchronous — it returns the full output — so it drives the orchestrator's
        blocking `execute` arm regardless of backend. Wait-semantics is endpoint-intrinsic, never
        requestable, so there is nothing for the caller to get wrong here (the fire-and-forget arm
        is `/start`'s, gated there by an honest capability check).

        The orchestrator is injected as this runner's `_pipe_run` so the inherited base `execute`
        keeps the entire run lifecycle (library setup/teardown, tracer close, pipeline-manager
        cleanup, telemetry, error mapping); only the dispatch backend and the output rehydration
        (`_OrchestratorPipeRun`) change. `request_id` is an API-layer extra threaded into
        `RunMetadata.request_id` for log correlation, so it reaches the job a worker is handed.
        `requested_orchestration_mode` is the optional per-request backend override
        (`PipelineApiExtras.orchestration_mode`).
        """
        # Resolve the effective orchestration mode FIRST — a per-request override the deployment
        # policy forbids is refused (403) here, before any library load / run registration. Mirrors start().
        orchestration_mode = resolve_orchestration_mode(requested_orchestration_mode, config=get_api_config())
        orchestrator = get_orchestrator_registry().get_optional(mode=orchestration_mode)
        if orchestrator is None:
            raise MissingOrchestratorError(mode=orchestration_mode)

        # Dispatch the run through the mode-selected orchestrator by injecting it as this runner's
        # PipeRun, then delegate to the base execute, which owns the full run lifecycle. The
        # ApiRunner is constructed per request, so mutating _pipe_run here is request-scoped.
        # `/execute` is synchronous, so it drives the orchestrator's BLOCKING `execute` arm.
        self._pipe_run = _OrchestratorPipeRun(orchestrator=orchestrator)
        return await super().execute(
            pipe_code=pipe_code,
            mthds_contents=mthds_contents,
            inputs=inputs,
            output_name=output_name,
            output_multiplicity=output_multiplicity,
            dynamic_output_concept_ref=dynamic_output_concept_ref,
            extra=extra,
            delivery_assignment=delivery_assignment,
            request_id=request_id,
        )

    @override
    async def start(
        self,
        pipe_code: str | None = None,
        mthds_contents: list[str] | None = None,
        inputs: PipelineInputs | WorkingMemoryAbstract[Any] | None = None,
        output_name: str | None = None,
        output_multiplicity: VariableMultiplicity | None = None,
        dynamic_output_concept_ref: str | None = None,
        extra: dict[str, Any] | None = None,
        pipeline_run_id: str | None = None,
        callback_urls: list[str] | None = None,
        request_id: str | None = None,
        requested_orchestration_mode: str | None = None,
    ) -> PipelexRunResultStart:
        """Start a method execution asynchronously without waiting for completion.

        Dispatch is orchestrator-agnostic: the rich `PipeJob` is built locally (so
        `request_id`, `output_multiplicity`, `dynamic_output_concept_ref`, the run
        registration, and telemetry all survive) and then handed to the resolved
        `orchestration_mode`'s orchestrator via its fire-and-forget `start` arm, through the
        hub's `OrchestratorRegistry`. The base imports no `temporalio` / orchestrator SDK; the
        async-capable Temporal arm (returning a `workflow_id` immediately) is contributed by the
        `pipelex-temporal` plugin when installed.

        `/start` is genuinely fire-and-forget, so it is HONEST about its capability: the resolved
        mode's orchestrator is looked up and its `supports_fire_and_forget` checked BEFORE any
        library load. A blocking-only orchestrator (the in-process `direct` base) cannot honor
        async delivery, so it is refused with a 400 (`START_REQUIRES_ASYNC_ORCHESTRATION`) — use
        `/execute` — rather than silently running blocking and acking. A mode with no registered
        orchestrator fails loud with `MissingOrchestratorError` (carrying the install hint), also
        before any library load.

        `pipeline_run_id` is the client-supplied run identifier — this source-available runner
        honors it (protocol: implementations MAY decline it, but then MUST 422;
        we accept it, and `StartAck.pipeline_run_id` echoes it back as authoritative).
        `callback_urls` is THIS server's extension (completion webhooks) — the wire
        layer validates it (`PipelineApiExtras`) and passes it here by name.
        `extra` is the protocol's generic extension slot; this runner's wire
        extras are parsed by the route layer, so nothing reaches it — a
        non-empty value is an in-process misuse and is rejected. `request_id`
        is an API-layer extra threaded into `RunMetadata.request_id` for log
        correlation, so it reaches the job a worker is handed. `requested_orchestration_mode` is the optional per-request backend override
        (`PipelineApiExtras.orchestration_mode`); it is resolved against the deployment's
        `api.toml` policy and a forbidden override is refused with a 403.
        """
        if extra:
            msg = f"ApiRunner defines no extension args beyond its named ones; got {sorted(extra)}."
            raise PipelineRequestError(msg)
        # Resolve the effective orchestration mode FIRST — a per-request override the deployment
        # policy forbids is refused (403) here. Then look up the orchestrator and check its async
        # capability: `/start` is fire-and-forget, so a blocking-only orchestrator (direct on the
        # agnostic base) is refused HONESTLY with a 400 instead of silently running blocking and
        # acking. Both gates run BEFORE pipeline_run_setup so a doomed request never loads a library.
        orchestration_mode = resolve_orchestration_mode(requested_orchestration_mode, config=get_api_config())
        orchestrator = get_orchestrator_registry().get_optional(mode=orchestration_mode)
        if orchestrator is None:
            raise MissingOrchestratorError(mode=orchestration_mode)
        if not orchestrator.supports_fire_and_forget:
            msg = (
                f"Orchestration mode '{orchestration_mode}' cannot honor fire-and-forget delivery: /start requires an "
                f"async-capable orchestration, and this deployment has none. Use /execute (synchronous) instead."
            )
            raise_bad_request(msg, error_type=ErrorType.START_REQUIRES_ASYNC_ORCHESTRATION)
        created_at = get_current_iso_timestamp()
        pipelex_inputs: PipelineInputs | WorkingMemory | None = cast("PipelineInputs | WorkingMemory | None", inputs)

        execution_config = self.execution_config or get_config().interpreter.pipeline_execution
        # Wire and runtime share the `pipeline_run_id` name (master D1 as
        # revised — the id rename was reversed).
        pipe_job, resolved_pipeline_run_id, _ = await pipeline_run_setup(
            execution_config=execution_config,
            library_id=self.library_id,
            library_dirs=self.library_dirs,
            pipe_code=pipe_code,
            mthds_contents=mthds_contents,
            bundle_uris=self.bundle_uris,
            inputs=pipelex_inputs,
            output_name=output_name,
            output_multiplicity=output_multiplicity,
            dynamic_output_concept_ref=dynamic_output_concept_ref,
            pipe_run_mode=self.pipe_run_mode,
            user_id=self.user_id,
            storage_scope=self.storage_scope,
            read_scope=self.read_scope,
            # The base `execute` threads this itself; `start` builds its job
            # here, so a group left out of this call is dropped with no error
            # and the run's spans lose their groups while the ack still says 202.
            extras=self.extras,
            pipeline_run_id=pipeline_run_id,
            request_id=request_id,
        )

        delivery_assignment = DeliveryAssignment(
            # NO `key_prefix` — the runtime owns the `results/` leaf.
            #
            # This used to say `key_prefix="results"`, from the layout where the
            # executor built `{user_id}/{key_prefix}{pipeline_run_id}` and the
            # caller supplied the leaf. It now builds
            # `{storage_scope}/{key_prefix}results`, so passing it here wrote
            # every run's output to `<scope>/results/results/` — valid, stable,
            # and wrong, with nothing failing to say so.
            #
            # `key_prefix` remains the caller's slot for an EXTRA level between
            # the scope and the leaf; it is not where the leaf itself comes from.
            storage=StorageTarget(),
            # The completion payload's wire fields (`pipeline_run_id`/`state`,
            # plus the transitional `status` alias) are written per delivery by
            # pipelex's DeliveryExecutor — they are reserved keys on
            # WebhookTarget.payload, so nothing is injected here.
            webhooks=[
                WebhookTarget(
                    url=url,
                    headers={"X-Completion-Signature": _completion_signature(resolved_pipeline_run_id)},
                )
                for url in callback_urls
            ]
            if callback_urls
            else [],
        )

        # Dispatch the locally-built job through the resolved mode's orchestrator (looked up and
        # capability-checked above) via its fire-and-forget `start` arm — the same final dispatch
        # `run_pipe_via_bridge` performs, but fed the rich PipeJob instead of the lossy
        # `PipelexPipeRunInput` (which carries no request_id / output_multiplicity /
        # dynamic_output_concept_ref and skips run registration + telemetry). `start` genuinely
        # enqueues the job and returns a `PipelexPipeDispatchAck` (ids only) immediately.
        dispatch_ack = await orchestrator.start(pipe_job=pipe_job, delivery_assignment=delivery_assignment)

        return PipelexRunResultStart(
            pipeline_run_id=resolved_pipeline_run_id,
            created_at=created_at,
            state=RunState.STARTED,
            workflow_id=dispatch_ack.workflow_id,
        )

    async def validate_verdict(
        self,
        *,
        mthds_contents: list[str],
        mthds_sources: list[str] | None,
        allow_signatures: bool,
        requested_orchestration_mode: str | None,
        graph_pipe_code: str | None,
    ) -> PipelexValidationReport | ErrorReport:
        """Validate MTHDS bundles, returning the verdict as a value (the route maps it to a 200).

        Mode-aware, mirroring `start`: the effective `orchestration_mode` is resolved FIRST (config
        default + optional per-request override, so a forbidden override is refused with a 403
        before any library load), then dispatched through the hub's `BundleValidatorRegistry`.
        `direct` validates in-process on this agnostic base; a `temporal` mode dispatches the
        whole job to a worker (`pipelex-temporal`). A mode with no registered validator fails
        loud with `MissingBundleValidatorError` (carrying the install hint). Validation is inherently
        blocking, so there is no delivery axis here — the registry holds one validator per mode.

        Returns the verdict, not a raise: the valid `PipelexValidationReport`, or the structured
        `ErrorReport` an invalid bundle produces (carrying `validation_errors`). A genuine
        no-verdict infra fault propagates to the global problem+json handler (5xx). The route
        discriminates on `isinstance(verdict, PipelexValidationReport)`.

        `mthds_sources` is the optional per-content source-threading hook: each source lands on
        the corresponding `blueprint.source`, so the structured `validation_errors` on a failure —
        and the `bundle_blueprint` on success — carry a real `source` instead of `None`. The route
        maps a length mismatch to a 422 before we get here; `None` keeps the sourceless behavior.
        `library_dirs` is host context the in-process arm needs; a dispatched arm ignores it (the
        worker loads its own library). A bundle without a declared `main_pipe` validates fine and
        simply carries `graph_spec=None` (D2 — no precondition).

        `graph_pipe_code` is the pipe the best-effort graph is drawn from, resolved the way a run
        resolves its entry pipe; `None` keeps the runtime's default, the primary blueprint's
        `main_pipe`. The route passes a fetched package manifest's `main_pipe`, so the graph shows
        the pipe a selector-less run by that address executes.
        """
        # Resolve the effective mode FIRST — a per-request override the deployment policy forbids
        # is refused (403) here, before any validator dispatch / library load. Mirrors start().
        orchestration_mode = resolve_orchestration_mode(requested_orchestration_mode, config=get_api_config())
        validator = get_bundle_validator_registry().get_optional(mode=orchestration_mode)
        if validator is None:
            raise MissingBundleValidatorError(mode=orchestration_mode)
        library_dirs = [Path(library_dir) for library_dir in self.library_dirs] if self.library_dirs else None
        verdict = await validator.validate_bundles(
            mthds_contents=mthds_contents,
            mthds_sources=mthds_sources,
            allow_signatures=allow_signatures,
            library_dirs=library_dirs,
            # A validation is not a run, but its dry runs and its `pipe_dry_run` event are still
            # done for the caller this runner was built for — the user and groups a run would state.
            caller_identity=self.caller_identity,
            graph_pipe_code=graph_pipe_code,
        )
        # The core seam types its valid arm at the protocol-level ValidationReport (a leaf type)
        # to stay import-acyclic in core; every registered validator in fact produces the canonical
        # PipelexValidationReport. Recover the precise type here — the single narrowing point — so
        # the route's `isinstance(verdict, PipelexValidationReport)` yields ErrorReport on the else arm.
        return cast("PipelexValidationReport | ErrorReport", verdict)


# The object keys a kajson decoder reads as class markers: `__class__` and `__module__` name a class to
# import and instantiate, and kajson reserves every key starting with `__kajson` for itself. The same set
# the hosted platform refuses before it forwards a run body.
_RESERVED_OBJECT_KEYS = frozenset({"__class__", "__module__"})
_RESERVED_OBJECT_KEY_PREFIX = "__kajson"


def _find_reserved_object_key(payload: object) -> str | None:
    """Return the first reserved object key found at any depth of a parsed JSON value, or `None`.

    Walks every object key at every depth with an explicit stack, so a deeply nested body cannot
    exhaust the interpreter's recursion budget here. Values are never inspected: a string that
    merely contains `__class__` is data, not a marker.
    """
    stack: list[object] = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, value in cast("dict[str, object]", current).items():
                if key in _RESERVED_OBJECT_KEYS or key.startswith(_RESERVED_OBJECT_KEY_PREFIX):
                    return key
                stack.append(value)
        elif isinstance(current, list):
            stack.extend(cast("list[object]", current))
    return None


def _decode_body(body: bytes) -> dict[str, Any]:
    """Parse the run body as plain JSON and confirm it is an object free of class markers. Raises 422 if not.

    The body is parsed with `json.loads`, never with kajson. kajson reads a
    `{"__class__": ..., "__module__": ...}` object as an order to import that module and
    instantiate that class, so decoding a caller's body with it let any caller run code on the
    server (`subprocess.Popen` included) before a single field was validated. The MTHDS Protocol
    wire is plain JSON, and no client sends class markers.

    Parsing as plain data is not enough on its own: a marker accepted as an ordinary dict comes
    back to life the moment the runtime round-trips the inputs through kajson. So a key a kajson
    decoder treats as a marker is refused at any depth with a 422 `ReservedObjectKey`.

    The parse failures are caller mistakes, so they map to a 422 `InvalidJSON` rather than a
    sanitized 500:
      - `UnicodeDecodeError` — the body bytes are not valid UTF-8.
      - `ValueError` — `json.JSONDecodeError` (it subclasses `ValueError`).
      - `RecursionError` — a deeply nested JSON array or object exhausts the parser's
        recursion budget.
    """
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise_validation_error(
            message=f"Request body is not valid JSON: {exc!s}",
            error_type=ErrorType.INVALID_JSON,
        )
    if not isinstance(decoded, dict):
        raise_validation_error(
            message="Request body must be a JSON object",
            error_type=ErrorType.INVALID_JSON,
        )
    request_data = cast("dict[str, Any]", decoded)
    reserved_key = _find_reserved_object_key(request_data)
    if reserved_key is not None:
        # The key is the caller's, as long as the body allows (any `__kajson…` key matches), and the
        # detail is logged as a field: echo it bounded, as the correlation fields are.
        shown_key = reserved_key if len(reserved_key) <= _MAX_CORRELATION_FIELD_LEN else f"{reserved_key[:_MAX_CORRELATION_FIELD_LEN]}…"
        raise_validation_error(
            message=(
                f"Request body contains the reserved object key '{shown_key}'. A run request is plain JSON: "
                f"no object in it may carry a '__class__' or '__module__' key, or a key starting with '{_RESERVED_OBJECT_KEY_PREFIX}'."
            ),
            error_type=ErrorType.RESERVED_OBJECT_KEY,
        )
    return request_data


# The `error_type` a 422 on one extras field carries. A field absent from this map
# (`pipeline_run_id`, `orchestration_mode`) answers with the generic `ValidationError`.
_EXTRAS_FIELD_ERROR_TYPES: dict[str, ErrorType] = {
    "callback_urls": ErrorType.INVALID_CALLBACK_URLS,
    "storage_scope": ErrorType.INVALID_STORAGE_SCOPE,
    "read_scope": ErrorType.INVALID_READ_SCOPE,
    "analytics_groups": ErrorType.INVALID_ANALYTICS_GROUPS,
}


def _extras_error_type(exc: ValidationError) -> ErrorType:
    """Classify an extras failure by the field that failed, so a client can branch on `error_type`.

    Every extras failure used to answer `InvalidCallbackUrls`, including a traversal in
    `storage_scope` on a request that carried no callback at all. A body failing on
    more than one field gets the generic `ValidationError`: naming one of them would
    send the caller to fix that field and leave the other one for the next request.
    """
    failed_fields = {str(error["loc"][0]) for error in exc.errors() if error["loc"]}
    if len(failed_fields) != 1:
        return ErrorType.VALIDATION_ERROR
    return _EXTRAS_FIELD_ERROR_TYPES.get(failed_fields.pop(), ErrorType.VALIDATION_ERROR)


def _validate_extras(request_data: dict[str, Any]) -> PipelineApiExtras:
    """Validate the API-server-only fields `PipelineApiExtras` declares, read straight off the body.

    The whole body is validated rather than a hand-copied subset of its keys: the model
    ignores keys it does not declare, so a field added to it is read off the wire with no
    second list to keep in step. Such a list would drop a forgotten key SILENTLY, and for
    `storage_scope` that is worse than an error: the run falls back to the caller's own id
    and writes to the wrong prefix while reporting success.
    """
    try:
        return PipelineApiExtras.model_validate(request_data)
    except ValidationError as exc:
        raise_validation_error(
            message=str(exc),
            error_type=_extras_error_type(exc),
        )


# Per-field bound applied at the request.state binding site so an oversized
# caller-supplied `pipe_code` cannot blow up the size of every record the request emits.
# `RunRequest.pipe_code` carries no Pydantic `max_length`; this is the
# narrow cap that protects the structured error log without changing the
# upstream type contract. 256 covers any realistic pipe code (kebab-case
# identifier, typically tens of chars) with headroom.
_MAX_CORRELATION_FIELD_LEN = 256


def _coerce_correlation_field(value: Any) -> str | None:
    """Normalize a body-derived correlation identifier for `request.state` binding.

    Returns `None` when the value is missing, empty, or non-string — so the
    handler's `_pipe_code_of` / `_pipeline_run_id_of` getters see a uniform
    `None` and the error record carries no attribute at all, rather than an
    empty string a downstream query would read as a real value. Truncates
    oversized strings to `_MAX_CORRELATION_FIELD_LEN` so a caller cannot
    inflate every error record the request emits by sending a megabyte-long
    pipe_code.
    """
    if not isinstance(value, str) or not value:
        return None
    return value[:_MAX_CORRELATION_FIELD_LEN]


async def _parse_request(request: Request) -> tuple[RunRequest, PipelineApiExtras]:
    """Parse and validate the request body.

    Splits the body into:
      1. The upstream `RunRequest` (pipe_code, mthds_contents, inputs, …),
         parsed as plain JSON by `_decode_body`, which refuses class markers.
      2. `PipelineApiExtras` (pipeline_run_id, callback_urls, orchestration_mode,
         storage_scope, analytics_groups) validated by Pydantic — callback_urls
         are checked for scheme + private/loopback hosts to harden against SSRF.

    Body size is capped upstream by `request_body_size_middleware`.
    """
    body = await request.body()
    request_data = _decode_body(body)
    # Bind body-derived correlation identifiers onto `request.state` as soon as
    # the raw dict is in hand — before `_validate_extras` or `from_body`, so a
    # later validation failure (a rejected callback URL, a Pydantic coercion
    # error on a sibling field) still rides the identifiers the caller named.
    # `_coerce_correlation_field` normalizes empty / non-string / oversized.
    # Mirrors the `_set_request_user` pattern in `pipelex_api.security` (binding the
    # earliest known identity onto the request).
    request.state.pipe_code = _coerce_correlation_field(request_data.get("pipe_code"))
    request.state.pipeline_run_id = _coerce_correlation_field(request_data.get("pipeline_run_id"))
    extras = _validate_extras(request_data)
    try:
        run_request = RunRequest.from_body(request_data)
    except (PipelineRequestError, ValidationError) as exc:
        # `from_body` rejects a body where neither `pipe_code` nor
        # `mthds_contents` is supplied (PipelineRequestError) and a body whose
        # fields fail Pydantic coercion (ValidationError) — both are caller
        # mistakes, not server faults, so they map to a 422 rather than
        # escaping to the generic-500 fallback.
        raise_validation_error(message=str(exc))
    return run_request, extras


@contextmanager
def _bundle_run_source(run_request: RunRequest) -> Generator[tuple[list[str] | None, list[str] | None], None, None]:
    """Resolve a run's `(mthds_contents, library_dirs)` from the request.

    A method bundle KEEPS the proven run path rather than replacing it: its `.mthds`
    text travels as `mthds_contents` — so `main_pipe` resolves exactly as it does for a
    plain (non-bundle) run — and ONLY the non-`.mthds` files (custom PipeFunc `.py`,
    `requirements.txt`) are materialized into a temp `library_dirs` entry, where the
    load path reads them without importing them. This mirrors "a normal run, plus the Python", instead of
    handing the engine a bare directory with no `mthds_contents` (which never resolves
    `main_pipe`, since that is only derived from `mthds_contents`).

    No bundle → yields the request's own `mthds_contents` and no library dir (the
    classic path, unchanged). Bundle with no non-`.mthds` files → yields the `.mthds`
    texts and no library dir. The temp dir (when created) is cleaned up on exit.

    Security gate (decision 5): a bundle that ships custom Python (`.py`) is only
    honored on a sandbox-hosted deployment, where the load path reads the source
    without importing it and refuses, with a 403 `MethodStructuresRefusedError`, a
    bundle whose Python declares a structure class; PipeFunc source is captured for
    the sandbox. On a non-hosted deployment, running that code would import it
    in-process — refused with a 403 rather than executing untrusted code.
    """
    if run_request.bundle_b64 is None and run_request.files is None:
        yield run_request.mthds_contents, None
        return
    # Parse + guard in memory FIRST, then apply the sandbox-hosted gate BEFORE any disk write —
    # a bundle destined for a 403 on a non-hosted deployment never touches the filesystem.
    parsed = parse_bundle(bundle_b64=run_request.bundle_b64, files=run_request.files)
    if parsed.has_python_sources and not is_pipe_func_sandbox_hosted():
        msg = "This bundle ships custom Python (.py); running it requires a sandbox-hosted deployment."
        raise_forbidden(message=msg, error_type=ErrorType.CUSTOM_CODE_REQUIRES_SANDBOX)
    # Split: `.mthds` text → `mthds_contents` (the proven main_pipe path); everything else
    # (`.py`, `requirements.txt`) → a temp `library_dirs` entry the load path source-captures.
    mthds_contents: list[str] = []
    other_entries: list[tuple[PurePosixPath, bytes]] = []
    for relpath, content in parsed.entries:
        if str(relpath).endswith(".mthds"):
            try:
                mthds_contents.append(content.decode("utf-8"))
            except UnicodeDecodeError:
                raise_validation_error(message=f"Bundle .mthds file '{relpath}' is not valid UTF-8.", error_type=ErrorType.INVALID_BUNDLE)
        else:
            other_entries.append((relpath, content))
    if not mthds_contents:
        raise_validation_error(message="Method bundle contains no .mthds file.", error_type=ErrorType.INVALID_BUNDLE)
    if not other_entries:
        yield mthds_contents, None
        return
    with materialize_parsed(ParsedBundle(entries=tuple(other_entries))) as bundle:
        yield mthds_contents, [str(bundle.directory)]


class _ResolvedRunSource(NamedTuple):
    """What the run routes hand the runner, whatever the request's source form was."""

    mthds_contents: list[str] | None
    library_dirs: list[str] | None
    pipe_code: str | None
    method_provenance: MethodProvenance | None


@contextmanager
def _run_source(run_request: RunRequest) -> Generator[_ResolvedRunSource, None, None]:
    """Resolve the request's run source: a `method_ref` fetch, a bundle, or the inline contents.

    A `method_ref` resolves through `pipelex_api.method_source.fetched_method_source` (fetch → locate →
    execution-locus gate → materialize) into exactly the shape a bundle produces — `.mthds` text
    as `mthds_contents`, non-`.mthds` files in a temp `library_dirs` entry — so the engine runs
    the same proven path. The entry pipe defaults to the fetched manifest's `main_pipe`; a
    request `pipe_code` overrides it. Provenance `(address, tag, commit_sha)` rides back so the
    routes can put it on the response. The other two forms delegate to `_bundle_run_source`,
    unchanged.
    """
    if run_request.method_ref is not None:
        with fetched_method_source(run_request.method_ref) as fetched:
            yield _ResolvedRunSource(
                mthds_contents=fetched.mthds_contents,
                library_dirs=fetched.library_dirs,
                pipe_code=run_request.pipe_code or fetched.main_pipe,
                method_provenance=fetched.provenance,
            )
        return
    with _bundle_run_source(run_request) as (mthds_contents, library_dirs):
        yield _ResolvedRunSource(
            mthds_contents=mthds_contents,
            library_dirs=library_dirs,
            pipe_code=run_request.pipe_code,
            method_provenance=None,
        )


@router.post(
    "/execute",
    # Documented 200 = the run result with the WIRE-shaped `pipe_output`: the handler returns a
    # `JSONResponse` built from a trimmed dump, so FastAPI never serializes through this model —
    # it is purely what the artifact publishes, and it must match `apply_tokens_usage_wire_shape`.
    response_model=PipelexApiExecuteResponse,
    # On top of the composite router's shared 401/413/422/500: the policy 403s (a forbidden
    # per-request `orchestration_mode` override, the custom-code sandbox gate, the structures
    # refusal on a bundle or a fetched package), the `method_ref` package-not-found 404, and the provider
    # rate-limit passthrough (429) — `/execute` is the only route that runs inference, so it is
    # the only one that can be rate-limited upstream. NO 409: unlike `/start`, `/execute` takes
    # no client-supplied `pipeline_run_id` (the base runner generates one per call), so a caller
    # cannot collide with an in-flight run.
    responses={403: PROBLEM_403_RUN_POLICY, 404: PROBLEM_404_METHOD_PACKAGE, 429: PROBLEM_429},
    # Documented body = the protocol's RunRequest plus THIS server's own
    # `orchestration_mode` extension (the route honors a per-request override). The
    # body is read through the raw Request (plain JSON with the reserved-key
    # refusal — see `_parse_request`), so FastAPI cannot infer a typed body parameter;
    # document it explicitly so the committed OpenAPI artifact (and protocol
    # conformance tooling) publishes the request schema. `responses=` and
    # `openapi_extra` touch different members of the operation object, so both land.
    openapi_extra={
        "x-mthds-protocol": True,
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": PipelexApiExecuteRequest.model_json_schema()}},
        },
    },
)
async def execute(request: Request) -> JSONResponse:
    """Execute a method synchronously and return its full output (MTHDS Protocol `POST /execute`).

    The backend is selected by the resolved `orchestration_mode` (deployment default + optional
    policy-gated per-request override via the `orchestration_mode` extra), symmetric with `/start` —
    not by `boot_orchestrator`. `/execute` is synchronous, so it dispatches with `BLOCKING` delivery
    regardless of backend (wait-semantics is endpoint-set, never requestable). Pipelex domain
    failures propagate untouched: the global `PipelexError` handler in `pipelex_api.exception_handlers`
    turns them into an RFC 7807 problem response.
    """
    run_request, extras = await _parse_request(request)
    scopes = _resolve_run_scopes(request, extras=extras)
    with _run_source(run_request) as source:
        runner = ApiRunner(
            user_id=get_request_user_id(request),
            storage_scope=scopes.storage_scope,
            read_scope=scopes.read_scope,
            extras=extras.analytics_groups,
            library_dirs=source.library_dirs,
        )
        response = await runner.execute(
            pipe_code=source.pipe_code,
            mthds_contents=source.mthds_contents,
            inputs=run_request.inputs,
            output_name=run_request.output_name,
            output_multiplicity=run_request.output_multiplicity,
            dynamic_output_concept_ref=run_request.dynamic_output_concept_ref,
            request_id=request_id_of(request),
            requested_orchestration_mode=extras.orchestration_mode,
        )
    # The response dump carries the full internal usage models on
    # `pipe_output.tokens_usages`; the client boundary gets the trimmed
    # `TokensUsageRecord` wire shape instead (pipelex owns the shape authority).
    response_dump = response.model_dump(mode="json", serialize_as_any=True, by_alias=True)
    apply_tokens_usage_wire_shape(response_dump, pipe_output=response.pipe_output)
    # Provenance of a `method_ref` run (address, tag, resolved commit SHA) — attached only when
    # the run was selected by reference, so the classic response stays byte-identical.
    if source.method_provenance is not None:
        response_dump["method_provenance"] = source.method_provenance.model_dump(mode="json")
    return JSONResponse(content=response_dump)


@router.post(
    "/start",
    response_model=PipelexApiStartResponse,
    status_code=202,
    # On top of the composite router's shared 401/413/422/500. `/start` is fire-and-forget, so
    # its extra failures are all about the backend's ability to honor that and about the
    # client-supplied run id it (alone) accepts:
    #   400 — the resolved orchestrator is blocking-only (the in-process `direct` base): refuse
    #         honestly rather than block-and-ack. Use `/execute`.
    #   403 — a per-request `orchestration_mode` override the deployment forbids, the
    #         custom-code sandbox gate, or the structures refusal on a bundle or a fetched package.
    #   404 — a `method_ref` whose repository holds no matching package.
    #   409 — the submitted `pipeline_run_id` is still registered for an in-flight run.
    #   501 — an async-capable deployment whose async execution is not enabled.
    responses={
        400: PROBLEM_400_START_REQUIRES_ASYNC,
        403: PROBLEM_403_RUN_POLICY,
        404: PROBLEM_404_METHOD_PACKAGE,
        409: PROBLEM_409_DUPLICATE_RUN,
        501: PROBLEM_501_ASYNC_NOT_ENABLED,
    },
    # Documented body = the protocol's StartRequest plus THIS server's own
    # extensions (callback_urls) — the protocol model no longer advertises
    # implementation extensions, so the server documents what it implements.
    # Raw-Request parsing prevents FastAPI from inferring it — see the
    # /execute note.
    openapi_extra={
        "x-mthds-protocol": True,
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": PipelexApiStartRequest.model_json_schema()}},
        },
    },
)
async def start(
    request: Request,
    parsed: Annotated[tuple[RunRequest, PipelineApiExtras], Depends(_parse_request)],
) -> PipelexApiStartResponse:
    """Start a method run and return its pipeline_run_id with a 202 ack (MTHDS Protocol `POST /start`).

    Answers `202 Accepted` with a `StartAck`. A client-supplied `pipeline_run_id` is
    honored (the protocol lets an implementation decline it; this runner accepts it, and
    `StartAck.pipeline_run_id` is always authoritative). Pipelex domain failures propagate untouched: the global
    `PipelexError` handler in `pipelex_api.exception_handlers` turns them into an
    RFC 7807 problem response.

    Fire-and-forget is a property of THIS endpoint (its delivery axis), honored only by an
    async-capable backend. A deployment configures the backend (`orchestration_mode`) once; `/start`
    sets `FIRE_AND_FORGET` delivery and checks the resolved orchestrator can honor it. A Temporal
    deployment (`orchestration_mode = "temporal"`) enqueues the run and returns immediately with a
    `workflow_id`. On the orchestrator-agnostic base (`orchestration_mode = "direct"`, the default)
    the in-process orchestrator is blocking-only, so `/start` is HONEST: it refuses with a `400`
    (`StartRequiresAsyncOrchestration`) — use `/execute` — rather than silently blocking and acking.
    The completion callback (`callback_urls` / storage delivery) fires on the async path.
    """
    run_request, extras = parsed
    scopes = _resolve_run_scopes(request, extras=extras)
    # The run source is materialized only for the synchronous setup phase: `start` builds the
    # PipeJob (crate carrying the captured `python_sources`) before it enqueues, so the temp dir
    # (a bundle's, or a fetched package's) is no longer needed once `start` returns — cleanup on
    # context exit is safe for the async path.
    with _run_source(run_request) as source:
        runner = ApiRunner(
            user_id=get_request_user_id(request),
            storage_scope=scopes.storage_scope,
            read_scope=scopes.read_scope,
            extras=extras.analytics_groups,
            library_dirs=source.library_dirs,
        )
        start_result = await runner.start(
            pipe_code=source.pipe_code,
            mthds_contents=source.mthds_contents,
            inputs=run_request.inputs,
            output_name=run_request.output_name,
            output_multiplicity=run_request.output_multiplicity,
            dynamic_output_concept_ref=run_request.dynamic_output_concept_ref,
            pipeline_run_id=extras.pipeline_run_id,
            callback_urls=extras.callback_urls,
            request_id=request_id_of(request),
            requested_orchestration_mode=extras.orchestration_mode,
        )
    # The ack plus this server's provenance extension: `(address, tag, commit_sha)` for a
    # `method_ref` run, null otherwise — the caller (and, on hosted, the platform's Run row)
    # learns exactly what was fetched and at which commit.
    return PipelexApiStartResponse(
        **dict(start_result),
        method_provenance=source.method_provenance,
    )
