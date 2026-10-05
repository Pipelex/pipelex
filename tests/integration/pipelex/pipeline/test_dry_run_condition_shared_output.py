"""A dry-run condition's result is one stuff, with a producer per outcome.

A dry run cannot know which outcome a live run would take, so ``PipeCondition`` dry-runs every
outcome. Each outcome writes the condition's one slot, so the GraphSpec must show the condition's
result as one stuff that every outcome produces and the step after the condition reads, rather
than one outcome wired to that step and every other outcome's output left as a stuff nobody reads.

Two things make that shape true, and each has its tests here:

- Every outcome but the last runs on a copy of the memory the condition received, and the default
  outcome runs last. No outcome reads what a sibling wrote, and downstream steps read the value a
  live run falls back to when nothing matches.
- Every outcome's output is merged onto the last outcome's digest, which is the condition's own
  output digest, by a record both graph builders apply once the graph is built.
"""

from collections.abc import Callable, Sequence
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory import working_memory as working_memory_module
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.graph.condition_output_merge import ConditionOutputMerge, ConditionOutputTyping
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.graph.graphspec import EdgeKind, GraphSpec, IOSpec, NodeSpec
from pipelex.interpreter_hub import get_library_manager, get_required_pipe
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.dry_run_pipeline import dry_run_pipeline
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from tests.unit.pipelex.graph.conftest import make_trace_context

_REPORT_SHAPE_MTHDS = """
domain = "dry_condition_report_shape"
description = "Judge a CV, route the follow-up, assemble both"
main_pipe = "screen"

[pipe.screen]
type = "PipeSequence"
description = "Screen a CV"
inputs = { cv = "Text" }
output = "Text"
steps = [
  { pipe = "judge", result = "verdict" },
  { pipe = "route", result = "follow_up" },
  { pipe = "assemble", result = "result" },
]

[pipe.judge]
type = "PipeLLM"
description = "Judge the CV"
inputs = { cv = "Text" }
output = "Text"
prompt = "Judge $cv"

[pipe.route]
type = "PipeCondition"
description = "Route the follow-up on the verdict"
inputs = { verdict = "Text", cv = "Text" }
output = "Text"
expression = "verdict"
outcomes = { fit = "write_questions", no_fit = "write_rejection" }
default_outcome = "write_rejection"

[pipe.write_questions]
type = "PipeLLM"
description = "Write interview questions"
inputs = { cv = "Text" }
output = "Text"
prompt = "Questions for $cv"

[pipe.write_rejection]
type = "PipeLLM"
description = "Write a rejection"
inputs = { cv = "Text" }
output = "Text"
prompt = "Rejection for $cv"

[pipe.assemble]
type = "PipeLLM"
description = "Assemble the verdict and the follow-up"
inputs = { verdict = "Text", follow_up = "Text" }
output = "Text"
prompt = "Assemble $verdict and $follow_up"
"""

# The condition writes `draft`, a slot that already holds `first_draft`'s value, and `b_polish`
# reads that slot. Run last and unisolated, `b_polish` would read the draft `a_rewrite` just wrote.
_SLOT_CROSS_READ_MTHDS = """
domain = "dry_condition_slot_cross_read"
description = "A condition whose outcome reads the slot the condition writes"
main_pipe = "flow"

[pipe.flow]
type = "PipeSequence"
description = "Draft, judge, then rewrite or polish the draft"
inputs = { text = "Text" }
output = "Text"
steps = [
  { pipe = "first_draft", result = "draft" },
  { pipe = "judge", result = "verdict" },
  { pipe = "route", result = "draft" },
]

[pipe.first_draft]
type = "PipeLLM"
description = "Write a first draft"
inputs = { text = "Text" }
output = "Text"
prompt = "Draft $text"

[pipe.judge]
type = "PipeLLM"
description = "Judge the draft"
inputs = { draft = "Text" }
output = "Text"
prompt = "Judge $draft"

[pipe.route]
type = "PipeCondition"
description = "Rewrite from scratch or polish the draft"
inputs = { verdict = "Text", text = "Text", draft = "Text" }
output = "Text"
expression = "verdict"
outcomes = { rewrite = "a_rewrite", polish = "b_polish" }
default_outcome = "b_polish"

[pipe.a_rewrite]
type = "PipeLLM"
description = "Rewrite from the original text"
inputs = { text = "Text" }
output = "Text"
prompt = "Rewrite $text"

[pipe.b_polish]
type = "PipeLLM"
description = "Polish the draft"
inputs = { draft = "Text" }
output = "Text"
prompt = "Polish $draft"
"""

