from __future__ import annotations

import asyncio
import hashlib
import hmac
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, NamedTuple, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from mthds.protocol.problem.registry import CoreCode
from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.config import get_config
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.errors.bundle_validation_failure import BundleValidationFailure
from pipelex.errors.problem import ProblemView
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.libraries.method_requirements import ensure_served_method_requirements_met
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, StorageTarget, WebhookTarget
from pipelex.pipe_run.exceptions import AsyncExecutionNotEnabledError
from pipelex.pipe_run.pipe_run_protocol import PipeRunProtocol
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.pipeline_response import PipelexRunResultExecute, PipelexRunResultStart, RunState
from pipelex.pipeline.pipeline_run_setup import pipeline_run_setup
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.pipeline.validate_bundle_translation import translate_to_validate_bundle_error
from pipelex.reporting.usage_records import apply_tokens_usage_wire_shape
from pipelex.runtime_bridge.exceptions import MissingBundleValidatorError, MissingOrchestratorError
from pipelex.runtime_bridge.primitives.hydration import hydrate_working_memory
from pipelex.runtime_hub import get_bundle_validator_registry, get_orchestrator_registry
from pipelex.system.environment import get_required_env
from pipelex.system.storage_scope import LOCAL_STORAGE_SCOPE, SINGLE_TENANT_USER_ID, validate_storage_scope_within_read_scope
from pydantic import ValidationError
from typing_extensions import override

from pipelex_api.api_config import ApiConfig, get_api_config, is_callers_override, resolve_orchestration_mode
from pipelex_api.blob_store import RunnerBlobStore
from pipelex_api.bundle_resources import decode_bundle_resources
from pipelex_api.exceptions import CustomCodeOrigin, ReservedObjectKeyError, RunnerRequestError
from pipelex_api.json_body import decode_json_body
from pipelex_api.method_source import fetched_method
from pipelex_api.method_tree_request import (
    BUNDLE_FIELD,
    REQUEST_METHOD_LABEL,
    RequestMethod,
    ensure_method_holds_a_bundle,
    ensure_python_allowed,
    read_archive_method,
    read_request_method,
    record_request_method,
    select_tree_entry,
    tree_documents_of,
    with_resources,
    written_method,
)
from pipelex_api.middleware import request_id_of
from pipelex_api.openapi_responses import (
    PROBLEM_404_METHOD_PACKAGE,
    PROBLEM_409_DUPLICATE_RUN,
    PROBLEM_429,
    PROBLEM_501_RUN_POLICY,
    PROBLEM_501_START,
)
from pipelex_api.problem_view import problem_view_of
from pipelex_api.request_refusals import WHOLE_BODY_FIELD, callback_url_refusal_in, refused_request_error
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
    from collections.abc import AsyncGenerator

    from mthds.protocol.pipe_output import VariableMultiplicity
    from mthds.protocol.pipeline_inputs import PipelineInputs
    from mthds.protocol.working_memory import WorkingMemoryAbstract
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


def resolve_blob_scope(request: Request, *, read_scope: str | None) -> str:
    """The scope of the blob store a request's hash entries resolve in: its read scope, else the caller's own id.

    The same scope a run reads under, so a hash entry resolves only in the caller's own blobs, never across tenants:
    a multi-tenant host sends the organization it serves as the read scope, and a deployment that identifies no caller
    is one tenant, `single-tenant`.
    """
    return read_scope or get_request_user_id(request)


class _RunScopes(NamedTuple):
    storage_scope: str
    read_scope: str | None


