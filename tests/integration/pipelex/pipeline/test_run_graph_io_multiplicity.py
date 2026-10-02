"""A run-produced graph marks every list-valued stuff as a list, on both graph builders.

The io items a run writes carry `multiplicity: True` exactly when the stuff is a list, read off the
value the runtime holds: a method input declared `Text[]`, an output declared `Record[]`, a batch's
aggregate, a step run with `nb_output`, a parallel's list-valued branch output, and a lifted plural
output's empty list. A batch's item and every single value carry no multiplicity. A stuff reads the
same on its producer's io item and on its consumers'.

Each run is read through both builders at once: the GraphSpec the run returns is the event-replay
`GraphSpecAssembler`'s, and the in-process `GraphTracer`'s is captured from its teardown.
"""

from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.graph.graph_tracer import GraphTracer
from pipelex.graph.graphspec import GraphSpec, IOSpec, NodeSpec, NodeStatus
from pipelex.pipeline.dry_run_pipeline import dry_run_pipeline
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.runtime_hub import scoped_event_log
from pipelex.system.registries.func_registry import func_registry
from pipelex.tracing.in_memory_event_log import InMemoryEventLog

_DRY_BUNDLE = '''
domain = "io_multiplicity_dry"
description = "Every way a run makes a list, and the single values around them"
main_pipe = "process_documents"

[concept.Record]
description = "A record extracted from the documents"

[concept.Record.structure]
title = { type = "text", description = "The record's title" }

[pipe.process_documents]
type = "PipeSequence"
description = "Extract, batch, brainstorm, fan out, conclude"
inputs = { documents = "Text[]" }
output = "Text"
steps = [
  { pipe = "extract_records", result = "records" },
  { pipe = "summarize_record", batch_over = "records", batch_as = "record", result = "summaries" },
  { pipe = "brainstorm", result = "ideas", nb_output = 3 },
  { pipe = "assess", result = "assessment" },
  { pipe = "conclude", result = "conclusion" },
]

[pipe.extract_records]
type = "PipeLLM"
description = "A declared list output"
inputs = { documents = "Text[]" }
output = "Record[]"
prompt = """
Extract the records from these documents:

@documents
"""

[pipe.summarize_record]
type = "PipeLLM"
description = "The batch's body, run once per record"
inputs = { record = "Record" }
output = "Text"
prompt = "Summarize $record"

[pipe.brainstorm]
type = "PipeLLM"
description = "A single output made a list by the step's nb_output"
inputs = { summaries = "Text[]" }
output = "Text"
prompt = """
Brainstorm an idea from these summaries:

@summaries
"""

[pipe.assess]
type = "PipeParallel"
description = "One list-valued branch and one single-valued branch"
inputs = { ideas = "Text[]" }
output = "Composite"
add_each_output = true
branches = [
  { pipe = "list_risks", result = "risks" },
  { pipe = "pick_idea", result = "pick" },
]

[pipe.list_risks]
type = "PipeLLM"
description = "A list-valued branch"
inputs = { ideas = "Text[]" }
output = "Text[]"
prompt = """
List the risks of these ideas:

@ideas
"""

[pipe.pick_idea]
type = "PipeLLM"
description = "A single-valued branch"
inputs = { ideas = "Text[]" }
output = "Text"
prompt = """
Pick the best of these ideas:

@ideas
"""

[pipe.conclude]
type = "PipeLLM"
description = "Consumes the branch outputs"
inputs = { risks = "Text[]", pick = "Text" }
output = "Text"
prompt = """
Conclude on $pick given these risks:

@risks
"""
'''

