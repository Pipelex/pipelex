"""Framework-agnostic Pipelex runtime-bridge surface for host runtimes.

This module re-exports the boundary types (``PipelexPipeRunInput`` /
``PipelexPipeRunOutput``, defined in ``payloads.py``) and holds the dispatch
entry-point (``run_pipe_via_bridge``) used by host runtimes (Mistral Workflows, raw
Temporal, future plugins) to invoke Pipelex pipes from inside their own
activities. It deliberately does NOT import any host-runtime-specific
modules at module top-level so that callers can use the bridge directly
(Tier 3 usage) and so that unit tests can exercise it without optional
host-runtime deps installed.

Dispatch is by orchestration mode through the ``OrchestratorRegistry`` (on the hub):
the bridge resolves the orchestrator for the requested token and calls its ``run``,
passing the ``delivery`` axis (BLOCKING vs FIRE_AND_FORGET) the orchestrator honors per
its nature. It names no integration — ``"direct"`` is contributed by a core plugin,
``"temporal"`` by the external ``pipelex-temporal`` plugin,
``"mistralai-workflows"`` by the external ``pipelex-mistralai-workflows`` plugin. A mode
with no registered orchestrator raises a generic ``MissingOrchestratorError``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import shortuuid
from pydantic import ValidationError

from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.hub import get_orchestrator_registry, get_required_pipe
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.runtime_bridge.bootstrap import ensure_pipelex_booted
from pipelex.runtime_bridge.delivery_mode import DeliveryMode
from pipelex.runtime_bridge.exceptions import MissingOrchestratorError, PipelexBridgeDispatchError
from pipelex.runtime_bridge.orchestration_mode import DIRECT_ORCHESTRATION_MODE
from pipelex.runtime_bridge.payloads import (  # noqa: TC001 — re-exported at runtime for host-runtime back-compat
    PipelexPipeRunInput,
    PipelexPipeRunOutput,
)
from pipelex.runtime_bridge.primitives.scoped_library import scoped_library_for_crate
from pipelex.runtime_bridge.serialization import serialize_pipe_output  # noqa: F401 — re-exported for the orchestrator SPI / host-runtime back-compat
from pipelex.system.telemetry.otel_constants import OTelConstants

if TYPE_CHECKING:
    from pipelex.core.memory.working_memory import WorkingMemory
    from pipelex.graph.trace_context import TraceContext
    from pipelex.pipe_run.pipe_job import PipeJob
    from pipelex.plugins.orchestrator_registry import OrchestratorProtocol


async def run_pipe_via_bridge(
    input_payload: PipelexPipeRunInput,
    *,
    trace_context: TraceContext | None = None,
) -> PipelexPipeRunOutput:
    """Run a Pipelex pipe from inside a host-runtime activity.

    Booting Pipelex on first call (no-op if already initialized); validating
    the input; opening a per-call scoped library if a ``library_crate_dump``
    is provided; then dispatching to the requested orchestration mode.

    The optional ``trace_context`` is plumbed into ``JobMetadata`` so callers
    (e.g. a streaming activity) that already opened a ``GraphTracerManager``
    tracer for this pipeline run get per-step graph/usage trace events flowing
    through the configured event log. ``trace_context`` is honored for the
    ``"direct"`` mode only — it is deliberately nulled for a distributed mode
    (e.g. ``"temporal"``), which has its own event-log infrastructure via
    ``pipeline_run_setup``. Forwarding a host ``trace_context`` to such a mode
    would make its workflow open its tracer under the host's graph id and merge
    its trace events into the host's graph, so the bridge does not thread it through.
    """
    ensure_pipelex_booted()

    library_crate = _decode_library_crate(input_payload.library_crate_dump)
    delivery_assignment = _decode_delivery_assignment(input_payload.delivery_assignment_dump)

    # Resolve the orchestrator up front so _validate_input can reject an impossible
    # (mode, delivery) pair — fire-and-forget on a blocking-only orchestrator — before opening
    # the scoped library or building the pipe job for a doomed request. This is the Tier-3
    # counterpart of the /start endpoint's capability check.
    orchestrator = get_orchestrator_registry().get_optional(mode=input_payload.orchestration_mode)
    if orchestrator is None:
        raise MissingOrchestratorError(mode=input_payload.orchestration_mode)
    _validate_input(input_payload, orchestrator=orchestrator, delivery_assignment=delivery_assignment)

    with scoped_library_for_crate(library_crate, library_id_prefix="runtime_bridge"):
        # trace_context is honored for the "direct" mode only. A distributed mode has its
        # own event-log infrastructure (via pipeline_run_setup); forwarding a host
        # trace_context there would make WfPipeRouter open its tracer under the
        # host's graph_id and merge the distributed trace events into the host
        # graph — exactly the cross-contamination the contract forbids. Null it
        # for the non-"direct" modes.
        is_direct = input_payload.orchestration_mode == DIRECT_ORCHESTRATION_MODE
        pipe_job = build_pipe_job_from_input(
            input_payload=input_payload,
            library_crate=library_crate,
            trace_context=trace_context if is_direct else None,
        )
        return await orchestrator.run(pipe_job=pipe_job, delivery_assignment=delivery_assignment, delivery=input_payload.delivery)


def build_pipe_job_from_input(
    input_payload: PipelexPipeRunInput,
    *,
    library_crate: LibraryCrate | None,
    trace_context: TraceContext | None = None,
) -> PipeJob:
    """Hydrate a PipeJob from JSON-safe input.

    Looks up the pipe in the active library; the caller is responsible for
    making sure the active library contains the pipe (by passing a
    ``library_crate_dump`` or pre-loading the library at boot).

    The optional ``trace_context`` is plumbed into ``JobMetadata`` so a
    caller (e.g. a streaming activity) that has already opened a
    ``GraphTracerManager`` tracer for this pipeline run can have per-step
    ``PipeStartEvent`` / ``PipeEndSuccessEvent`` events flow through the
    pipe execution. When ``None``, no tracing happens (current default).
    """
    pipe = get_required_pipe(pipe_code=input_payload.pipe_code)

    # When the caller supplies a trace_context but no explicit pipeline_run_id, adopt the
    # trace_context's lookup_key (= tracer_key or graph_id) as the run id. lookup_key is the key the
    # caller's already-open tracer is registered under in GraphTracerManager AND the key PipeRun.run
    # closes it under (close_tracer takes pipeline_run_id); minting a fresh id would leak the tracer.
    #
    # On every reachable path lookup_key == graph_id, so it is also the partition tracing_assembly
    # reads under: only the Temporal child path (wf_pipe_router) opens a tracer with tracer_key !=
    # graph_id, and it never routes through the bridge — non-DIRECT modes null trace_context, and it
    # builds its PipeJob directly, not via this function. A host that hand-built a divergent keyed
    # trace_context and forced it through DIRECT would split event emission (under graph_id) from
    # assembly (under tracer_key); nothing constructs that, and it is documented as unsupported in
    # wip/runtime-bridge/bridge-keyed-tracer-unsupported.md (graph_id "is typically the pipeline run id").
    if input_payload.pipeline_run_id is not None:
        pipeline_run_id = input_payload.pipeline_run_id
    elif trace_context is not None:
        pipeline_run_id = trace_context.lookup_key
    else:
        pipeline_run_id = shortuuid.uuid()

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
        trace_context=trace_context,
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


def _validate_input(
    input_payload: PipelexPipeRunInput, *, orchestrator: OrchestratorProtocol, delivery_assignment: DeliveryAssignment | None
) -> None:
    if input_payload.delivery is DeliveryMode.FIRE_AND_FORGET:
        # Capability gate first: a blocking-only orchestrator (e.g. the core "direct" mode) has no
        # genuine async path — it would run the pipe to completion and return is_completed=True while
        # never invoking the delivery target, i.e. block the caller AND falsely ack. Reject honestly
        # regardless of whether a target was supplied (the mode, not the target, is the problem).
        if not orchestrator.supports_fire_and_forget:
            msg = (
                f"Orchestration mode '{input_payload.orchestration_mode}' cannot honor fire-and-forget delivery: "
                "its orchestrator runs in-process and always blocks until completion. Use blocking delivery, or "
                "request an async-capable orchestration mode (e.g. 'temporal')."
            )
            raise PipelexBridgeDispatchError(msg)
        if delivery_assignment is None or not delivery_assignment.has_delivery_target:
            msg = (
                "Fire-and-forget delivery requires a delivery_assignment_dump with at least one "
                "delivery target (storage or a webhook); otherwise the pipe completion would be silently dropped."
            )
            raise PipelexBridgeDispatchError(msg)


def _decode_library_crate(library_crate_dump: dict[str, Any] | None) -> LibraryCrate | None:
    if library_crate_dump is None:
        return None
    try:
        return LibraryCrate.model_validate(library_crate_dump)
    except ValidationError as exc:
        msg = f"Invalid library_crate_dump passed to the runtime bridge: {exc}"
        raise PipelexBridgeDispatchError(msg) from exc


def _decode_delivery_assignment(delivery_assignment_dump: dict[str, Any] | None) -> DeliveryAssignment | None:
    if delivery_assignment_dump is None:
        return None
    try:
        return DeliveryAssignment.model_validate(delivery_assignment_dump)
    except ValidationError as exc:
        msg = f"Invalid delivery_assignment_dump passed to the runtime bridge: {exc}"
        raise PipelexBridgeDispatchError(msg) from exc