# The run request's field naming the scope a run may read, which a refusal of the scopes it resolves to names.
_READ_SCOPE_FIELD = "read_scope"


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
            msg = f"A run with a read_scope must pass its own storage_scope, not the local sentinel {LOCAL_STORAGE_SCOPE!r}."
            raise RunnerRequestError(msg, field=_READ_SCOPE_FIELD)
        try:
            validate_storage_scope_within_read_scope(storage_scope=storage_scope, read_scope=read_scope)
        except ValueError as exc:
            origin = "sent" if extras.read_scope is not None else "defaulted to the caller's id"
            msg = f"{exc} The read_scope {read_scope!r} was {origin}, and the storage_scope is {storage_scope!r}."
            raise RunnerRequestError(msg, field=_READ_SCOPE_FIELD) from exc
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

    def __init__(self, *, orchestrator: OrchestratorProtocol, orchestration_mode: str) -> None:
        self._orchestrator = orchestrator
        self._orchestration_mode = orchestration_mode

    @override
    async def run(self, pipe_job: PipeJob, *, delivery_assignment: DeliveryAssignment | None = None) -> PipeOutput:
        run_output = await self._orchestrator.execute(pipe_job=pipe_job, delivery_assignment=delivery_assignment)
        return _pipe_output_from_run_output(run_output)


def _missing_orchestrator_error(*, mode: str, api_config: ApiConfig) -> MissingOrchestratorError:
    """The refusal of a run whose orchestration mode no installed plugin serves, coded by whose choice the mode was.

    A mode the caller named as a per-request override is the caller's to change (`runtime.unsupported`); the
    deployment's own default is the operator's, who installs its plugin (`pipelex.plugin.not_found`).
    """
    if is_callers_override(orchestration_mode=mode, config=api_config):
        return MissingOrchestratorError(mode=mode).with_error_code(CoreCode.RUNTIME_UNSUPPORTED)
    return MissingOrchestratorError(mode=mode).with_error_code(PipelexErrorCode.PLUGIN_NOT_FOUND)


