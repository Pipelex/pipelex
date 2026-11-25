import asyncio

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.assignment_models import LLMAssignment, ObjectAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.dry_mock import build_mock_objects, dry_img_gen_image_contents, dry_search_gen_sourced_answer
from pipelex.cogt.content_generation.llm_generate import llm_gen_object_list
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.config import get_config
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.declared_item_count import (
    ItemCountSource,
    ensure_declared_item_count_allowed,
    ensure_mock_item_count_allowed,
    ensure_run_item_count_allowed,
    get_max_declared_item_count,
    spend_dry_run_mock_items,
    validate_requested_max_declared_item_count,
)
from pipelex.core.pipes.declared_item_count_scope import scoped_dry_run_mock_budget, scoped_max_declared_item_count, validate_max_declared_item_count
from pipelex.core.pipes.exceptions import DeclaredItemCountLimitError, DryRunMockBudgetError
from pipelex.core.pipes.inputs.input_stuff_specs import TypedNamedStuffSpec
from pipelex.core.stuffs.text_content import TextContent
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.kernel.pipelex_kernel import PipelexKernel
from pipelex.system.configuration.configs import MethodLimitsConfig
from pipelex.system.exceptions import RunParameterError
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode


def _text_list_spec(*, multiplicity: int | bool) -> TypedNamedStuffSpec:
    return TypedNamedStuffSpec(
        variable_name="items",
        concept=ConceptFactory.make(
            concept_code=NativeConceptCode.TEXT, domain_code="native", description="A text", structure_class_name="TextContent"
        ),
        multiplicity=multiplicity,
        structure_class=TextContent,
    )


def _dry_text_list_assignment(*, nb_items: int | None, run_max_declared_item_count: int | None) -> ObjectAssignment:
    """A dry object-list assignment as a worker's activity receives it: its job's metadata carries the run's maximum."""
    run_metadata = RunMetadata(
        storage_scope="test/scope",
        read_scope=None,
        user_id="test-user",
        pipeline_run_id="test-run",
        max_declared_item_count=run_max_declared_item_count,
    )
    llm_assignment = LLMAssignment(
        job_metadata=JobMetadata(run_metadata=run_metadata),
        cogt_run_params=CogtRunParams(run_mode=PipeRunMode.DRY),
        llm_setting=LLMSetting(model="test-model", temperature=0.7),
        llm_prompt=LLMPrompt(user_text="test prompt"),
    )
    return ObjectAssignment.make_for_class(TextContent, llm_assignment=llm_assignment, nb_items=nb_items)