_LIFT_BUNDLE = """
domain = "io_multiplicity_lift"
description = "Plural outputs lifted to empty lists when the optional source is absent"
main_pipe = "lift_flow"

[pipe.lift_flow]
type = "PipeSequence"
description = "Lifts its first two steps, then counts what they left"
inputs = { source = "Text?" }
output = "Text"
steps = [
  { pipe = "find_many", result = "findings" },
  { pipe = "branch_out", result = "combined" },
  { pipe = "count_findings", result = "report" },
]

[pipe.find_many]
type = "PipeFunc"
description = "A plural output: lifted to an empty list"
inputs = { source = "Text" }
output = "Text[]"
function_name = "io_multiplicity_find_many"

[pipe.branch_out]
type = "PipeParallel"
description = "Lifted wholesale: its plural branch slot becomes an empty list"
inputs = { source = "Text" }
output = "Composite"
add_each_output = true
branches = [
  { pipe = "find_one", result = "one_out" },
  { pipe = "find_many_again", result = "many_out" },
]

[pipe.find_one]
type = "PipeFunc"
description = "A singular branch"
inputs = { source = "Text" }
output = "Text"
function_name = "io_multiplicity_find_one"

[pipe.find_many_again]
type = "PipeFunc"
description = "A plural branch"
inputs = { source = "Text" }
output = "Text[]"
function_name = "io_multiplicity_find_many"

[pipe.count_findings]
type = "PipeFunc"
description = "Consumes the lifted lists"
inputs = { findings = "Text[]", many_out = "Text[]", one_out = "Text?" }
output = "Text"
function_name = "io_multiplicity_count_findings"
"""


def io_multiplicity_find_many(working_memory: WorkingMemory) -> ListContent[TextContent]:
    return ListContent[TextContent](items=[TextContent(text=f"found:{working_memory.get_stuff_as_str(name='source')}")])


def io_multiplicity_find_one(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text=f"found:{working_memory.get_stuff_as_str(name='source')}")


def io_multiplicity_count_findings(working_memory: WorkingMemory) -> TextContent:
    findings = working_memory.get_stuff(name="findings").content
    many_out = working_memory.get_stuff(name="many_out").content
    assert isinstance(findings, ListContent)
    assert isinstance(many_out, ListContent)
    return TextContent(text=f"{findings.nb_items} findings, {many_out.nb_items} more")


_TEST_FUNCS = [io_multiplicity_find_many, io_multiplicity_find_one, io_multiplicity_count_findings]


def _io_items(graph: GraphSpec) -> list[tuple[NodeSpec, IOSpec]]:
    return [(node, io_spec) for node in graph.nodes for io_spec in [*node.node_io.inputs, *node.node_io.outputs]]


def _assert_one_reading_per_stuff(graph: GraphSpec) -> None:
    """A stuff reads the same on every io item that names it, and only ever `True` or `None`."""
    readings: dict[str, set[Any]] = {}
    for _, io_spec in _io_items(graph):
        assert io_spec.multiplicity in {True, None}, f"{io_spec.name}: a run never writes a count, got {io_spec.multiplicity!r}"
        if io_spec.digest is not None:
            readings.setdefault(io_spec.digest, set()).add(io_spec.multiplicity)
    disagreeing = {digest: values for digest, values in readings.items() if len(values) > 1}
    assert not disagreeing, f"io items disagree on a stuff's multiplicity: {disagreeing}"


def _multiplicities(graph: GraphSpec, *, pipe_code: str, direction: str, name: str) -> set[Any]:
    """Every multiplicity written for the io item `name` on the nodes of `pipe_code`."""
    found: set[Any] = set()
    for node in graph.nodes:
        if node.pipe_code != pipe_code:
            continue
        io_specs = node.node_io.inputs if direction == "input" else node.node_io.outputs
        found.update(io_spec.multiplicity for io_spec in io_specs if io_spec.name == name)
    assert found, f"no {direction} named '{name}' on '{pipe_code}'"
    return found


def _in_process_graph(teardown_spy: Any) -> GraphSpec:
    """The one GraphSpec the in-process tracer built during the run."""
    graphs = [graph for graph in teardown_spy.spy_return_list if isinstance(graph, GraphSpec)]
    assert len(graphs) == 1
    return graphs[0]