def _missing_bundle_validator_error(*, mode: str, api_config: ApiConfig) -> MissingBundleValidatorError:
    """The `/validate` twin of `_missing_orchestrator_error`, coded the same way by whose choice the mode was."""
    if is_callers_override(orchestration_mode=mode, config=api_config):
        return MissingBundleValidatorError(mode=mode).with_error_code(CoreCode.RUNTIME_UNSUPPORTED)
    return MissingBundleValidatorError(mode=mode).with_error_code(PipelexErrorCode.PLUGIN_NOT_FOUND)


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
        + optional per-request override, so a forbidden override is refused with a 422 before any
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
        # policy forbids is refused (422) here, before any library load / run registration. Mirrors start().
        api_config = get_api_config()
        orchestration_mode = resolve_orchestration_mode(requested_orchestration_mode, config=api_config)
        orchestrator = get_orchestrator_registry().get_optional(mode=orchestration_mode)
        if orchestrator is None:
            raise _missing_orchestrator_error(mode=orchestration_mode, api_config=api_config)
        await self._ensure_served_method_requirements_met()

        # Dispatch the run through the mode-selected orchestrator by injecting it as this runner's
        # PipeRun, then delegate to the base execute, which owns the full run lifecycle. The
        # ApiRunner is constructed per request, so mutating _pipe_run here is request-scoped.
        # `/execute` is synchronous, so it drives the orchestrator's BLOCKING `execute` arm.
        self._pipe_run = _OrchestratorPipeRun(orchestrator=orchestrator, orchestration_mode=orchestration_mode)
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
        callback_problem_view: ProblemView = ProblemView.CALLER,
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
        async delivery, so it is refused with a 501 (`runtime.unsupported`) — use
        `/execute` — rather than silently running blocking and acking. A mode with no registered
        orchestrator fails loud with `MissingOrchestratorError` (carrying the install hint), also
        before any library load.

        `pipeline_run_id` is the client-supplied run identifier — this source-available runner
        honors it (protocol: implementations MAY decline it, but then MUST 422;
        we accept it, and `StartAck.pipeline_run_id` echoes it back as authoritative).
        `callback_urls` is THIS server's extension (completion webhooks) — the wire
        layer validates it (`PipelineApiExtras`) and passes it here by name.
        `callback_problem_view` is the view of a failed run's problem those webhooks carry: the
        view of the request's own reader (`pipelex_api.problem_view`), since a completion webhook
        is the same answer as the synchronous response, delivered later.
        `extra` is the protocol's generic extension slot; this runner's wire
        extras are parsed by the route layer, so nothing reaches it — a
        non-empty value is an in-process misuse and is rejected. `request_id`
        is an API-layer extra threaded into `RunMetadata.request_id` for log
        correlation, so it reaches the job a worker is handed. `requested_orchestration_mode` is the optional per-request backend override
        (`PipelineApiExtras.orchestration_mode`); it is resolved against the deployment's
        `api.toml` policy and a forbidden override is refused with a 422.
        """
        if extra:
            # Nothing on the wire reaches `extra`: the route parses the extras itself and passes them by name, so a
            # value here is a fault of the in-process code calling this runner, never the caller's.
            msg = f"ApiRunner defines no extension args beyond its named ones; got {sorted(extra)}."
            raise PipelexUnexpectedError(msg)
        # Resolve the effective orchestration mode FIRST — a per-request override the deployment
        # policy forbids is refused (422) here. Then look up the orchestrator and check its async
        # capability: `/start` is fire-and-forget, so a blocking-only orchestrator (direct on the
        # agnostic base) is refused HONESTLY with a 501 `runtime.unsupported` instead of silently
        # running blocking and acking. Both gates run BEFORE pipeline_run_setup so a doomed request never loads a library.
        api_config = get_api_config()
        orchestration_mode = resolve_orchestration_mode(requested_orchestration_mode, config=api_config)
        orchestrator = get_orchestrator_registry().get_optional(mode=orchestration_mode)
        if orchestrator is None:
            raise _missing_orchestrator_error(mode=orchestration_mode, api_config=api_config)
        if not orchestrator.supports_fire_and_forget:
            msg = (
                f"Orchestration mode '{orchestration_mode}' cannot honor fire-and-forget delivery: /start requires an "
                f"async-capable orchestration, and this deployment has none. Use /execute (synchronous) instead."
            )
            raise AsyncExecutionNotEnabledError(msg)
        await self._ensure_served_method_requirements_met()
        created_at = get_current_iso_timestamp()
        pipelex_inputs: PipelineInputs | WorkingMemory | None = cast("PipelineInputs | WorkingMemory | None", inputs)

        execution_config = self.execution_config or get_config().interpreter.pipeline_execution
        # Wire and runtime share the `pipeline_run_id` name (master D1 as
        # revised — the id rename was reversed).
        pipe_job, resolved_pipeline_run_id, _ = await pipeline_run_setup(
            execution_config=execution_config,
            library_id=self.library_id,
            library_dirs=self.library_dirs,
            # A method the request carries as a tree is the caller's, as the base `execute` threads it too.
            library_dirs_are_callers=self.library_dirs_are_callers,
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
            # The packages the request ships, which the base `execute` threads too.
            methods_dirs=self.methods_dirs,
            # The files submitted with the contents, such as a template file, which the base `execute` threads too.
            submitted_files=self.submitted_files,
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
                    problem_view=callback_problem_view,
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

    async def _ensure_served_method_requirements_met(self) -> None:
        """Refuse the request's method when its requirements.txt is not met, before anything loads or is dispatched.

        This runner's `library_dirs` are the directories it wrote the request's method tree into, the caller's own,
        whose load reports a requirements refusal as the caller's too; judging it here first refuses the run before
        any library opens or any run is registered, naming no path on this host. The tree is held as written, so its
        listing is the tree the request sent. The listing reads and hashes files, so it runs off the event loop.

        Raises:
            MethodRequirementsFileError: The method's requirements.txt holds a line the standard refuses.
            MethodRequirementsNotMetError: The PipeFunc environment does not meet the method's requirements.
            HostLibraryTreeError: A directory of the request could not be listed as a method tree.
            PipeFuncPackageSetUnstatedError: The deployment states no package set for its PipeFunc sandbox.
        """
        if not self.library_dirs:
            return
        library_dirs = [Path(library_dir) for library_dir in self.library_dirs]
        await asyncio.to_thread(ensure_served_method_requirements_met, library_dirs=library_dirs)

    async def validate_verdict(
        self,
        *,
        mthds_contents: list[str] | None,
        mthds_sources: list[str] | None,
        allow_signatures: bool,
        requested_orchestration_mode: str | None,
        graph_pipe_code: str | None,
        method_dir: Path | None = None,
    ) -> PipelexValidationReport | BundleValidationFailure:
        """Validate MTHDS bundles, returning the verdict as a value (the route maps it to a 200).

        Mode-aware, mirroring `start`: the effective `orchestration_mode` is resolved FIRST (config
        default + optional per-request override, so a forbidden override is refused with a 422
        before any library load), then dispatched through the hub's `BundleValidatorRegistry`.
        `direct` validates in-process on this agnostic base; a `temporal` mode dispatches the
        whole job to a worker (`pipelex-temporal`). A mode with no registered validator fails
        loud with `MissingBundleValidatorError` (carrying the install hint). Validation is inherently
        blocking, so there is no delivery axis here — the registry holds one validator per mode.

        Returns the verdict, not a raise: the valid `PipelexValidationReport`, or the
        `BundleValidationFailure` an invalid bundle produces (carrying `validation_errors`). A genuine
        no-verdict infra fault propagates to the global problem+json handler (5xx). The route
        discriminates on `isinstance(verdict, PipelexValidationReport)`.

        `mthds_sources` is the optional per-content source-threading hook: each source lands on
        the corresponding `blueprint.source`, so the structured `validation_errors` on a failure —
        and the `bundle_blueprint` on success — carry a real `source` instead of `None`. The route
        maps a length mismatch to a 422 before we get here; `None` keeps the sourceless behavior.
        `library_dirs` is host context the in-process arm needs; a dispatched arm ignores it (the
        worker loads its own library), so the requirements.txt of the methods they hold is checked here
        first, for every arm, and a method whose requirements are not met is an invalid verdict. A
        bundle without a declared `main_pipe` validates fine and simply carries `graph_spec=None`
        (D2 — no precondition).

        `graph_pipe_code` is the pipe the best-effort graph is drawn from, resolved the way a run
        resolves its entry pipe; `None` keeps the runtime's default, the primary blueprint's
        `main_pipe`. The route passes the entry pipe of a method tree, so the graph shows the pipe a
        selector-less run of that method executes.

        `method_dir` is the directory a method tree the request carries was written as, by `files` or
        fetched by `method_ref`: the validation loads it whole, with this runner's `methods_dirs`, in
        place of `mthds_contents`, which is then None, and its refusals are the method's verdict.
        """
        # Resolve the effective mode FIRST — a per-request override the deployment policy forbids
        # is refused (422) here, before any validator dispatch / library load. Mirrors start().
        api_config = get_api_config()
        orchestration_mode = resolve_orchestration_mode(requested_orchestration_mode, config=api_config)
        validator = get_bundle_validator_registry().get_optional(mode=orchestration_mode)
        if validator is None:
            raise _missing_bundle_validator_error(mode=orchestration_mode, api_config=api_config)
        library_dirs = [Path(library_dir) for library_dir in self.library_dirs] if self.library_dirs else None
        # The method's requirements.txt is judged here, on the runner, which holds the method's files and the package set
        # its PipeFunc steps run with, before any dispatch: a dispatched validator never reads these directories. A
        # refusal is the method's invalid verdict, as a run of it is refused before its files load.
        try:
            with translate_to_validate_bundle_error():
                await self._ensure_served_method_requirements_met()
        except ValidateBundleError as invalid_method:
            return BundleValidationFailure(
                problem=invalid_method.to_problem(view=ProblemView.OPERATOR),
                validation_errors=invalid_method.validation_error_items(),
            )
        verdict = await validator.validate_bundles(
            mthds_contents=mthds_contents,
            mthds_sources=mthds_sources,
            allow_signatures=allow_signatures,
            # A method directory is the whole method: no library directory loads beside it.
            library_dirs=None if method_dir is not None else library_dirs,
            method_dir=method_dir,
            methods_dirs=self.methods_dirs if method_dir is not None else None,
            # A validation is not a run, but its dry runs and its `pipe_dry_run` event are still
            # done for the caller this runner was built for — the user and groups a run would state.
            caller_identity=self.caller_identity,
            graph_pipe_code=graph_pipe_code,
            # The files submitted with the contents, which the validation's dry run reads, the template check included.
            submitted_files=self.submitted_files,
        )
        # The core seam types its valid arm at the protocol-level ValidationReport (a leaf type)
        # to stay import-acyclic in core; every registered validator in fact produces the canonical
        # PipelexValidationReport. Recover the precise type here — the single narrowing point — so
        # the route's `isinstance(verdict, BundleValidationFailure)` yields the report on the else arm.
        return cast("PipelexValidationReport | BundleValidationFailure", verdict)


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
    """Parse the run body as plain JSON and confirm it is an object. Raises 422 if not.

    The body is parsed as plain JSON by `decode_json_body`, never with kajson. kajson reads a
    `{"__class__": ..., "__module__": ...}` object as an order to import that module and
    instantiate that class, so decoding a caller's body with it let any caller run code on the
    server (`subprocess.Popen` included) before a single field was validated. The MTHDS Protocol
    wire is plain JSON, and no client sends class markers.

    Parsing as plain data is not enough on its own: a marker accepted as an ordinary dict comes
    back to life the moment the runtime round-trips the inputs through kajson. So the caller,
    `_parse_request`, refuses a key a kajson decoder treats as a marker at any depth with a 422
    `pipelex.security.reserved_key` (`_refuse_reserved_object_keys`), once the run's extras are bound
    for the security event that refusal logs.

    The parse is `decode_json_body`'s, so its failures are caller mistakes answered with a 422
    `request.malformed` rather than a sanitized 500: a body nested deeper than `MAX_JSON_NESTING_DEPTH`,
    refused before it is parsed whatever the interpreter and its stack, a body that is not UTF-8,
    and one that is not JSON. A body that parses to anything but an object is a 422 `request.invalid`.
    """
    decoded = decode_json_body(body)
    if not isinstance(decoded, dict):
        msg = "Request body must be a JSON object"
        raise RunnerRequestError(msg, field=WHOLE_BODY_FIELD)
    return cast("dict[str, Any]", decoded)


def _refuse_reserved_object_keys(request_data: dict[str, Any]) -> None:
    """Refuse a body holding an object key a kajson decoder reads as a class marker, at any depth, with a 422.

    The refusal is a security rule's, `pipelex.security.reserved_key`, so it logs a security event, which names the
    kind of thing refused and never the key. The problem's `keys` parameter names the key the caller sent, bounded as
    the correlation fields are.
    """
    reserved_key = _find_reserved_object_key(request_data)
    if reserved_key is not None:
        # The key is the caller's, as long as the body allows (any `__kajson…` key matches): echo it bounded.
        shown_key = reserved_key if len(reserved_key) <= _MAX_CORRELATION_FIELD_LEN else f"{reserved_key[:_MAX_CORRELATION_FIELD_LEN]}…"
        msg = (
            f"Request body contains the reserved object key '{shown_key}'. A run request is plain JSON: "
            f"no object in it may carry a '__class__' or '__module__' key, or a key starting with '{_RESERVED_OBJECT_KEY_PREFIX}'."
        )
        raise ReservedObjectKeyError(msg, keys=[shown_key])


def _validate_extras(request_data: dict[str, Any]) -> PipelineApiExtras:
    """Validate the API-server-only fields `PipelineApiExtras` declares, read straight off the body.

    The whole body is validated rather than a hand-copied subset of its keys: the model
    ignores keys it does not declare, so a field added to it is read off the wire with no
    second list to keep in step. Such a list would drop a forgotten key SILENTLY, and for
    `storage_scope` that is worse than an error: the run falls back to the caller's own id
    and writes to the wrong prefix while reporting success.

    A field the model refuses is a 422 `request.invalid` with one item per refused field (`refused_request_error`),
    except a callback URL the SSRF rules refuse, which is answered as its own security refusal,
    `security.input_url_refused`, whatever else failed (`callback_url_refusal_in`).
    """
    try:
        return PipelineApiExtras.model_validate(request_data)
    except ValidationError as exc:
        faults = exc.errors()
        raise (callback_url_refusal_in(faults=faults) or refused_request_error(faults=faults, located_by_request_part=False)) from exc


def _validated_run_extras_or_none(request_data: dict[str, Any]) -> dict[str, str] | None:
    """The body's `analytics_groups` when they pass the runtime's rules on their own, else `None`.

    Read before anything else is refused, so that the security event of a refusal before the extras are validated,
    such as a reserved object key or a callback URL, still names whose request it was, with values the runtime's
    own rules accepted.
    """
    try:
        return PipelineApiExtras.model_validate({"analytics_groups": request_data.get("analytics_groups")}).analytics_groups
    except ValidationError:
        return None


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


class _ParsedRunRequest(NamedTuple):
    """A run request's body as the routes read it: the typed request, its extras, and its raw bytes."""

    run_request: RunRequest
    extras: PipelineApiExtras
    body: bytes
    """The raw body, which a method sent as `files` is read from, keeping what only the JSON text holds."""