class TestDeclaredItemCountMaximum:
    def test_outside_every_scope_the_maximum_is_the_deployments(self) -> None:
        assert get_max_declared_item_count() == 1000

    def test_a_scope_states_the_maximum_and_none_keeps_the_one_in_force(self) -> None:
        with scoped_max_declared_item_count(maximum=5000):
            assert get_max_declared_item_count() == 5000
            with scoped_max_declared_item_count(maximum=None):
                assert get_max_declared_item_count() == 5000
            with scoped_max_declared_item_count(maximum=3):
                assert get_max_declared_item_count() == 3
            assert get_max_declared_item_count() == 5000
        assert get_max_declared_item_count() == 1000

    @pytest.mark.parametrize("maximum", [0, -5, 1_000_000_000, True])
    def test_a_maximum_no_runtime_may_set_is_refused(self, maximum: int) -> None:
        with pytest.raises(RunParameterError, match="maximum declared item count"):
            validate_max_declared_item_count(value=maximum)
        with pytest.raises(RunParameterError), scoped_max_declared_item_count(maximum=maximum):
            pass

    def test_a_requests_maximum_is_held_to_the_deployments_ceiling(self, mocker: MockerFixture) -> None:
        """At or below the ceiling, a lower maximum included, a request's maximum stands; past it, it is refused naming the ceiling."""
        assert validate_requested_max_declared_item_count(value=1000) == 1000
        assert validate_requested_max_declared_item_count(value=3) == 3
        with pytest.raises(RunParameterError, match=r"at most 1000, this deployment's max_declared_item_count_ceiling, got 1001"):
            validate_requested_max_declared_item_count(value=1001)

        mocker.patch.object(get_config().interpreter.method_limits, "max_declared_item_count_ceiling", 5000)
        assert validate_requested_max_declared_item_count(value=5000) == 5000

    def test_the_deployments_maximum_may_not_pass_its_ceiling(self) -> None:
        assert (
            MethodLimitsConfig(max_declared_item_count=1000, max_declared_item_count_ceiling=1000, max_dry_run_mock_items=10).max_declared_item_count
            == 1000
        )
        with pytest.raises(ValidationError, match="raise the ceiling with it"):
            MethodLimitsConfig(max_declared_item_count=2000, max_declared_item_count_ceiling=1000, max_dry_run_mock_items=10)

    @pytest.mark.parametrize(
        ("source", "lead_in"),
        [
            (ItemCountSource.METHOD, "The method declares 1001 items for the output of the pipe 'make_ideas'"),
            (ItemCountSource.DRY_RUN, "A dry run would build 1001 items for the output of the pipe 'make_ideas'"),
            (ItemCountSource.RUN, "The run asks for 1001 items for the output of the pipe 'make_ideas'"),
        ],
    )
    def test_the_refusal_names_who_asks_the_slot_the_count_and_the_maximum(self, source: ItemCountSource, lead_in: str) -> None:
        ensure_declared_item_count_allowed(count=1000, slot="the output of the pipe 'make_ideas'", maximum=1000, source=source)
        with pytest.raises(DeclaredItemCountLimitError) as exc_info:
            ensure_declared_item_count_allowed(count=1001, slot="the output of the pipe 'make_ideas'", maximum=1000, source=source)

        refusal = exc_info.value
        assert refusal.error_code == PipelexErrorCode.DEPLOYMENT_DECLARED_COUNT_OVER_LIMIT
        assert refusal.problem_params() == {"slot": "the output of the pipe 'make_ideas'", "count": 1001, "limit": 1000}
        assert str(refusal).startswith(f"{lead_in}, more than the 1000 this runtime allows for one slot.")

    def test_the_mock_builders_and_the_run_refuse_a_fixed_count_past_the_maximum_and_never_shorten_it(self, mocker: MockerFixture) -> None:
        """The dry run's second line: a fixed count past the maximum in force is refused before anything is built."""
        with scoped_max_declared_item_count(maximum=2):
            ensure_mock_item_count_allowed(count=2, slot="a slot")
            mock_stuff = WorkingMemoryFactory.make_mock_stuff(_text_list_spec(multiplicity=2))
            assert len(mock_stuff.as_list_of_fixed_content_type(TextContent).items) == 2

            with pytest.raises(DeclaredItemCountLimitError, match="A dry run would build 3 items for the mock input 'items'"):
                WorkingMemoryFactory.make_mock_stuff(_text_list_spec(multiplicity=3))
            with pytest.raises(DeclaredItemCountLimitError, match="mock images"):
                dry_img_gen_image_contents(mocker.MagicMock(nb_images=3))
            with pytest.raises(DeclaredItemCountLimitError, match="The run asks for 3 items"):
                ensure_run_item_count_allowed(count=3, slot="the run's output")

    def test_a_length_the_dry_run_chooses_is_shortened_to_the_maximum_never_refused(self) -> None:
        """A variable list declares no count: under a maximum below the dry run's defaults, its mocks are shorter, not refused."""
        assert get_config().inference.dry_run.nb_list_items == 3
        with scoped_max_declared_item_count(maximum=1):
            mock_stuff = WorkingMemoryFactory.make_mock_stuff(_text_list_spec(multiplicity=True))
            assert len(mock_stuff.as_list_of_fixed_content_type(TextContent).items) == 1
            assert len(dry_search_gen_sourced_answer().sources) == 1
        with scoped_max_declared_item_count(maximum=2):
            assert len(dry_search_gen_sourced_answer().sources) == 2

    @pytest.mark.asyncio
    async def test_a_dry_leaf_with_no_scope_open_reads_its_runs_maximum_from_its_job_metadata(self) -> None:
        """A worker's activity opens no scope: the leaf holds a fixed count to the maximum its job carries, else the worker's."""
        assert len(await llm_gen_object_list(_dry_text_list_assignment(nb_items=None, run_max_declared_item_count=2))) == 2
        assert len(await llm_gen_object_list(_dry_text_list_assignment(nb_items=5, run_max_declared_item_count=None))) == 5
        with pytest.raises(DeclaredItemCountLimitError) as exc_info:
            await llm_gen_object_list(_dry_text_list_assignment(nb_items=5, run_max_declared_item_count=4))
        assert exc_info.value.limit == 4

    @pytest.mark.asyncio
    async def test_a_dry_leaf_with_no_scope_open_spends_a_budget_of_its_own(self, mocker: MockerFixture) -> None:
        mocker.patch.object(get_config().interpreter.method_limits, "max_dry_run_mock_items", 4)
        assert len(await llm_gen_object_list(_dry_text_list_assignment(nb_items=4, run_max_declared_item_count=None))) == 4
        with pytest.raises(DryRunMockBudgetError):
            await llm_gen_object_list(_dry_text_list_assignment(nb_items=5, run_max_declared_item_count=None))

    def test_every_mock_builder_spends_one_budget_per_dry_run(self, mocker: MockerFixture) -> None:
        """The budget bounds the sum of the slots: each builder fits alone, their sum passes it."""
        mocker.patch.object(get_config().interpreter.method_limits, "max_dry_run_mock_items", 10)
        with scoped_dry_run_mock_budget() as tally:
            build_mock_objects(TextContent, count=4)
            WorkingMemoryFactory.make_mock_stuff(_text_list_spec(multiplicity=4))
            assert tally.built == 8
            with pytest.raises(DryRunMockBudgetError) as exc_info:
                WorkingMemoryFactory.make_mock_stuff(_text_list_spec(multiplicity=3))
            assert tally.built == 8

        refusal = exc_info.value
        assert refusal.error_code == PipelexErrorCode.DEPLOYMENT_DRY_RUN_MOCK_BUDGET_EXCEEDED
        assert refusal.problem_params() == {"slot": "the mock input 'items'", "budget": 10}
        assert "after 8 already built, past the 10 this runtime builds for one dry run" in str(refusal)

    @pytest.mark.asyncio
    async def test_the_concurrent_branches_of_one_dry_run_share_its_budget(self, mocker: MockerFixture) -> None:
        """Each task runs in a copy of the context, and still adds to the one tally the scope opened."""
        mocker.patch.object(get_config().interpreter.method_limits, "max_dry_run_mock_items", 100)

        async def _branch() -> None:
            await asyncio.sleep(0)
            spend_dry_run_mock_items(count=10, slot="a branch's mock list")

        with scoped_dry_run_mock_budget() as tally:
            results = await asyncio.gather(*[_branch() for _ in range(15)], return_exceptions=True)

        refusals = [result for result in results if isinstance(result, DryRunMockBudgetError)]
        assert tally.built == 100
        assert len(refusals) == 5

    def test_a_nested_budget_scope_joins_the_open_one(self) -> None:
        with scoped_dry_run_mock_budget() as outer, scoped_dry_run_mock_budget() as inner:
            assert inner is outer

    def test_the_kernel_validates_and_carries_the_runs_maximum(self) -> None:
        kernel = PipelexKernel.make(user_id="test-user", storage_scope="test/scope", read_scope=None, max_declared_item_count=4)
        assert kernel.job_metadata.run_metadata.max_declared_item_count == 4
        assert (
            PipelexKernel.make(user_id="test-user", storage_scope="test/scope", read_scope=None).job_metadata.run_metadata.max_declared_item_count
            is None
        )
        with pytest.raises(RunParameterError, match="max_declared_item_count_ceiling"):
            PipelexKernel.make(user_id="test-user", storage_scope="test/scope", read_scope=None, max_declared_item_count=1001)
