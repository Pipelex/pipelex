"""Temporal activity wrapper for graph assembly.

Thin ``@activity.defn`` wrapper around the framework-agnostic core in
``pipelex.runtime_bridge.primitives.graph_assembly``. The body is shared
with other host runtimes (e.g. Mistral Workflows).
"""

from pydantic import BaseModel
from temporalio import activity

from pipelex.graph.graphspec import GraphSpec
from pipelex.runtime_bridge.primitives.graph_assembly import assemble_graph_for_pipeline_run


class AssembleGraphArg(BaseModel):
    """Input for the graph assembly activity."""

    pipeline_run_id: str
    domain_code: str | None = None
    main_pipe_code: str | None = None


@activity.defn(name="act_assemble_graph")
async def act_assemble_graph(arg: AssembleGraphArg) -> GraphSpec | None:
    return await assemble_graph_for_pipeline_run(
        pipeline_run_id=arg.pipeline_run_id,
        domain_code=arg.domain_code,
        main_pipe_code=arg.main_pipe_code,
    )
