"""The merge record a dry-run condition leaves, read off what its outcomes left in the slot and what they declare."""

from collections.abc import Callable

import pytest
from pytest_mock import MockerFixture, MockType

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.graph.condition_output_merge import ConditionOutputMerge, ConditionOutputTyping
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.interpreter_hub import get_library_manager, get_required_pipe
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipe_controllers.condition.pipe_condition import DryRunOutcomeSlot, PipeCondition
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from tests.integration.pipelex.pipeline.dry_run_condition.test_data import DryRunConditionTestData
from tests.unit.pipelex.graph.conftest import make_trace_context

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


def _slot(stuff: Stuff | None, *, declared_concept: str = "Text", declared_list: bool = False) -> DryRunOutcomeSlot:
    return DryRunOutcomeSlot(declared_concept=declared_concept, declared_list=declared_list, stuff=stuff)


class TestDryRunConditionMergeRecord:
    @pytest.fixture
    def route(self, load_empty_library: Callable[[], str]) -> PipeCondition:
        library_id = load_empty_library()
        blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=DryRunConditionTestData.REPORT_SHAPE_MTHDS)
        get_library_manager().load_from_blueprints(library_id=library_id, blueprints=[blueprint])
        condition = get_required_pipe(pipe_code="dry_condition_report_shape.route")
        assert isinstance(condition, PipeCondition)
        return condition

    @pytest.fixture
    def tracer_manager(self, mocker: MockerFixture) -> MockType:
        manager: MockType = mocker.MagicMock(spec=GraphTracerManager)
        mocker.patch.object(GraphTracerManager, "get_instance", return_value=manager)
        return manager

    def _register(
        self,
        *,
        route: PipeCondition,
        received: list[Stuff],
        outcome_slots: list[DryRunOutcomeSlot],
        output_multiplicity: int | None = None,
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

    def _recorded_merges(self, tracer_manager: MockType) -> list[ConditionOutputMerge]:
        return [call.kwargs["merge"] for call in tracer_manager.register_condition_output_merge.call_args_list]

    def test_outcomes_that_agree_merge_without_a_typing(self, route: PipeCondition, tracer_manager: MockType) -> None:
        questions, rejection = _text_stuff(text="questions"), _text_stuff(text="rejection")

        self._register(route=route, received=[], outcome_slots=[_slot(questions), _slot(rejection)])

        assert self._recorded_merges(tracer_manager) == [
            ConditionOutputMerge(condition_node_id=_CONDITION_NODE_ID, shared_digest=rejection.stuff_code, merged_digests=[questions.stuff_code])
        ]

    def test_outcomes_that_write_differently_carry_the_declared_typing(self, route: PipeCondition, tracer_manager: MockType) -> None:
        questions, rejection = _text_list_stuff(texts=["one", "two"]), _text_stuff(text="rejection")

        self._register(route=route, received=[], outcome_slots=[_slot(questions, declared_list=True), _slot(rejection)])

        [merge] = self._recorded_merges(tracer_manager)
        assert merge.shared_typing == ConditionOutputTyping(concept="Text", multiplicity=None)

    def test_outcomes_that_declare_differently_carry_the_declared_typing(self, route: PipeCondition, tracer_manager: MockType) -> None:
        """A nested condition hands back one outcome's stuff, which can agree with its sibling's while its declaration does not."""
        nested, fallback = _text_stuff(text="nested"), _text_stuff(text="fallback")

        self._register(route=route, received=[], outcome_slots=[_slot(nested, declared_concept="Anything"), _slot(fallback)])

        [merge] = self._recorded_merges(tracer_manager)
        assert merge.shared_typing == ConditionOutputTyping(concept="Text", multiplicity=None)

    def test_an_output_count_types_the_stuff_as_a_list_not_a_count(self, route: PipeCondition, tracer_manager: MockType) -> None:
        """Every io item records a list as `True`, so the shared stuff reads the same on the condition and its readers."""
        questions, rejection = _text_list_stuff(texts=["one", "two"]), _text_stuff(text="rejection")

        self._register(route=route, received=[], outcome_slots=[_slot(questions, declared_list=True), _slot(rejection)], output_multiplicity=3)

        [merge] = self._recorded_merges(tracer_manager)
        assert merge.shared_typing == ConditionOutputTyping(concept="Text", multiplicity=True)

    def test_outcomes_sharing_one_stuff_code_still_carry_the_declared_typing(self, route: PipeCondition, tracer_manager: MockType) -> None:
        """Run as a batch's branch, every outcome mints under the branch's stuff code: nothing to merge, a typing to record."""
        branch_stuff = _text_stuff(text="branch")

        self._register(route=route, received=[], outcome_slots=[_slot(branch_stuff, declared_concept="Number"), _slot(branch_stuff)])

        assert self._recorded_merges(tracer_manager) == [
            ConditionOutputMerge(
                condition_node_id=_CONDITION_NODE_ID,
                shared_digest=branch_stuff.stuff_code,
                merged_digests=[],
                shared_typing=ConditionOutputTyping(concept="Text", multiplicity=None),
            )
        ]

    def test_outcomes_sharing_one_stuff_code_and_agreeing_record_nothing(self, route: PipeCondition, tracer_manager: MockType) -> None:
        branch_stuff = _text_stuff(text="branch")

        self._register(route=route, received=[], outcome_slots=[_slot(branch_stuff), _slot(branch_stuff)])

        assert self._recorded_merges(tracer_manager) == []

    def test_a_received_stuff_is_never_merged(self, route: PipeCondition, tracer_manager: MockType) -> None:
        """An outcome handing back a stuff it was given would drag that stuff's producer into the result."""
        cv, rejection = _text_stuff(text="cv"), _text_stuff(text="rejection")

        self._register(route=route, received=[cv], outcome_slots=[_slot(cv), _slot(rejection)])

        assert self._recorded_merges(tracer_manager) == []

    def test_a_received_shared_stuff_merges_nothing(self, route: PipeCondition, tracer_manager: MockType) -> None:
        cv, questions = _text_stuff(text="cv"), _text_stuff(text="questions")

        self._register(route=route, received=[cv], outcome_slots=[_slot(questions), _slot(cv)])

        assert self._recorded_merges(tracer_manager) == []

    def test_an_absent_last_outcome_merges_nothing(self, route: PipeCondition, tracer_manager: MockType) -> None:
        self._register(route=route, received=[], outcome_slots=[_slot(_text_stuff(text="questions")), _slot(None)])

        assert self._recorded_merges(tracer_manager) == []

    def test_an_absent_outcome_is_left_out(self, route: PipeCondition, tracer_manager: MockType) -> None:
        """An absent outcome neither merges nor counts towards the typing, even when it declares another concept."""
        questions, rejection = _text_stuff(text="questions"), _text_stuff(text="rejection")

        self._register(route=route, received=[], outcome_slots=[_slot(None, declared_concept="Number"), _slot(questions), _slot(rejection)])

        [merge] = self._recorded_merges(tracer_manager)
        assert merge.merged_digests == [questions.stuff_code]
        assert merge.shared_typing is None
