"""Framework-agnostic Pipelex runtime-bridge surface for host runtimes.

This module contains the boundary types (``PipelexPipeRunInput`` /
``PipelexPipeRunOutput``) and the dispatch entry-point
(``run_pipe_via_bridge``) used by host runtimes (Mistral Workflows, raw
Temporal, future plugins) to invoke Pipelex pipes from inside their own
activities. It deliberately does NOT import any host-runtime-specific
modules at module top-level so that callers can use the bridge directly
(Tier 3 usage) and so that unit tests can exercise it without optional
host-runtime deps installed.

The Temporal extra is lazy-imported only inside the temporal-mode branches.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncGenerator, Callable, cast
from uuid import uuid4

import shortuuid
from kajson.class_registry import ClassRegistry
from kajson.kajson_manager import KajsonManager
from pydantic import BaseModel, ConfigDict, Field

from pipelex.core.memory.working_memory import MAIN_STUFF_NAME
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.hub import (
    get_library_manager,
    get_required_pipe,
    scoped_current_library,
    scoped_pipe_router,
)
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
from pipelex.pipe_run.exceptions import PipeJobError, PipeRouterError, PipeRunError
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_router import PipeRouter
from pipelex.pipe_run.pipe_run import PipeRun
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.exceptions import PipeExecutionError, PipelineExecutionError
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.runtime_bridge.bootstrap import ensure_pipelex_booted
from pipelex.runtime_bridge.exceptions import (
    MissingMistralWorkflowsPluginError,
    MissingPipelexTemporalExtraError,
    PipelexBridgeDispatchError,
)
from pipelex.runtime_bridge.execution_mode import PipelexExecutionMode
from pipelex.system.telemetry.otel_constants import OTelConstants

if TYPE_CHECKING:
    from pipelex.core.memory.working_memory import WorkingMemory
    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.graph.graph_context import GraphContext
    from pipelex.pipe_run.pipe_job import PipeJob
    from pipelex.pipe_run.pipe_run_protocol import PipeRunProtocol


class PipelexPipeRunInput(BaseModel):
    """JSON-safe input crossing the host-runtime / Temporal boundary."""

    model_config = ConfigDict(extra="forbid")

    pipe_code: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    output_name: str | None = None
    pipeline_run_id: str | None = None
    user_id: str | None = None
    library_crate_dump: dict[str, Any] | None = None
    execution_mode: PipelexExecutionMode = PipelexExecutionMode.DIRECT
    delivery_assignment_dump: dict[str, Any] | None = None


class PipelexPipeRunOutput(BaseModel):
    """JSON-safe output crossing the host-runtime / Temporal boundary."""

    model_config = ConfigDict(extra="forbid")

    output_dict: dict[str, Any]
    main_stuff_name: str | None = None
    pipeline_run_id: str
    workflow_id: str | None = None
    is_completed: bool
    graph_spec_dump: dict[str, Any] | None = None


async def run_pipe_via_bridge(
    input_payload: PipelexPipeRunInput,
    graph_context: GraphContext | None = None,
) -> PipelexPipeRunOutput:
    """Run a Pipelex pipe from inside a host-runtime activity.

    Booting Pipelex on first call (no-op if already initialized); validating
    the input; opening a per-call scoped library if a ``library_crate_dump``
    is provided; then dispatching to the requested execution mode.

    The optional ``graph_context`` is plumbed into ``JobMetadata`` so callers
    (e.g. a streaming activity) that already opened a ``GraphTracerManager``
    tracer for this pipeline run get per-step trace events flowing through
    the configured event log. ``graph_context`` is honored for ``DIRECT``
    mode only — it is deliberately nulled for the Temporal modes, which have
    their own event-log infrastructure via ``pipeline_run_setup``. Forwarding
    a host ``graph_context`` to a Temporal mode would make Pipelex's Temporal
    workflow open its tracer under the host's graph id and merge its trace
    events into the host's graph, so the bridge does not thread it through.
    """
    ensure_pipelex_booted()
    _validate_input(input_payload)

    library_crate = _decode_library_crate(input_payload.library_crate_dump)
    delivery_assignment = _decode_delivery_assignment(input_payload.delivery_assignment_dump)

    async with _scoped_library_for_crate(library_crate):
        # graph_context is honored for DIRECT only. The Temporal modes have their
        # own event-log infrastructure (via pipeline_run_setup); forwarding a host
        # graph_context there would make WfPipeRouter open its tracer under the
        # host's graph_id and merge Pipelex's Temporal trace events into the host
        # graph — exactly the cross-contamination the contract forbids. Null it
        # for the non-DIRECT modes.
        is_direct = input_payload.execution_mode is PipelexExecutionMode.DIRECT
        pipe_job = build_pipe_job_from_input(
            input_payload=input_payload,
            library_crate=library_crate,
            graph_context=graph_context if is_direct else None,
        )

        match input_payload.execution_mode:
            case PipelexExecutionMode.DIRECT:
                return await _run_direct(pipe_job=pipe_job, delivery_assignment=delivery_assignment)
            case PipelexExecutionMode.TEMPORAL_BLOCKING:
                _require_pipelex_temporal_extra()
                return await _run_temporal_blocking(pipe_job=pipe_job, delivery_assignment=delivery_assignment)
            case PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET:
                _require_pipelex_temporal_extra()
                return await _run_temporal_fire_and_forget(pipe_job=pipe_job, delivery_assignment=delivery_assignment)
            case PipelexExecutionMode.MISTRAL_NATIVE:
                return await _run_mistral_native(pipe_job=pipe_job, delivery_assignment=delivery_assignment)


def build_pipe_job_from_input(
    input_payload: PipelexPipeRunInput,
    library_crate: LibraryCrate | None,
    graph_context: GraphContext | None = None,
) -> PipeJob:
    """Hydrate a PipeJob from JSON-safe input.

    Looks up the pipe in the active library; the caller is responsible for
    making sure the active library contains the pipe (by passing a
    ``library_crate_dump`` or pre-loading the library at boot).

    The optional ``graph_context`` is plumbed into ``JobMetadata`` so a
    caller (e.g. a streaming activity) that has already opened a
    ``GraphTracerManager`` tracer for this pipeline run can have per-step
    ``PipeStartEvent`` / ``PipeEndSuccessEvent`` events flow through the
    pipe execution. When ``None``, no tracing happens (current default).
    """
    pipe = get_required_pipe(pipe_code=input_payload.pipe_code)

    pipeline_run_id = input_payload.pipeline_run_id or shortuuid.uuid()

    working_memory: WorkingMemory
    if input_payload.inputs:
        working_memory = WorkingMemoryFactory.make_from_pipeline_inputs(
            pipeline_inputs=input_payload.inputs,
            search_domain_codes=[pipe.domain_code],
        )
    else:
        working_memory = WorkingMemoryFactory.make_empty()

    job_metadata = JobMetadata(
        user_id=input_payload.user_id or OTelConstants.DEFAULT_USER_ID,
        pipeline_run_id=pipeline_run_id,
        graph_context=graph_context,
    )
    pipe_run_params = PipeRunParamsFactory.make_run_params()

    return PipeJobFactory.make_pipe_job(
        pipe=pipe,
        pipe_run_params=pipe_run_params,
        job_metadata=job_metadata,
        working_memory=working_memory,
        output_name=input_payload.output_name,
        library_crate=library_crate,
    )


def serialize_pipe_output(pipe_output: PipeOutput) -> dict[str, Any]:
    """Dehydrate a PipeOutput's working memory to a JSON-safe dict.

    Always uses ``WorkingMemory.dump_for_temporal()`` — the same format Pipelex
    uses internally for Temporal transit. The shape is stable regardless of
    whether a ``library_crate`` was attached:
    ``{"root": {stuff_name: {"content": {...}, ...}}, "aliases": {...}}``.

    Type metadata embedded by ``dump_for_temporal`` lets callers reconstruct a
    typed ``WorkingMemory`` when they have the matching class registry in
    scope (e.g. via ``hydrate_working_memory``).
    """
    return pipe_output.working_memory.dump_for_temporal()


def _validate_input(input_payload: PipelexPipeRunInput) -> None:
    if input_payload.execution_mode is PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET:
        delivery_assignment = _decode_delivery_assignment(input_payload.delivery_assignment_dump)
        if delivery_assignment is None or not delivery_assignment.has_delivery_target:
            msg = (
                "PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET requires a delivery_assignment_dump with at least one "
                "delivery target (storage or a webhook); otherwise the pipe completion would be silently dropped."
            )
            raise PipelexBridgeDispatchError(msg)


def _decode_library_crate(library_crate_dump: dict[str, Any] | None) -> LibraryCrate | None:
    if library_crate_dump is None:
        return None
    return LibraryCrate.model_validate(library_crate_dump)


def _decode_delivery_assignment(delivery_assignment_dump: dict[str, Any] | None) -> DeliveryAssignment | None:
    if delivery_assignment_dump is None:
        return None
    return DeliveryAssignment.model_validate(delivery_assignment_dump)


@asynccontextmanager
async def _scoped_library_for_crate(library_crate: LibraryCrate | None) -> AsyncGenerator[str | None, None]:  # noqa: RUF029
    """Open a per-call scoped library for the duration of a pipe run.

    When ``library_crate`` is None, this is a no-op: callers fall back to the
    library that was loaded into the active class registry at boot. When
    provided, opens a fresh library, loads the crate into it, sets it as the
    current library for the duration of the pipe execution, and tears it down
    on the way out.
    """
    if library_crate is None:
        yield None
        return

    library_manager = get_library_manager()
    library_id = f"runtime_bridge_{uuid4().hex[:8]}"

    # Pre-seed a per-call ClassRegistry from the global one so classes generated
    # from the crate's inline structured concepts register into this scoped
    # registry (discarded on teardown) rather than leaking into / colliding in
    # the global Kajson registry. Mirrors the Temporal worker hydration path
    # (see wf_pipe_router.py).
    global_registry = KajsonManager.get_class_registry()
    scoped_registry = ClassRegistry()
    scoped_registry.register_classes_dict(global_registry.get_classes_dict())
    _opened_library_id, library = library_manager.open_library(library_id=library_id)
    library.set_class_registry(scoped_registry)
    try:
        # scoped_current_library captures and restores the prior current-library
        # ContextVar, so a bridge call made from within an already-scoped library
        # doesn't clobber the caller's context.
        with scoped_current_library(library_id=library_id):
            library_manager.load_from_crate(library_id=library_id, crate=library_crate)
            yield library_id
    finally:
        library_manager.teardown(library_id=library_id)


async def _run_direct(
    pipe_job: PipeJob,
    delivery_assignment: DeliveryAssignment | None,
) -> PipelexPipeRunOutput:
    # DIRECT mode forces in-process execution even inside a Temporal-enabled
    # worker. Scope the in-process router as the active router for the WHOLE
    # run so nested controller sub-pipes — which dispatch through
    # get_pipe_router() — resolve THIS router rather than falling back to the
    # hub default. Without the scope, the hub default in a Temporal-enabled
    # worker is the Temporal router, so a DIRECT-mode sequence/batch would leak
    # its nested pipes to Temporal, defeating the point of DIRECT.
    direct_router = PipeRouter()
    with scoped_pipe_router(direct_router):
        pipe_run = PipeRun(pipe_router=direct_router)
        try:
            pipe_output = await pipe_run.run(pipe_job=pipe_job, delivery_assignment=delivery_assignment)
        except (PipeRunError, PipeJobError, PipeRouterError, PipeExecutionError, PipelineExecutionError) as exc:
            msg = f"Pipe execution failed in DIRECT mode for pipe '{pipe_job.pipe.code}': {exc}"
            raise PipelexBridgeDispatchError(msg) from exc

    return _serialize_completed_output(
        pipe_output=pipe_output,
        pipe_job=pipe_job,
        workflow_id=None,
    )


async def _run_temporal_blocking(
    pipe_job: PipeJob,
    delivery_assignment: DeliveryAssignment | None,
) -> PipelexPipeRunOutput:
    from pipelex.temporal.tprl_pipe.temporal_pipe_run import make_temporal_pipe_run  # noqa: PLC0415

    temporal_pipe_run = make_temporal_pipe_run()
    try:
        pipe_output = await temporal_pipe_run.run(pipe_job=pipe_job, delivery_assignment=delivery_assignment)
    except (PipeRunError, PipeJobError, PipeRouterError, PipeExecutionError, PipelineExecutionError) as exc:
        msg = f"Pipe execution failed in TEMPORAL_BLOCKING mode for pipe '{pipe_job.pipe.code}': {exc}"
        raise PipelexBridgeDispatchError(msg) from exc

    return _serialize_completed_output(
        pipe_output=pipe_output,
        pipe_job=pipe_job,
        workflow_id=pipe_output.pipeline_run_id,
    )


async def _run_temporal_fire_and_forget(
    pipe_job: PipeJob,
    delivery_assignment: DeliveryAssignment | None,
) -> PipelexPipeRunOutput:
    from pipelex.temporal.tprl_pipe.temporal_pipe_run import make_temporal_pipe_run  # noqa: PLC0415

    temporal_pipe_run = make_temporal_pipe_run()
    try:
        workflow_id, _handle = await temporal_pipe_run.start(pipe_job=pipe_job, delivery_assignment=delivery_assignment)
    except (PipeRunError, PipeJobError, PipeRouterError, PipeExecutionError, PipelineExecutionError) as exc:
        msg = f"Pipe dispatch failed in TEMPORAL_FIRE_AND_FORGET mode for pipe '{pipe_job.pipe.code}': {exc}"
        raise PipelexBridgeDispatchError(msg) from exc

    return PipelexPipeRunOutput(
        output_dict={},
        main_stuff_name=None,
        pipeline_run_id=pipe_job.job_metadata.pipeline_run_id,
        workflow_id=workflow_id,
        is_completed=False,
        graph_spec_dump=None,
    )


def _serialize_completed_output(
    pipe_output: PipeOutput,
    pipe_job: PipeJob,  # noqa: ARG001 — kept for symmetry with future per-crate serialization tweaks
    workflow_id: str | None,
) -> PipelexPipeRunOutput:
    output_dict = serialize_pipe_output(pipe_output=pipe_output)

    main_stuff_name = _resolve_main_stuff_root_key(pipe_output=pipe_output)

    graph_spec_dump = pipe_output.graph_spec.model_dump(mode="json") if pipe_output.graph_spec is not None else None

    return PipelexPipeRunOutput(
        output_dict=output_dict,
        main_stuff_name=main_stuff_name,
        pipeline_run_id=pipe_output.pipeline_run_id,
        workflow_id=workflow_id,
        is_completed=True,
        graph_spec_dump=graph_spec_dump,
    )


def _resolve_main_stuff_root_key(pipe_output: PipeOutput) -> str | None:
    """Return the actual ``root`` dict key under which the main stuff lives.

    The main stuff can either sit directly at ``root[MAIN_STUFF_NAME]`` or be
    referenced via ``aliases[MAIN_STUFF_NAME]`` pointing at its real name.
    Callers indexing the output_dict need the actual root key, not the
    stuff's display ``stuff_name``.
    """
    working_memory = pipe_output.working_memory
    if MAIN_STUFF_NAME in working_memory.root:
        return MAIN_STUFF_NAME
    aliased_target = working_memory.aliases.get(MAIN_STUFF_NAME)
    if aliased_target is not None and aliased_target in working_memory.root:
        return aliased_target
    return None


def _require_pipelex_temporal_extra() -> None:
    try:
        import temporalio  # noqa: F401, PLC0415
    except ImportError as exc:
        msg = "TEMPORAL_* execution modes require the pipelex[temporal] extra. Install with: pip install 'pipelex[temporal]'"
        raise MissingPipelexTemporalExtraError(msg) from exc


async def _run_mistral_native(
    pipe_job: PipeJob,
    delivery_assignment: DeliveryAssignment | None,
) -> PipelexPipeRunOutput:
    try:
        from pipelex_mistralai_workflows.primitives.pipe_run import (  # type: ignore[import-not-found]  # noqa: PLC0415  # pyright: ignore[reportMissingImports]
            make_mistral_workflows_pipe_run as _make_pipe_run_untyped,  # pyright: ignore[reportUnknownVariableType]
        )
    except ImportError as exc:
        msg = (
            "PipelexExecutionMode.MISTRAL_NATIVE requires the pipelex-mistralai-workflows "
            "package. Install with: pip install pipelex-mistralai-workflows"
        )
        raise MissingMistralWorkflowsPluginError(msg) from exc

    make_pipe_run = cast("Callable[[], PipeRunProtocol]", _make_pipe_run_untyped)
    pipe_run = make_pipe_run()
    try:
        pipe_output = await pipe_run.run(pipe_job=pipe_job, delivery_assignment=delivery_assignment)
    except (PipeRunError, PipeJobError, PipeRouterError, PipeExecutionError, PipelineExecutionError) as exc:
        msg = f"Pipe execution failed in MISTRAL_NATIVE mode for pipe '{pipe_job.pipe.code}': {exc}"
        raise PipelexBridgeDispatchError(msg) from exc

    return _serialize_completed_output(
        pipe_output=pipe_output,
        pipe_job=pipe_job,
        workflow_id=pipe_output.pipeline_run_id,
    )