# The outcomes write different concepts and multiplicities, so only the condition's declaration
# covers both: the shared stuff is typed `Anything`, single.
_DIFFERING_OUTCOMES_MTHDS = """
domain = "dry_condition_differing_outcomes"
description = "A condition whose outcomes write different concepts"
main_pipe = "screen"

[concept.Question]
description = "An interview question"
refines = "Text"

[concept.Rejection]
description = "A rejection letter"
refines = "Text"

[pipe.screen]
type = "PipeSequence"
description = "Screen a CV"
inputs = { cv = "Text" }
output = "Text"
steps = [
  { pipe = "judge", result = "verdict" },
  { pipe = "route", result = "follow_up" },
  { pipe = "assemble", result = "result" },
]

[pipe.judge]
type = "PipeLLM"
description = "Judge the CV"
inputs = { cv = "Text" }
output = "Text"
prompt = "Judge $cv"

[pipe.route]
type = "PipeCondition"
description = "Route the follow-up on the verdict"
inputs = { verdict = "Text", cv = "Text" }
output = "Anything"
expression = "verdict"
outcomes = { fit = "write_questions", no_fit = "write_rejection" }
default_outcome = "write_rejection"

[pipe.write_questions]
type = "PipeLLM"
description = "Write interview questions"
inputs = { cv = "Text" }
output = "Question[]"
prompt = "Questions for $cv"

[pipe.write_rejection]
type = "PipeLLM"
description = "Write a rejection"
inputs = { cv = "Text" }
output = "Rejection"
prompt = "Rejection for $cv"

[pipe.assemble]
type = "PipeLLM"
description = "Assemble the verdict and the follow-up"
inputs = { verdict = "Text", follow_up = "Anything" }
output = "Text"
prompt = "Assemble $verdict and $follow_up"
"""

# An outcome that is a sequence: its last step's output is the sequence's output, so it moves too.
_SEQUENCE_OUTCOME_MTHDS = """
domain = "dry_condition_sequence_outcome"
description = "A condition whose non-default outcome is a sequence"
main_pipe = "screen"

[pipe.screen]
type = "PipeSequence"
description = "Screen a CV"
inputs = { cv = "Text" }
output = "Text"
steps = [
  { pipe = "judge", result = "verdict" },
  { pipe = "route", result = "follow_up" },
  { pipe = "assemble", result = "result" },
]

[pipe.judge]
type = "PipeLLM"
description = "Judge the CV"
inputs = { cv = "Text" }
output = "Text"
prompt = "Judge $cv"

[pipe.route]
type = "PipeCondition"
description = "Route the follow-up on the verdict"
inputs = { verdict = "Text", cv = "Text" }
output = "Text"
expression = "verdict"
outcomes = { fit = "questions_flow", no_fit = "write_rejection" }
default_outcome = "write_rejection"

[pipe.questions_flow]
type = "PipeSequence"
description = "Draft then finalize the questions"
inputs = { cv = "Text" }
output = "Text"
steps = [
  { pipe = "draft_questions", result = "question_draft" },
  { pipe = "finalize_questions", result = "questions" },
]

[pipe.draft_questions]
type = "PipeLLM"
description = "Draft the questions"
inputs = { cv = "Text" }
output = "Text"
prompt = "Draft questions for $cv"

[pipe.finalize_questions]
type = "PipeLLM"
description = "Finalize the questions"
inputs = { question_draft = "Text" }
output = "Text"
prompt = "Finalize $question_draft"

[pipe.write_rejection]
type = "PipeLLM"
description = "Write a rejection"
inputs = { cv = "Text" }
output = "Text"
prompt = "Rejection for $cv"

[pipe.assemble]
type = "PipeLLM"
description = "Assemble the verdict and the follow-up"
inputs = { verdict = "Text", follow_up = "Text" }
output = "Text"
prompt = "Assemble $verdict and $follow_up"
"""

