"""A dry-run condition's result is one stuff, with a writer per outcome.

A dry run cannot know which outcome a live run would take, so ``PipeCondition`` dry-runs every
outcome. Each outcome writes the condition's one slot, so the GraphSpec must show the condition's
result as one stuff that every outcome writes and the step after the condition reads, rather than
one outcome wired to that step and every other outcome's output left as a stuff nobody reads. Every
outcome's output is merged onto the last outcome's digest, which is the condition's own output
digest, by a record both graph builders apply once the graph is built.
"""

import re

import pytest

from pipelex.graph.graph_analysis import GraphAnalysis
from pipelex.graph.graphspec import EdgeKind, GraphSpec
from pipelex.graph.mermaidflow.mermaidflow_factory import MermaidflowFactory
from pipelex.graph.mermaidflow.mermaidflow_utils import make_stuff_id
from pipelex.pipeline.dry_run_pipeline import dry_run_pipeline
from pipelex.tools.mermaid.mermaid_utils import sanitize_mermaid_id
from tests.integration.pipelex.pipeline.dry_run_condition.graph_reading import (
    input_named,
    node_by_code,
    nodes_by_code,
    only_output,
    output_named,
    read_digests,
)
from tests.integration.pipelex.pipeline.dry_run_condition.test_data import DryRunConditionTestData
from tests.unit.pipelex.graph.conftest import make_graph_config

_SUBGRAPH_OPENING = re.compile(r"^\s*subgraph (\S+?)\[")


def _subgraphs_declaring(*, mermaid_code: str, mermaid_id: str) -> list[str | None]:
    """The innermost subgraph around each declaration of `mermaid_id`, None at top level."""
    open_subgraphs: list[str] = []
    enclosing: list[str | None] = []
    for line in mermaid_code.splitlines():
        if opening := _SUBGRAPH_OPENING.match(line):
            open_subgraphs.append(opening.group(1))
        elif line.strip() == "end":
            open_subgraphs.pop()
        elif line.strip().startswith(f"{mermaid_id}(["):
            enclosing.append(open_subgraphs[-1] if open_subgraphs else None)
    return enclosing


def _shared_digest(graph_spec: GraphSpec, *, condition_code: str) -> str:
    digest = only_output(node_by_code(graph_spec, condition_code)).digest
    assert digest is not None
    return digest


