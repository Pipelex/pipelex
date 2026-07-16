"""End-to-end absent main output (Step E): a run whose declared `?` output resolves absent is a
first-class success on every in-repo surface — the execute response names the declared slot, the
working memory carries the provenance ledger, and the execution graph shows the lifted pipes as
`skipped` with their skip reasons.
"""

import json

import pytest

from pipelex.config import get_config
from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.graph.graphspec import NodeStatus
from pipelex.pipeline.pipeline_response import RunState
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.registries.func_registry import func_registry

_BUNDLE = """
domain = "opt_surfaces"
description = "Optional flow whose whole chain lifts when the optional input is omitted"
main_pipe = "opt_flow"

[pipe.opt_surfaces_make_analysis]
type = "PipeFunc"
description = "Analyzes the source (plain input: lifts when source is absent)"
inputs = { source = "Text" }
output = "Text"
function_name = "opt_surfaces_make_analysis"

[pipe.opt_surfaces_summarize]
type = "PipeFunc"
description = "Summarizes the analysis (plain input: lifts in chain)"
inputs = { analysis = "Text" }
output = "Text"
function_name = "opt_surfaces_summarize"

[pipe.opt_flow]
type = "PipeSequence"
description = "Whole chain lifts when source is absent; output declared optional"
inputs = { source = "Text?" }
output = "Text?"
steps = [
    { pipe = "opt_surfaces_make_analysis", result = "analysis" },
    { pipe = "opt_surfaces_summarize", result = "summary" },
]
"""


def opt_surfaces_make_analysis(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text=f"analysis of {working_memory.get_stuff_as_str(name='source')}")


def opt_surfaces_summarize(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text=f"summary: {working_memory.get_stuff_as_str(name='analysis')}")


_TEST_FUNCS = [opt_surfaces_make_analysis, opt_surfaces_summarize]


@pytest.mark.asyncio(loop_scope="class")
class TestAbsentMainOutputSurfaces:
    @classmethod
    def setup_class(cls):
        for func in _TEST_FUNCS:
            func_registry.register_function(func)

    @classmethod
    def teardown_class(cls):
        for func in _TEST_FUNCS:
            if func_registry.has_function(func.__name__):
                func_registry.unregister_function_by_name(func.__name__)

    async def test_execute_with_absent_main_output_succeeds_across_surfaces(self):
        """Omitting the optional input lifts the whole chain: the execute response is a success
        naming the declared slot, the ledger chains provenance, and the graph marks skips.
        """
        execution_config = get_config().pipelex.pipeline_execution_config.with_execution_overrides(generate_graph=True)
        runner = PipelexMTHDSProtocol(execution_config=execution_config)

        response = await runner.execute(mthds_contents=[_BUNDLE], inputs={})

        # Execute response: success with an absent result — main_stuff_name names the declared slot.
        assert response.state == RunState.COMPLETED
        assert response.main_stuff_name == "summary"

        memory = response.pipe_output.working_memory
        main_resolved = memory.resolve_main_stuff()
        assert isinstance(main_resolved, AbsenceRecord)
        assert main_resolved.kind == AbsenceKind.SKIPPED
        assert main_resolved.producing_pipe == "opt_surfaces_summarize"
        # Provenance chains back to the omitted method input.
        origin = main_resolved.origin()
        assert origin.variable_name == "source"
        assert origin.kind == AbsenceKind.NOT_PROVIDED

        # Graph: the lifted pipes are skipped with reasons; the controller succeeded.
        graph_spec = response.pipe_output.graph_spec
        assert graph_spec is not None
        nodes_by_code = {node.pipe_code: node for node in graph_spec.nodes}
        analysis_node = nodes_by_code["opt_surfaces_make_analysis"]
        assert analysis_node.status == NodeStatus.SKIPPED
        assert analysis_node.skip_reason is not None
        assert "source" in analysis_node.skip_reason
        summary_node = nodes_by_code["opt_surfaces_summarize"]
        assert summary_node.status == NodeStatus.SKIPPED
        assert summary_node.skip_reason is not None
        assert "analysis" in summary_node.skip_reason
        assert nodes_by_code["opt_flow"].status == NodeStatus.SUCCEEDED

        # The skipped state serializes on the wire.
        graph_dump = json.loads(graph_spec.to_json())
        statuses = {node["pipe_code"]: node["status"] for node in graph_dump["nodes"]}
        assert statuses["opt_surfaces_make_analysis"] == "skipped"

    async def test_execute_with_source_runs_the_full_chain(self):
        """With the optional input provided, nothing lifts and the chain delivers a value."""
        runner = PipelexMTHDSProtocol()

        response = await runner.execute(mthds_contents=[_BUNDLE], inputs={"source": "clause 12"})

        assert response.state == RunState.COMPLETED
        assert response.pipe_output.main_stuff.as_text.text == "summary: analysis of clause 12"
        assert response.pipe_output.working_memory.absences == {}