# An outcome that is a batch: the aggregate edge into its output list names that list's digest,
# which moves onto the condition's.
_BATCH_OUTCOME_MTHDS = """
domain = "dry_condition_batch_outcome"
description = "A condition whose non-default outcome is a batch"
main_pipe = "screen"

[pipe.screen]
type = "PipeSequence"
description = "Screen a CV over topics"
inputs = { cv = "Text", topics = "Text[]" }
output = "Text"
steps = [
  { pipe = "judge", result = "verdict" },
  { pipe = "route", result = "follow_up" },
  { pipe = "assemble", result = "result" },
]

[pipe.judge]
type = "PipeLLM"
description = "Judge the CV"
inputs = { cv = "Text" }
output = "Text"
prompt = "Judge $cv"

[pipe.route]
type = "PipeCondition"
description = "Route the follow-up on the verdict"
inputs = { verdict = "Text", cv = "Text", topics = "Text[]" }
output = "Text[]"
expression = "verdict"
outcomes = { fit = "ask_each_topic", no_fit = "write_rejections" }
default_outcome = "write_rejections"

[pipe.ask_each_topic]
type = "PipeBatch"
description = "Ask one question per topic"
inputs = { topics = "Text[]" }
output = "Text[]"
branch_pipe_code = "ask_topic"
input_list_name = "topics"
input_item_name = "topic"

[pipe.ask_topic]
type = "PipeLLM"
description = "Ask a question on one topic"
inputs = { topic = "Text" }
output = "Text"
prompt = "Ask about $topic"

[pipe.write_rejections]
type = "PipeLLM"
description = "Write rejection paragraphs"
inputs = { cv = "Text" }
output = "Text[]"
prompt = "Rejection paragraphs for $cv"

[pipe.assemble]
type = "PipeLLM"
description = "Assemble the verdict and the follow-up"
inputs = { verdict = "Text", follow_up = "Text[]" }
output = "Text"
prompt = "Assemble $verdict and $follow_up"
"""


def _node_by_code(graph_spec: GraphSpec, pipe_code: str) -> NodeSpec:
    matches = [node for node in graph_spec.nodes if node.pipe_code == pipe_code]
    assert len(matches) == 1, f"expected one node for '{pipe_code}', found {len(matches)}"
    return matches[0]


def _nodes_by_code(graph_spec: GraphSpec, pipe_code: str) -> list[NodeSpec]:
    return [node for node in graph_spec.nodes if node.pipe_code == pipe_code]


def _only_output(node: NodeSpec) -> IOSpec:
    assert len(node.node_io.outputs) == 1, f"expected one output on '{node.pipe_code}', found {node.node_io.outputs}"
    return node.node_io.outputs[0]


def _input_named(node: NodeSpec, name: str) -> IOSpec:
    matches = [input_spec for input_spec in node.node_io.inputs if input_spec.name == name]
    assert len(matches) == 1, f"expected one input '{name}' on '{node.pipe_code}', found {node.node_io.inputs}"
    return matches[0]


def _read_digests(graph_spec: GraphSpec) -> set[str]:
    return {input_spec.digest for node in graph_spec.nodes for input_spec in node.node_io.inputs if input_spec.digest is not None}


def _replaced_key_warnings(warning_calls: Sequence[object], *, key: str) -> list[str]:
    needle = f"Key '{key}' already exists in WorkingMemory and will be replaced"
    return [str(call) for call in warning_calls if needle in str(call)]


@pytest.mark.asyncio(loop_scope="class")
class TestDryRunConditionOutcomeIsolation:
    async def test_an_outcome_reads_the_slot_as_the_condition_received_it(self) -> None:
        """`b_polish` runs after `a_rewrite` and reads `draft`: it must read `first_draft`'s value."""
        graph_spec, _ = await dry_run_pipeline(mthds_contents=[_SLOT_CROSS_READ_MTHDS])

        first_draft_digest = _only_output(_node_by_code(graph_spec, "first_draft")).digest
        polish_read_digest = _input_named(_node_by_code(graph_spec, "b_polish"), "draft").digest
        rewrite_digest = _only_output(_node_by_code(graph_spec, "a_rewrite")).digest

        assert first_draft_digest is not None
        assert polish_read_digest == first_draft_digest
        assert polish_read_digest != rewrite_digest

    async def test_no_outcome_replaces_a_sibling_value_in_the_slot(self, mocker: MockerFixture) -> None:
        """`follow_up` holds nothing before the condition, so no outcome may find it already written."""
        warning_spy = mocker.spy(working_memory_module.log, "warning")

        await dry_run_pipeline(mthds_contents=[_REPORT_SHAPE_MTHDS])

        assert _replaced_key_warnings(warning_spy.call_args_list, key="follow_up") == []