@pytest.mark.asyncio(loop_scope="class")
class TestRunGraphIoMultiplicity:
    @classmethod
    def setup_class(cls):
        for func in _TEST_FUNCS:
            func_registry.register_function(func)

    @classmethod
    def teardown_class(cls):
        for func in _TEST_FUNCS:
            if func_registry.has_function(func.__name__):
                func_registry.unregister_function_by_name(func.__name__)

    async def test_dry_run_marks_every_list(self, mocker: MockerFixture) -> None:
        teardown_spy = mocker.spy(GraphTracer, "teardown")

        assembled_graph, _ = await dry_run_pipeline(mthds_contents=[_DRY_BUNDLE])
        in_process_graph = _in_process_graph(teardown_spy)

        for graph in (assembled_graph, in_process_graph):
            _assert_one_reading_per_stuff(graph)
            # A method input declared as a list, on the method and on its first consumer.
            assert _multiplicities(graph, pipe_code="process_documents", direction="input", name="documents") == {True}
            assert _multiplicities(graph, pipe_code="extract_records", direction="input", name="documents") == {True}
            # A declared list output, with the concept left bare.
            assert _multiplicities(graph, pipe_code="extract_records", direction="output", name="records") == {True}
            records_concepts = {
                io_spec.concept for node, io_spec in _io_items(graph) if node.pipe_code == "extract_records" and io_spec.name == "records"
            }
            assert records_concepts == {"Record"}
            # A batch: each item single, each item's result single, the aggregate a list.
            assert _multiplicities(graph, pipe_code="summarize_record", direction="input", name="record") == {None}
            assert _multiplicities(graph, pipe_code="brainstorm", direction="input", name="summaries") == {True}
            # A single output made a list by the step's nb_output.
            assert _multiplicities(graph, pipe_code="brainstorm", direction="output", name="ideas") == {True}
            # A parallel's branch outputs, registered on the parallel itself.
            assert _multiplicities(graph, pipe_code="assess", direction="output", name="risks") == {True}
            assert _multiplicities(graph, pipe_code="assess", direction="output", name="pick") == {None}
            assert _multiplicities(graph, pipe_code="conclude", direction="input", name="risks") == {True}
            assert _multiplicities(graph, pipe_code="conclude", direction="input", name="pick") == {None}
            assert _multiplicities(graph, pipe_code="conclude", direction="output", name="conclusion") == {None}

    async def test_lifted_plural_outputs_read_as_lists(self, mocker: MockerFixture) -> None:
        """An empty list from a lift is still a list: `True`, never `0` and never single."""
        teardown_spy = mocker.spy(GraphTracer, "teardown")
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=True)
        runner = PipelexMTHDSProtocol(execution_config=execution_config)

        with scoped_event_log(InMemoryEventLog()):
            response = await runner.execute(mthds_contents=[_LIFT_BUNDLE], inputs={})

        assert response.pipe_output.main_stuff.as_text.text == "0 findings, 0 more"
        assembled_graph = response.pipe_output.graph_spec
        assert assembled_graph is not None
        in_process_graph = _in_process_graph(teardown_spy)

        for graph in (assembled_graph, in_process_graph):
            _assert_one_reading_per_stuff(graph)
            lifted_codes = {node.pipe_code for node in graph.nodes if node.status == NodeStatus.SKIPPED}
            assert {"find_many", "branch_out"} <= lifted_codes
            # A lifted pipe's plural main output.
            assert _multiplicities(graph, pipe_code="find_many", direction="output", name="findings") == {True}
            assert _multiplicities(graph, pipe_code="count_findings", direction="input", name="findings") == {True}
            # A lifted parallel's plural companion slot.
            assert _multiplicities(graph, pipe_code="branch_out", direction="output", name="many_out") == {True}
            assert _multiplicities(graph, pipe_code="count_findings", direction="input", name="many_out") == {True}