@pytest.mark.asyncio(loop_scope="class")
class TestDryRunConditionSharedOutput:
    async def test_every_outcome_produces_the_stuff_the_next_step_reads(self) -> None:
        graph_spec, _ = await dry_run_pipeline(mthds_contents=[DryRunConditionTestData.REPORT_SHAPE_MTHDS])

        shared_digest = _shared_digest(graph_spec, condition_code="route")
        assert only_output(node_by_code(graph_spec, "write_questions")).digest == shared_digest
        assert only_output(node_by_code(graph_spec, "write_rejection")).digest == shared_digest
        assert input_named(node_by_code(graph_spec, "assemble"), "follow_up").digest == shared_digest

        # The step after the condition reads it through the condition, as in a live run.
        route_node_id = node_by_code(graph_spec, "route").node_id
        assemble_node_id = node_by_code(graph_spec, "assemble").node_id
        data_edges_into_assemble = {
            (edge.source, edge.label) for edge in graph_spec.edges if edge.kind == EdgeKind.DATA and edge.target == assemble_node_id
        }
        assert (route_node_id, "follow_up") in data_edges_into_assemble

        # No outcome's output is left as a stuff nobody reads.
        digests_read = read_digests(graph_spec)
        for outcome_code in ("write_questions", "write_rejection"):
            assert only_output(node_by_code(graph_spec, outcome_code)).digest in digests_read

    async def test_outcomes_that_disagree_type_the_stuff_by_the_declaration(self) -> None:
        graph_spec, _ = await dry_run_pipeline(mthds_contents=[DryRunConditionTestData.DIFFERING_OUTCOMES_MTHDS])

        route_output = only_output(node_by_code(graph_spec, "route"))
        questions_output = only_output(node_by_code(graph_spec, "write_questions"))
        rejection_output = only_output(node_by_code(graph_spec, "write_rejection"))

        assert questions_output.digest == route_output.digest
        assert rejection_output.digest == route_output.digest
        # The condition's own item types the shared stuff by its declaration...
        assert route_output.concept == "Anything"
        assert not route_output.multiplicity
        # ...while each outcome's card keeps what that outcome writes.
        assert questions_output.concept == "Question"
        assert questions_output.multiplicity is True
        assert rejection_output.concept == "Rejection"
        assert not rejection_output.multiplicity

    async def test_outcomes_that_agree_keep_their_typing(self) -> None:
        graph_spec, _ = await dry_run_pipeline(mthds_contents=[DryRunConditionTestData.REPORT_SHAPE_MTHDS])

        route_output = only_output(node_by_code(graph_spec, "route"))
        assert route_output.concept == "Text"
        assert not route_output.multiplicity

    async def test_a_sequence_outcome_moves_its_last_step_with_it(self) -> None:
        graph_spec, _ = await dry_run_pipeline(mthds_contents=[DryRunConditionTestData.SEQUENCE_OUTCOME_MTHDS])

        shared_digest = _shared_digest(graph_spec, condition_code="route")
        assert only_output(node_by_code(graph_spec, "questions_flow")).digest == shared_digest
        assert only_output(node_by_code(graph_spec, "finalize_questions")).digest == shared_digest
        # The sequence's first step is internal to the outcome and keeps its own stuff.
        assert only_output(node_by_code(graph_spec, "draft_questions")).digest != shared_digest

    async def test_a_batch_outcome_moves_its_aggregate_with_it(self) -> None:
        graph_spec, _ = await dry_run_pipeline(mthds_contents=[DryRunConditionTestData.BATCH_OUTCOME_MTHDS])

        shared_digest = _shared_digest(graph_spec, condition_code="route")
        batch_node = node_by_code(graph_spec, "ask_each_topic")
        assert only_output(batch_node).digest == shared_digest

        aggregate_edges = [edge for edge in graph_spec.edges if edge.kind == EdgeKind.BATCH_AGGREGATE and edge.target == batch_node.node_id]
        assert aggregate_edges, "the batch outcome aggregates its items"
        assert {edge.target_stuff_digest for edge in aggregate_edges} == {shared_digest}
        # The batch's items are internal to the outcome and keep their own stuffs.
        item_digests = {only_output(node).digest for node in nodes_by_code(graph_spec, "ask_topic")}
        assert shared_digest not in item_digests
        # The batch writes the stuff as a controller, so the condition still owns it.
        analysis = GraphAnalysis.from_graphspec(graph_spec)
        assert analysis.shared_stuff_controllers == {shared_digest: node_by_code(graph_spec, "route").node_id}

    async def test_a_nested_condition_types_the_outer_stuff_by_the_declaration(self) -> None:
        """Both of `outer`'s outcomes hand back Text, but `inner` declares `Anything` over a Number outcome."""
        graph_spec, _ = await dry_run_pipeline(mthds_contents=[DryRunConditionTestData.NESTED_CONDITIONS_MTHDS])

        shared_digest = _shared_digest(graph_spec, condition_code="outer")
        for writer_code in ("inner", "score_cv", "summarize_cv", "write_note"):
            assert only_output(node_by_code(graph_spec, writer_code)).digest == shared_digest
        assert only_output(node_by_code(graph_spec, "score_cv")).concept == "Number"

        assert only_output(node_by_code(graph_spec, "outer")).concept == "Anything"
        analysis = GraphAnalysis.from_graphspec(graph_spec)
        assert analysis.shared_stuff_controllers == {shared_digest: node_by_code(graph_spec, "outer").node_id}
        assert analysis.stuff_registry[shared_digest].concept == "Anything"

    async def test_a_parallel_outcome_writes_the_stuff_its_condition_owns(self) -> None:
        graph_spec, _ = await dry_run_pipeline(mthds_contents=[DryRunConditionTestData.PARALLEL_OUTCOME_MTHDS])

        shared_digest = _shared_digest(graph_spec, condition_code="route")
        parallel_node = node_by_code(graph_spec, "write_both")
        # The parallel also lists each branch's output, which stays its own.
        assert output_named(parallel_node, "follow_up").digest == shared_digest
        assert output_named(parallel_node, "questions").digest != shared_digest
        combine_edges = [edge for edge in graph_spec.edges if edge.kind == EdgeKind.PARALLEL_COMBINE and edge.target == parallel_node.node_id]
        assert {edge.target_stuff_digest for edge in combine_edges} == {shared_digest}

        route_node_id = node_by_code(graph_spec, "route").node_id
        analysis = GraphAnalysis.from_graphspec(graph_spec)
        assert analysis.shared_stuff_controllers == {shared_digest: route_node_id}
        # The parallel's Composite and the fallback's Text disagree, so the condition's `Anything` types the stuff.
        assert analysis.stuff_registry[shared_digest].concept == "Anything"

        # The stuff is drawn once, inside the condition, never inside the parallel outcome.
        mermaidflow = MermaidflowFactory.make_from_graphspec(graph_spec, graph_config=make_graph_config())
        declarations = _subgraphs_declaring(mermaid_code=mermaidflow.mermaid_code, mermaid_id=make_stuff_id(shared_digest))
        assert declarations == [f"sg_{sanitize_mermaid_id(route_node_id)}"]