@pytest.mark.asyncio(loop_scope="class")
class TestDryRunConditionSharedOutput:
    async def test_every_outcome_produces_the_stuff_the_next_step_reads(self) -> None:
        graph_spec, _ = await dry_run_pipeline(mthds_contents=[_REPORT_SHAPE_MTHDS])

        shared_digest = _only_output(_node_by_code(graph_spec, "route")).digest
        assert shared_digest is not None
        assert _only_output(_node_by_code(graph_spec, "write_questions")).digest == shared_digest
        assert _only_output(_node_by_code(graph_spec, "write_rejection")).digest == shared_digest
        assert _input_named(_node_by_code(graph_spec, "assemble"), "follow_up").digest == shared_digest

        # The step after the condition reads it through the condition, as in a live run.
        route_node_id = _node_by_code(graph_spec, "route").node_id
        assemble_node_id = _node_by_code(graph_spec, "assemble").node_id
        data_edges_into_assemble = {
            (edge.source, edge.label) for edge in graph_spec.edges if edge.kind == EdgeKind.DATA and edge.target == assemble_node_id
        }
        assert (route_node_id, "follow_up") in data_edges_into_assemble

        # No outcome's output is left as a stuff nobody reads.
        read_digests = _read_digests(graph_spec)
        for outcome_code in ("write_questions", "write_rejection"):
            assert _only_output(_node_by_code(graph_spec, outcome_code)).digest in read_digests

    async def test_the_default_outcome_names_the_shared_stuff(self) -> None:
        """The default outcome runs last, so its value is the one the next step reads."""
        graph_spec, _ = await dry_run_pipeline(mthds_contents=[_SLOT_CROSS_READ_MTHDS])

        shared_digest = _only_output(_node_by_code(graph_spec, "route")).digest
        assert _only_output(_node_by_code(graph_spec, "b_polish")).digest == shared_digest
        assert _only_output(_node_by_code(graph_spec, "a_rewrite")).digest == shared_digest

    async def test_outcomes_that_disagree_type_the_stuff_by_the_declaration(self) -> None:
        graph_spec, _ = await dry_run_pipeline(mthds_contents=[_DIFFERING_OUTCOMES_MTHDS])

        route_output = _only_output(_node_by_code(graph_spec, "route"))
        questions_output = _only_output(_node_by_code(graph_spec, "write_questions"))
        rejection_output = _only_output(_node_by_code(graph_spec, "write_rejection"))

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
        graph_spec, _ = await dry_run_pipeline(mthds_contents=[_REPORT_SHAPE_MTHDS])

        route_output = _only_output(_node_by_code(graph_spec, "route"))
        assert route_output.concept == "Text"
        assert not route_output.multiplicity

    async def test_a_sequence_outcome_moves_its_last_step_with_it(self) -> None:
        graph_spec, _ = await dry_run_pipeline(mthds_contents=[_SEQUENCE_OUTCOME_MTHDS])

        shared_digest = _only_output(_node_by_code(graph_spec, "route")).digest
        assert _only_output(_node_by_code(graph_spec, "questions_flow")).digest == shared_digest
        assert _only_output(_node_by_code(graph_spec, "finalize_questions")).digest == shared_digest
        # The sequence's first step is internal to the outcome and keeps its own stuff.
        assert _only_output(_node_by_code(graph_spec, "draft_questions")).digest != shared_digest

    async def test_a_batch_outcome_moves_its_aggregate_with_it(self) -> None:
        graph_spec, _ = await dry_run_pipeline(mthds_contents=[_BATCH_OUTCOME_MTHDS])

        shared_digest = _only_output(_node_by_code(graph_spec, "route")).digest
        batch_node = _node_by_code(graph_spec, "ask_each_topic")
        assert _only_output(batch_node).digest == shared_digest

        aggregate_edges = [edge for edge in graph_spec.edges if edge.kind == EdgeKind.BATCH_AGGREGATE and edge.target == batch_node.node_id]
        assert aggregate_edges, "the batch outcome aggregates its items"
        assert {edge.target_stuff_digest for edge in aggregate_edges} == {shared_digest}
        # The batch's items are internal to the outcome and keep their own stuffs.
        item_digests = {_only_output(node).digest for node in _nodes_by_code(graph_spec, "ask_topic")}
        assert shared_digest not in item_digests


_CONDITION_NODE_ID = "graph:node_route"


def _text_stuff(*, text: str) -> Stuff:
    return StuffFactory.make_stuff(
        concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
        content=TextContent(text=text),
        name="follow_up",
    )