async def _parse_request(request: Request) -> _ParsedRunRequest:
    """Parse and validate the request body.

    Splits the body into:
      1. The upstream `RunRequest` (pipe_code, mthds_contents, inputs, …),
         parsed as plain JSON by `_decode_body`, then refused by `_refuse_reserved_object_keys` if it carries a class marker.
      2. `PipelineApiExtras` (pipeline_run_id, callback_urls, orchestration_mode,
         storage_scope, analytics_groups) validated by Pydantic — callback_urls
         are checked for scheme + private/loopback hosts to harden against SSRF.

    Body size is capped upstream by `request_body_size_middleware`.
    """
    body = await request.body()
    request_data = _decode_body(body)
    # The run's opaque extras, for the security event a refusal of this request logs before any run carries them.
    request.state.run_extras = _validated_run_extras_or_none(request_data)
    _refuse_reserved_object_keys(request_data)
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
    except ValidationError as exc:
        # A body whose fields fail Pydantic coercion is a caller mistake, not a server fault, so it maps to
        # a 422 `request.invalid`, one item per refused field, rather than escaping to the generic-500 fallback.
        # A body naming its run source wrongly, or none, is refused by `from_body` as a `PipelexRequestError`
        # instead, which needs no catch here: it is a `PipelexError` carrying `request.invalid` or
        # `request.unsupported`, and the global handler answers it with its code.
        raise refused_request_error(faults=exc.errors(), located_by_request_part=False) from exc
    return _ParsedRunRequest(run_request=run_request, extras=extras, body=body)


