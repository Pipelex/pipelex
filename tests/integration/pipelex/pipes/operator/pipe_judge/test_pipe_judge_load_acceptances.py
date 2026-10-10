"""What a PipeJudge step may declare and still load."""

import pytest

from pipelex.pipeline.validate_bundle import validate_bundle
from tests.integration.pipelex.pipes.operator.pipe_judge.test_data import (
    ClassBackedTriage,
    PipeJudgeClassBackedTestData,
    PipeJudgeLoadTestData,
    PipeJudgeSeveralQuestionsTestData,
)

_MODEL = f'model = "{PipeJudgeLoadTestData.JUDGMENT_MODEL}"'


@pytest.mark.asyncio(loop_scope="class")
class TestPipeJudgeLoadAcceptances:
    async def test_an_output_refining_the_verdict_native_is_admitted(self) -> None:
        bundle = PipeJudgeLoadTestData.bundle(output="Team", step_fields=f'{_MODEL}\noptions = {{ billing = "", technical = "" }}')
        result = await validate_bundle(mthds_contents=[bundle])
        assert "judge_load.judge_it" in {pipe.pipe_ref for pipe in result.pipes}

    async def test_an_input_read_by_the_question_alone_is_admitted(self) -> None:
        """The two-way check runs over the prompt and the question together, so a short parameter may live in the question."""
        bundle = PipeJudgeLoadTestData.bundle(
            inputs='{ message = "Text", topic = "Text" }', question="Is the message about $topic?", step_fields=_MODEL
        )
        await validate_bundle(mthds_contents=[bundle])

    @pytest.mark.usefixtures("judgment_model_reading_files")
    @pytest.mark.parametrize(
        ("inputs", "prompt"),
        [
            pytest.param('{ photo = "Image" }', "Inspect this photo: $photo", id="image"),
            pytest.param('{ photos = "Image[]", claim = "Document" }', "The photos: $photos\nThe claim: $claim", id="images_and_a_document"),
        ],
    )
    async def test_a_file_the_prompt_presents_is_admitted_for_a_model_that_reads_files(self, inputs: str, prompt: str) -> None:
        await validate_bundle(mthds_contents=[PipeJudgeLoadTestData.bundle(inputs=inputs, prompt=prompt, step_fields=_MODEL)])

    async def test_a_dynamic_input_is_admitted_for_a_text_only_model(self) -> None:
        # `Dynamic` is compatible with every concept, `Image` included, so the prompt renders it as text, never as a file.
        bundle = PipeJudgeLoadTestData.bundle(inputs='{ payload = "Dynamic" }', prompt="@payload", step_fields=_MODEL)
        await validate_bundle(mthds_contents=[bundle])

    async def test_an_optional_input_guarded_in_the_prompt_is_admitted(self) -> None:
        """Absence is the template's business: a guarded reference renders nothing when the input is absent."""
        bundle = PipeJudgeLoadTestData.bundle(inputs='{ message = "Text", note = "Text?" }', prompt="@message\n@?note", step_fields=_MODEL)
        await validate_bundle(mthds_contents=[bundle])

    async def test_a_labelled_scale_is_admitted(self) -> None:
        levels = '[{ label = "Cosmetic", description = "Appearance only" }, { label = "Fully blocked" }]'
        bundle = PipeJudgeLoadTestData.bundle(output="Rating", question="How severe is it?", step_fields=f"{_MODEL}\nlevels = {levels}")
        await validate_bundle(mthds_contents=[bundle])

    async def test_a_waterfall_no_backend_serves_is_left_to_the_run(self, unserved_judgment_waterfall: str) -> None:
        # Its model's spec is not on this boot, so whether it reads files is checked when the step runs, as on a keyless boot.
        bundle = PipeJudgeLoadTestData.bundle(
            inputs='{ photo = "Image" }', prompt="Inspect this photo: $photo", step_fields=f'model = "{unserved_judgment_waterfall}"'
        )
        await validate_bundle(mthds_contents=[bundle])

    async def test_several_questions_filling_a_structure_are_admitted(self) -> None:
        """Each field holds its question's verdict native or a concept refining it, and an optional field may be left absent."""
        result = await validate_bundle(mthds_contents=[PipeJudgeSeveralQuestionsTestData.bundle()])
        assert "judge_several.judge_it" in {pipe.pipe_ref for pipe in result.pipes}

    async def test_an_output_refining_the_structured_concept_is_admitted(self) -> None:
        """A refinement inherits the structure it refines, so its fields are the question names all the same."""
        bundle = PipeJudgeSeveralQuestionsTestData.bundle(
            output="UrgentTriage", extra_concepts='UrgentTriage = { description = "The triage of an urgent message", refines = "Triage" }'
        )
        await validate_bundle(mthds_contents=[bundle])

    async def test_a_field_refining_its_verdict_native_is_admitted(self) -> None:
        structure = {
            **PipeJudgeSeveralQuestionsTestData.STRUCTURE,
            "severity": '{ type = "concept", concept_ref = "Severity", description = "How severe it is" }',
        }
        bundle = PipeJudgeSeveralQuestionsTestData.bundle(
            structure=structure, extra_concepts='Severity = { description = "How severe an issue is", refines = "Rating" }'
        )
        await validate_bundle(mthds_contents=[bundle])

    async def test_an_input_read_by_one_of_several_questions_alone_is_admitted(self) -> None:
        questions = {**PipeJudgeSeveralQuestionsTestData.QUESTIONS, "urgent": 'question = "Is the message about $topic and urgent?"'}
        bundle = PipeJudgeSeveralQuestionsTestData.bundle(inputs='{ message = "Text", topic = "Text" }', questions=questions)
        await validate_bundle(mthds_contents=[bundle])

    @pytest.mark.usefixtures("class_backed_triages")
    async def test_several_questions_filling_a_class_backed_structure_are_admitted(self) -> None:
        """A structure that exists only as a Python class offers its class's fields, each typed by its verdict native's class."""
        await validate_bundle(mthds_contents=[PipeJudgeClassBackedTestData.bundle(structure_class_name=ClassBackedTriage.__name__)])
