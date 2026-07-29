"""Integration tests for PipeCompose native scalar conversions.

These tests verify that a whole-stuff `{ from = "..." }` construct source unwraps native
content wrappers into native-typed target fields:
- TextContent to Optional[str] field (Optional unwrap)
- ListContent[TextContent] to list[str] and Optional[list[str]] fields (item scalar extraction)
- NumberContent to float field
- YesNoContent to bool field (including a falsy value)
- DateContent to date field
"""

import datetime
from pathlib import Path
from typing import Any, Callable, cast

import pytest

from pipelex import pretty_print
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.date_content import DateContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.yes_no_content import YesNoContent
from pipelex.interpreter_hub import get_native_concept, get_pipe_router
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.compose.exceptions import PipeComposeError
from pipelex.pipe_operators.compose.pipe_compose import PipeCompose
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.pipes.operator.pipe_compose_structured.test_data import NativeScalarConversionTestData


def _make_tag_texts() -> ListContent[TextContent]:
    return ListContent[TextContent](items=[TextContent(text="alpha"), TextContent(text="bravo"), TextContent(text="charlie")])


@pytest.mark.dry_runnable
@pytest.mark.asyncio(loop_scope="class")
class TestPipeComposeNativeScalarConversions:
    """Integration tests for native scalar conversions in PipeCompose construct mode."""

    @pytest.fixture
    def test_library_path(self) -> list[Path]:
        """Path to the test library for these tests."""
        return [Path("tests/integration/pipelex/pipes/operator/pipe_compose_structured")]

    @pytest.mark.parametrize(
        ("pipe_code", "input_name", "input_concept_code", "input_content", "construct", "output_concept", "field_name", "expected_value"),
        [
            pytest.param(
                "compose_text_to_optional_str",
                "note_text",
                NativeConceptCode.TEXT,
                TextContent(text="A short note"),
                NativeScalarConversionTestData.TEXT_TO_OPTIONAL_STR_CONSTRUCT,
                "NoteHolder",
                "note",
                "A short note",
                id="text_content_to_optional_str_field",
            ),
            pytest.param(
                "compose_text_list_to_str_list",
                "tag_texts",
                NativeConceptCode.TEXT,
                _make_tag_texts(),
                NativeScalarConversionTestData.TEXT_LIST_TO_STR_LIST_CONSTRUCT,
                "TagsHolder",
                "tags",
                ["alpha", "bravo", "charlie"],
                id="text_list_to_required_str_list_field",
            ),
            pytest.param(
                "compose_text_list_to_optional_str_list",
                "tag_texts",
                NativeConceptCode.TEXT,
                _make_tag_texts(),
                NativeScalarConversionTestData.TEXT_LIST_TO_STR_LIST_CONSTRUCT,
                "OptionalTagsHolder",
                "tags",
                ["alpha", "bravo", "charlie"],
                id="text_list_to_optional_str_list_field",
            ),
            pytest.param(
                "compose_text_list_to_nullable_str_list",
                "tag_texts",
                NativeConceptCode.TEXT,
                _make_tag_texts(),
                NativeScalarConversionTestData.TEXT_LIST_TO_STR_LIST_CONSTRUCT,
                "NullableTagsHolder",
                "tags",
                ["alpha", "bravo", "charlie"],
                id="text_list_to_nullable_item_str_list_field",
            ),
            pytest.param(
                "compose_number_to_float",
                "score_number",
                NativeConceptCode.NUMBER,
                NumberContent(number=42.5),
                NativeScalarConversionTestData.NUMBER_TO_FLOAT_CONSTRUCT,
                "ScoreHolder",
                "score",
                42.5,
                id="number_content_to_float_field",
            ),
            pytest.param(
                "compose_yes_no_to_bool",
                "approval_flag",
                NativeConceptCode.YES_NO,
                YesNoContent(yes_no=False),
                NativeScalarConversionTestData.YES_NO_TO_BOOL_CONSTRUCT,
                "ApprovalHolder",
                "approved",
                False,
                id="yes_no_content_to_bool_field_falsy",
            ),
            pytest.param(
                "compose_date_to_date",
                "deadline_date",
                NativeConceptCode.DATE,
                DateContent(date=datetime.date(2026, 3, 14)),
                NativeScalarConversionTestData.DATE_TO_DATE_CONSTRUCT,
                "DeadlineHolder",
                "deadline",
                datetime.date(2026, 3, 14),
                id="date_content_to_date_field",
            ),
        ],
    )
    async def test_compose_native_scalar_conversion(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
        pipe_code: str,
        input_name: str,
        input_concept_code: NativeConceptCode,
        input_content: StuffContent,
        construct: dict[str, Any],
        output_concept: str,
        field_name: str,
        expected_value: Any,
    ):
        """A whole native stuff copied via construct must land in the target field as the native value with the exact native type."""
        load_test_library(test_library_path)

        input_stuff = StuffFactory.make_stuff(
            concept=get_native_concept(input_concept_code),
            content=input_content,
            name=input_name,
        )
        working_memory = WorkingMemory()
        working_memory.add_new_stuff(name=input_name, stuff=input_stuff)

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": f"Compose {output_concept} from a whole {input_concept_code} stuff",
                "inputs": {input_name: input_concept_code},
                "construct": construct,
                "output": f"compose_structured_test.{output_concept}",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code=pipe_code,
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None
        assert type(main_stuff.content).__name__ == output_concept

        composed_value = getattr(main_stuff.content, field_name)
        assert composed_value == expected_value
        assert type(composed_value) is type(expected_value)
        if isinstance(expected_value, list):
            expected_items = cast("list[Any]", expected_value)
            for composed_item, expected_item in zip(composed_value, expected_items, strict=True):
                assert type(composed_item) is type(expected_item)

        pretty_print(main_stuff.content, title=f"{output_concept} - native scalar conversion")

    async def test_compose_timestamped_date_to_date_field_raises(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """A Date carrying a time of day must be rejected by a bare `date` target field instead of silently dropping the time."""
        load_test_library(test_library_path)

        timestamped_date = DateContent(
            date=datetime.date(2026, 3, 14),
            time=datetime.time(15, 40, tzinfo=datetime.timezone(datetime.timedelta(hours=2))),
        )
        input_stuff = StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.DATE),
            content=timestamped_date,
            name="deadline_date",
        )
        working_memory = WorkingMemory()
        working_memory.add_new_stuff(name="deadline_date", stuff=input_stuff)

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose DeadlineHolder from a whole timestamped Date stuff",
                "inputs": {"deadline_date": NativeConceptCode.DATE},
                "construct": NativeScalarConversionTestData.DATE_TO_DATE_CONSTRUCT,
                "output": "compose_structured_test.DeadlineHolder",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_timestamped_date_to_date",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )

        with pytest.raises(PipeComposeError, match="time of day"):
            await get_pipe_router().run(pipe_job=pipe_job)