class _ResolvedRunSource(NamedTuple):
    """What the run routes hand the runner, whatever the request's source form was."""

    mthds_contents: list[str] | None
    library_dirs: list[str] | None
    library_dirs_are_callers: bool
    """Whether `library_dirs` hold the caller's own method, so a refusal while loading them is the caller's (a 422)."""
    methods_dirs: list[Path] | None
    pipe_code: str | None
    method_provenance: MethodProvenance | None
    submitted_files: dict[str, bytes] | None
    """The files `resources` sends beside `mthds_contents`; beside a method tree they join the tree instead."""


async def _request_method_of(*, run_request: RunRequest, body: bytes, blob_store: RunnerBlobStore) -> RequestMethod | None:
    """The method a run request carries as a tree, `files` or `bundle_b64`, read in full, or None when it carries none.

    The files `resources` sends join the tree. Every tree is recorded in the blob store once the Python gate passed.
    """
    if run_request.bundle_b64 is not None and run_request.files is not None:
        msg = "Provide either bundle_b64 or files, not both"
        raise RunnerRequestError(msg, field=BUNDLE_FIELD)
    request_method: RequestMethod | None
    if run_request.bundle_b64 is not None:
        request_method = await read_archive_method(bundle_b64=run_request.bundle_b64)
    elif run_request.files is not None or run_request.dependencies is not None:
        # Only a body sending a tree is parsed again, keeping its pairs; an inline run never pays a second parse.
        request_method = await read_request_method(documents=tree_documents_of(body=body), blob_store=blob_store)
    else:
        request_method = None
    if request_method is None:
        return None
    request_method = with_resources(request_method=request_method, resources=decode_bundle_resources(resources=run_request.resources))
    ensure_method_holds_a_bundle(request_method=request_method, label="This method")
    ensure_python_allowed(request_method=request_method, label="This method", origin=CustomCodeOrigin.BUNDLE)
    await record_request_method(request_method=request_method, blob_store=blob_store)
    return request_method