def _text_list_stuff(*, texts: list[str]) -> Stuff:
    return StuffFactory.make_stuff(
        concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
        content=ListContent[TextContent](items=[TextContent(text=text) for text in texts]),
        name="follow_up",
    )


class TestDryRunConditionMergeRecord:
    """The merge record a dry-run condition leaves, read off the slots its outcomes resolved."""

    @pytest.fixture
    def route(self, load_empty_library: Callable[[], str]) -> PipeCondition:
        library_id = load_empty_library()
        blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_REPORT_SHAPE_MTHDS)
        get_library_manager().load_from_blueprints(library_id=library_id, blueprints=[blueprint])
        condition = get_required_pipe(pipe_code="dry_condition_report_shape.route")
        assert isinstance(condition, PipeCondition)
        return condition

    @pytest.fixture
    def tracer_manager(self, mocker: MockerFixture) -> MagicMock:
        manager = MagicMock(spec=GraphTracerManager)
        mocker.patch.object(GraphTracerManager, "get_instance", return_value=manager)
        return manager

    def _register(
        self, *, route: PipeCondition, received: list[Stuff], outcome_slots: list[Stuff | None], output_multiplicity: int | None = None
    ) -> None:
        route._register_dry_run_output_merge(  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
            job_metadata=JobMetadata(
                run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="user_test", pipeline_run_id="run_merge_record"),
                pipe_code="route",
                trace_context=make_trace_context(graph_id="graph", parent_node_id=_CONDITION_NODE_ID),
            ),
            pipe_run_params=PipeRunParamsFactory.make_run_params(output_multiplicity=output_multiplicity),
            received_stuff_codes={stuff.stuff_code for stuff in received},
            outcome_slots=outcome_slots,
        )

    def _recorded_merges(self, tracer_manager: MagicMock) -> list[ConditionOutputMerge]:
        return [call.kwargs["merge"] for call in tracer_manager.register_condition_output_merge.call_args_list]

    def test_outcomes_that_agree_merge_without_a_typing(self, route: PipeCondition, tracer_manager: MagicMock) -> None:
        questions, rejection = _text_stuff(text="questions"), _text_stuff(text="rejection")

        self._register(route=route, received=[], outcome_slots=[questions, rejection])

        assert self._recorded_merges(tracer_manager) == [
            ConditionOutputMerge(condition_node_id=_CONDITION_NODE_ID, shared_digest=rejection.stuff_code, merged_digests=[questions.stuff_code])
        ]

    def test_outcomes_that_disagree_carry_the_declared_typing(self, route: PipeCondition, tracer_manager: MagicMock) -> None:
        questions, rejection = _text_list_stuff(texts=["one", "two"]), _text_stuff(text="rejection")

        self._register(route=route, received=[], outcome_slots=[questions, rejection], output_multiplicity=3)

        [merge] = self._recorded_merges(tracer_manager)
        # `route` declares `Text`; the invocation's count applies to the declaration.
        assert merge.shared_typing == ConditionOutputTyping(concept="Text", multiplicity=3)

    def test_a_received_stuff_is_never_merged(self, route: PipeCondition, tracer_manager: MagicMock) -> None:
        """An outcome handing back a stuff it was given would drag that stuff's producer into the result."""
        cv, rejection = _text_stuff(text="cv"), _text_stuff(text="rejection")

        self._register(route=route, received=[cv], outcome_slots=[cv, rejection])

        assert self._recorded_merges(tracer_manager) == []

    def test_a_received_shared_stuff_merges_nothing(self, route: PipeCondition, tracer_manager: MagicMock) -> None:
        cv, questions = _text_stuff(text="cv"), _text_stuff(text="questions")

        self._register(route=route, received=[cv], outcome_slots=[questions, cv])

        assert self._recorded_merges(tracer_manager) == []

    def test_an_absent_last_outcome_merges_nothing(self, route: PipeCondition, tracer_manager: MagicMock) -> None:
        self._register(route=route, received=[], outcome_slots=[_text_stuff(text="questions"), None])

        assert self._recorded_merges(tracer_manager) == []

    def test_an_absent_outcome_is_left_out(self, route: PipeCondition, tracer_manager: MagicMock) -> None:
        questions, rejection = _text_stuff(text="questions"), _text_stuff(text="rejection")

        self._register(route=route, received=[], outcome_slots=[None, questions, rejection])

        [merge] = self._recorded_merges(tracer_manager)
        assert merge.merged_digests == [questions.stuff_code]
        assert merge.shared_typing is None
