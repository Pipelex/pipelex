from typing import Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_native_concept
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.pipes.stored_value_prompt.cases import STORED_TEXT, StoredValuePromptTestData
from tests.integration.pipelex.pipes.stored_value_prompt.conftest import RecordingContentGenerator

# Tells a long text from a short one by its real length: the stored text is far past the bound, its preview is not.
_EXPRESSION = "{% if verdict.text|length > 500 %}long{% else %}short{% endif %}"


def _make_condition() -> PipeCondition:
    return PipeFactory[PipeCondition].make_from_blueprint(
        domain_code="stored_value_prompt",
        pipe_code="route_by_length",
        blueprint=PipeConditionBlueprint(
            description="Route a verdict by its length",
            inputs={"verdict": f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}"},
            output=f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}?",
            expression_template=_EXPRESSION,
            outcomes={"long": SpecialOutcome.CONTINUE, "short": SpecialOutcome.CONTINUE},
            default_outcome=SpecialOutcome.CONTINUE,
        ),
    )


@pytest.mark.asyncio(loop_scope="class")
class TestPipeConditionStoredText:
    @pytest.mark.parametrize(
        ("verdict_content", "pages_content", "expected_outcome", "expected_nb_loads"),
        [
            # The expression reads a stored text: it is loaded through the leaf, once, and the route follows its real length.
            (TextContent.model_validate(StoredValuePromptTestData.TEXT_REFERENCE), None, "long", 1),
            # The expression reads an inline value only: nothing is dispatched, even with a stored text elsewhere in memory.
            (TextContent(text="approved"), TextContent.model_validate(StoredValuePromptTestData.TEXT_REFERENCE), "short", 0),
            (TextContent(text=STORED_TEXT), None, "long", 0),
        ],
    )
    async def test_an_expression_loads_a_stored_value_through_a_leaf_only_when_it_reads_one(
        self,
        mocker: MockerFixture,
        load_empty_library: Callable[[], str],
        scoped_job_metadata: JobMetadata,
        recording_content_generator: RecordingContentGenerator,
        verdict_content: TextContent,
        pages_content: TextContent | None,
        expected_outcome: str,
        expected_nb_loads: int,
    ) -> None:
        load_empty_library()
        load_spy = mocker.spy(recording_content_generator, "load_stored_texts")
        render_spy = mocker.spy(PipeCondition, "_render_expression")
        stuffs = [StuffFactory.make_stuff(concept=get_native_concept(NativeConceptCode.TEXT), content=verdict_content, name="verdict")]
        if pages_content is not None:
            stuffs.append(StuffFactory.make_stuff(concept=get_native_concept(NativeConceptCode.TEXT), content=pages_content, name="pages"))
        working_memory = WorkingMemoryFactory.make_from_multiple_stuffs(stuff_list=stuffs, main_name="verdict")

        await _make_condition().run_pipe(
            job_metadata=scoped_job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
        )

        assert render_spy.spy_return == expected_outcome
        assert load_spy.call_count == expected_nb_loads
        if expected_nb_loads:
            uri_references = load_spy.call_args.kwargs["uri_references"]
            assert [uri_reference.uri for uri_reference in uri_references] == [StoredValuePromptTestData.TEXT_REFERENCE["url"]]
            # The loaded text is kept on the content, never written onto the model: its dump is still the reference.
            assert verdict_content.require_text() == STORED_TEXT
            assert verdict_content.smart_dump() == StoredValuePromptTestData.TEXT_REFERENCE
        if pages_content is not None:
            assert not pages_content.is_loaded
