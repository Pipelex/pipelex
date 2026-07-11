"""Boundary (de)serialization shared by the orchestrators.

Kept separate from the dispatch entry-point (``run_pipe_via_bridge``, now in the
closed ``pipelex-transport`` library) so the orchestrator implementations (DIRECT
in core, the distributed modes in the plugins) can serialize their ``PipeOutput``
into the JSON-safe ``PipelexPipeRunOutput`` without pulling the bootstrap path
(which would form an import cycle). This module is deliberately import-light: core
working-memory + the pipe-execution error types + ``payloads``; no bootstrap, no
plugin discovery, no host-runtime SDK.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pipelex.core.memory.working_memory import MAIN_STUFF_NAME
from pipelex.pipe_run.exceptions import PipeJobError, PipeRouterError, PipeRunError
from pipelex.pipeline.exceptions import PipeExecutionError, PipelineExecutionError
from pipelex.runtime_bridge.payloads import PipelexPipeRunOutput

if TYPE_CHECKING:
    from pipelex.base_exceptions import PipelexError
    from pipelex.core.pipes.pipe_output import PipeOutput


# Pipe-execution failures an orchestrator converts into PipelexBridgeDispatchError so a host can catch a
# single error type regardless of execution mode. The Temporal orchestrators additionally catch
# WorkflowExecutionError (lazy-imported there to keep temporal off the module import path); wrapping
# it with ``from exc`` loses no signal — the structured ErrorReport stays reachable via ``__cause__``
# and is surfaced by PipelexBridgeDispatchError.to_error_report()'s cause-chain enrichment.
PIPE_DISPATCH_ERRORS: tuple[type[PipelexError], ...] = (
    PipeRunError,
    PipeJobError,
    PipeRouterError,
    PipeExecutionError,
    PipelineExecutionError,
)


def serialize_pipe_output(pipe_output: PipeOutput) -> dict[str, Any]:
    """Dehydrate a PipeOutput's working memory to a JSON-safe dict.

    Always uses ``WorkingMemory.dump_for_transport()`` — the same format Pipelex
    uses internally for cross-process transit. The shape is stable regardless of
    whether a ``library_crate`` was attached:
    ``{"root": {stuff_name: {"content": {...}, ...}}, "aliases": {...}}``.

    Type metadata embedded by ``dump_for_transport`` lets callers reconstruct a
    typed ``WorkingMemory`` when they have the matching class registry in
    scope (e.g. via ``hydrate_working_memory``).
    """
    return pipe_output.working_memory.dump_for_transport()


def serialize_completed_output(
    pipe_output: PipeOutput,
    *,
    workflow_id: str | None,
) -> PipelexPipeRunOutput:
    output_dict = serialize_pipe_output(pipe_output=pipe_output)

    main_stuff_name = resolve_main_stuff_root_key(pipe_output=pipe_output)

    graph_spec_dump = pipe_output.graph_spec.model_dump(mode="json") if pipe_output.graph_spec is not None else None
    tokens_usages_dump = [usage.model_dump(mode="json") for usage in pipe_output.tokens_usages] if pipe_output.tokens_usages is not None else None

    return PipelexPipeRunOutput(
        output_dict=output_dict,
        main_stuff_name=main_stuff_name,
        pipeline_run_id=pipe_output.pipeline_run_id,
        workflow_id=workflow_id,
        graph_spec_dump=graph_spec_dump,
        graph_assembly_error=pipe_output.graph_assembly_error,
        tokens_usages_dump=tokens_usages_dump,
        usage_assembly_error=pipe_output.usage_assembly_error,
    )


def resolve_main_stuff_root_key(pipe_output: PipeOutput) -> str:
    """Return the key under which the run's resolved main result lives — always the declared slot.

    The main stuff can either sit directly at ``root[MAIN_STUFF_NAME]`` or be
    referenced via ``aliases[MAIN_STUFF_NAME]`` pointing at its real name.
    Callers indexing the output_dict need the actual root key, not the
    stuff's display ``stuff_name``.

    When the main output resolved as a recorded absence (an optional output that produced
    nothing), the returned key names the declared output slot and indexes the serialized
    ``absences`` ledger instead of ``root`` — consumers branch on the absence record, and
    the run stays a success.

    A completed run always resolves its declared output: a value or a recorded absence. A
    working memory with neither at this boundary is a contract violation and raises
    ``PipeJobError``.
    """
    working_memory = pipe_output.working_memory
    if MAIN_STUFF_NAME in working_memory.root:
        return MAIN_STUFF_NAME
    aliased_target = working_memory.aliases.get(MAIN_STUFF_NAME)
    if aliased_target is not None and aliased_target in working_memory.root:
        return aliased_target
    main_absence = working_memory.get_optional_absence(MAIN_STUFF_NAME)
    if main_absence is not None:
        return main_absence.variable_name
    msg = (
        f"Completed run '{pipe_output.pipeline_run_id}' resolved neither a main stuff nor a recorded absence in its "
        f"working memory — a completed run always resolves its declared output: a value or a recorded absence."
    )
    raise PipeJobError(msg)