@asynccontextmanager
async def _run_source(*, run_request: RunRequest, body: bytes, blob_scope: str) -> AsyncGenerator[_ResolvedRunSource, None]:
    """Resolve the request's run source: a method tree (`files`, `bundle_b64` or a `method_ref`), or the inline contents.

    A method tree is written into a temporary directory and held as written, then handed to the runner as its one
    library directory, the caller's own, with the dependency trees it carries as `methods_dirs`: the load reads the
    tree whole, its `.mthds` files as the method's bundles and every other file as one a step may read, such as a
    `PipeDocGen` template or a `PipeFunc` module, and names each by its tree path. A refusal while loading it is the
    caller's invalid method, a 422. With no `pipe_code`, the run starts at the protocol's entry pipe
    (`select_tree_entry`): the `main_pipe` of the manifest at the tree's root, else the one `main_pipe` its bundles
    declare. A `method_ref` is fetched and read from its commit's git objects (`pipelex_api.method_source`), its
    provenance riding back so the routes can put it on the response. The directory is removed when the run returns.

    Inline `mthds_contents` keep their path: the contents load as strings, and the files `resources` sends travel as
    the runtime's `submitted_files`.

    Security gate: a method shipping custom Python (`.py`) is only honored on a sandbox-hosted deployment, refused with
    a 501 before anything is written (`ensure_python_allowed`).
    """
    method_provenance: MethodProvenance | None = None
    method_label = REQUEST_METHOD_LABEL
    if run_request.method_ref is not None:
        fetched = await asyncio.to_thread(fetched_method, run_request.method_ref)
        request_method: RequestMethod | None = fetched.request_method
        ensure_method_holds_a_bundle(request_method=fetched.request_method, label=f"Method package {fetched.label}")
        ensure_python_allowed(request_method=fetched.request_method, label=f"Method package {fetched.label}", origin=CustomCodeOrigin.PACKAGE)
        method_provenance = fetched.provenance
        method_label = fetched.label
    else:
        request_method = await _request_method_of(run_request=run_request, body=body, blob_store=RunnerBlobStore.make_for_scope(scope=blob_scope))
    if request_method is None:
        yield _ResolvedRunSource(
            mthds_contents=run_request.mthds_contents,
            library_dirs=None,
            library_dirs_are_callers=False,
            methods_dirs=None,
            pipe_code=run_request.pipe_code,
            method_provenance=None,
            submitted_files=decode_bundle_resources(resources=run_request.resources),
        )
        return
    pipe_code = run_request.pipe_code or select_tree_entry(tree=request_method.tree, method_label=method_label).pipe_ref
    with written_method(request_method=request_method) as written:
        yield _ResolvedRunSource(
            mthds_contents=None,
            library_dirs=[str(written.method_dir)],
            library_dirs_are_callers=True,
            methods_dirs=written.methods_dirs,
            pipe_code=pipe_code,
            method_provenance=method_provenance,
            submitted_files=None,
        )


@router.post(
    "/execute",
    # Documented 200 = the run result with the WIRE-shaped `pipe_output`: the handler returns a
    # `JSONResponse` built from a trimmed dump, so FastAPI never serializes through this model —
    # it is purely what the artifact publishes, and it must match `apply_tokens_usage_wire_shape`.
    response_model=PipelexApiExecuteResponse,
    # On top of the composite router's shared 401/413/422/500: the `method_ref` package-not-found 404,
    # the provider rate-limit passthrough (429) — `/execute` is the only route that runs inference, so
    # it is the only one that can be rate-limited upstream — and the custom-code sandbox gate's 501 on a
    # bundle or a fetched package. NO 409: unlike `/start`, `/execute` takes no client-supplied
    # `pipeline_run_id` (the base runner generates one per call), so a caller cannot collide with an
    # in-flight run.
    responses={404: PROBLEM_404_METHOD_PACKAGE, 429: PROBLEM_429, 501: PROBLEM_501_RUN_POLICY},
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
    run_request, extras, body = await _parse_request(request)
    scopes = _resolve_run_scopes(request, extras=extras)
    blob_scope = resolve_blob_scope(request, read_scope=scopes.read_scope)
    async with _run_source(run_request=run_request, body=body, blob_scope=blob_scope) as source:
        runner = ApiRunner(
            user_id=get_request_user_id(request),
            storage_scope=scopes.storage_scope,
            read_scope=scopes.read_scope,
            extras=extras.analytics_groups,
            library_dirs=source.library_dirs,
            library_dirs_are_callers=source.library_dirs_are_callers,
            methods_dirs=source.methods_dirs,
            submitted_files=source.submitted_files,
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
    #   404 — a `method_ref` whose repository holds no matching package.
    #   409 — the submitted `pipeline_run_id` is still registered for an in-flight run.
    #   501 — the resolved orchestrator is blocking-only (the in-process `direct` base), or the
    #         deployment's async execution is not enabled: refuse honestly rather than block-and-ack,
    #         use `/execute`; or the custom-code sandbox gate on a bundle or a fetched package.
    responses={
        404: PROBLEM_404_METHOD_PACKAGE,
        409: PROBLEM_409_DUPLICATE_RUN,
        501: PROBLEM_501_START,
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
    parsed: Annotated[_ParsedRunRequest, Depends(_parse_request)],
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
    the in-process orchestrator is blocking-only, so `/start` is HONEST: it refuses with a `501`
    (`runtime.unsupported`) — use `/execute` — rather than silently blocking and acking.
    The completion callback (`callback_urls` / storage delivery) fires on the async path.
    """
    run_request, extras, body = parsed
    scopes = _resolve_run_scopes(request, extras=extras)
    blob_scope = resolve_blob_scope(request, read_scope=scopes.read_scope)
    # The run source is written out only for the synchronous setup phase: `start` builds the
    # PipeJob before it enqueues, its crate naming each method tree by digest, so the temp dir (a
    # tree's, sent or fetched) is no longer needed once `start` returns — cleanup on context
    # exit is safe for the async path. The worker reads a tree's files through its own method file
    # store, never from this directory: the orchestrator copies every tree the job's crate names
    # into that store before its `start` returns (`OrchestratorProtocol`), while this process's
    # library still serves them, and no orchestrator keeping a job running after `start` returned
    # may rely on this process's store.
    async with _run_source(run_request=run_request, body=body, blob_scope=blob_scope) as source:
        runner = ApiRunner(
            user_id=get_request_user_id(request),
            storage_scope=scopes.storage_scope,
            read_scope=scopes.read_scope,
            extras=extras.analytics_groups,
            library_dirs=source.library_dirs,
            library_dirs_are_callers=source.library_dirs_are_callers,
            methods_dirs=source.methods_dirs,
            submitted_files=source.submitted_files,
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
            callback_problem_view=problem_view_of(request),
        )
    # The ack plus this server's provenance extension: `(address, tag, commit_sha)` for a
    # `method_ref` run, null otherwise — the caller (and, on hosted, the platform's Run row)
    # learns exactly what was fetched and at which commit.
    return PipelexApiStartResponse(
        **dict(start_result),
        method_provenance=source.method_provenance,
    )
