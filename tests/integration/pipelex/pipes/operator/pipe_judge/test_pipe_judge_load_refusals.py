"""A PipeJudge step is refused when its method loads, before a run spends anything, for each thing it cannot do."""

import pytest

from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.runtime_hub import get_model_deck
from tests.integration.pipelex.pipes.operator.pipe_judge.test_data import (
    ClassBackedOpenTriage,
    PipeJudgeClassBackedTestData,
    PipeJudgeLoadTestData,
    PipeJudgeSeveralQuestionsTestData,
)

_MODEL = f'model = "{PipeJudgeLoadTestData.JUDGMENT_MODEL}"'
_STRUCTURE = PipeJudgeSeveralQuestionsTestData.STRUCTURE
_QUESTIONS = PipeJudgeSeveralQuestionsTestData.QUESTIONS


async def _refusal_report(bundle: str) -> str:
    with pytest.raises(ValidateBundleError) as exc_info:
        await validate_bundle(mthds_contents=[bundle])
    return str(exc_info.value.to_error_report().model_dump())


@pytest.mark.asyncio(loop_scope="class")
class TestPipeJudgeLoadRefusals:
    @pytest.mark.usefixtures("no_judgment_default")
    async def test_a_step_with_no_model_and_no_default_is_refused(self) -> None:
        report = await _refusal_report(PipeJudgeLoadTestData.bundle())
        assert "PipeJudge 'judge_it' has no judgment model" in report
        assert "`choice_default` under `[judgment]`" in report

    async def test_an_unknown_model_is_refused_on_its_field(self) -> None:
        report = await _refusal_report(PipeJudgeLoadTestData.bundle(step_fields='model = "jev-9.99.9"'))
        assert "jev-9.99.9" in report
        assert "model" in report

    async def test_a_model_the_deck_serves_only_as_an_llm_is_refused(self) -> None:
        """A handle names one model per model type: an LLM of that name is no judgment model, and the load says so."""
        served_models = get_model_deck().inference_models
        llm_only_handle = next(
            handle
            for handle in served_models.handles_of_type(model_type=ModelType.LLM)
            if ModelType.JUDGMENT not in served_models.types_serving(handle=handle)
        )

        report = await _refusal_report(PipeJudgeLoadTestData.bundle(step_fields=f'model = "{llm_only_handle}"'))

        assert llm_only_handle in report
        assert "field 'model'" in report
        assert "'unknown_model'" in report
        assert "'model_type': 'judgment'" in report

    @pytest.mark.parametrize(
        ("inputs", "file_kind"),
        [
            pytest.param('{ photo = "Image" }', "images", id="image"),
            pytest.param('{ photo = "Image[]" }', "images", id="list_of_images"),
            pytest.param('{ photo = "Document" }', "documents", id="document"),
        ],
    )
    async def test_a_file_the_prompt_presents_is_refused_for_a_text_only_model(self, inputs: str, file_kind: str) -> None:
        report = await _refusal_report(PipeJudgeLoadTestData.bundle(inputs=inputs, prompt="Inspect this: $photo", step_fields=_MODEL))
        assert f"does not read {file_kind}" in report
        assert "presents 'photo' in its prompt" in report
        assert PipeJudgeLoadTestData.JUDGMENT_MODEL in report

    @pytest.mark.usefixtures("judgment_model_reading_files")
    @pytest.mark.parametrize(
        "inputs",
        [
            pytest.param('{ message = "Text", photo = "Image" }', id="image"),
            pytest.param('{ message = "Text", photo = "Document" }', id="document"),
        ],
    )
    async def test_a_file_read_by_the_question_is_refused(self, inputs: str) -> None:
        """A question is plain text, so a file it read would reach the model as a token naming nothing, whatever the model reads."""
        report = await _refusal_report(PipeJudgeLoadTestData.bundle(inputs=inputs, question="Is $photo damaged?", step_fields=_MODEL))
        assert "reads 'photo' in its question" in report
        assert "only the prompt presents files" in report
        assert "'input_stuff_spec_mismatch'" in report

    @pytest.mark.parametrize(
        ("prompt", "question"),
        [
            pytest.param("@message\n$note", "Is it urgent?", id="in_the_prompt"),
            pytest.param("@message", "Is it urgent, given $note?", id="in_the_question"),
        ],
    )
    async def test_an_unguarded_optional_input_is_refused(self, prompt: str, question: str) -> None:
        """Both templates are linted, so an optional input read without a guard is refused wherever it is read."""
        bundle = PipeJudgeLoadTestData.bundle(inputs='{ message = "Text", note = "Text?" }', prompt=prompt, question=question, step_fields=_MODEL)
        report = await _refusal_report(bundle)
        assert "'optional_input_unguarded'" in report
        assert "note" in report

    async def test_an_input_neither_template_reads_is_refused(self) -> None:
        report = await _refusal_report(PipeJudgeLoadTestData.bundle(inputs='{ message = "Text", ticket = "Ticket" }', step_fields=_MODEL))
        assert "Input 'ticket' is declared but never read by the prompt or question" in report

    async def test_a_bundle_writing_its_question_in_prompt_is_told_where_each_goes(self) -> None:
        """Before MTHDS 5.0.0 `prompt` was a synonym of `question`, so a bundle written then holds its question in `prompt`."""
        report = await _refusal_report(PipeJudgeLoadTestData.bundle(prompt="Is the message urgent?\n@message", question=None, step_fields=_MODEL))
        assert "`prompt` holds the evidence the question is asked over, and the question is written in `question`" in report

    @pytest.mark.parametrize(
        ("output", "step_fields", "asks"),
        [
            pytest.param(
                "YesNo",
                'options = { billing = "", technical = "" }',
                "asks a choice question: its output must be `Choice`",
                id="choice_into_yes_no",
            ),
            pytest.param("Choice", 'levels = ["low", "high"]', "asks a rating question: its output must be `Rating`", id="rating_into_choice"),
            pytest.param("Text", "", "asks a yes/no question: its output must be `YesNo`", id="yes_no_into_text"),
            pytest.param("Dynamic", "", "asks a yes/no question: its output must be `YesNo`", id="yes_no_into_dynamic"),
        ],
    )
    async def test_an_output_disagreeing_with_the_kind_is_refused_naming_both_sides(self, output: str, step_fields: str, asks: str) -> None:
        report = await _refusal_report(PipeJudgeLoadTestData.bundle(output=output, step_fields=f"{_MODEL}\n{step_fields}"))
        assert asks in report
        assert f"declares `native.{output}`" in report

    @pytest.mark.parametrize(
        ("output", "shape"),
        [
            pytest.param("Text", "holds its value in a single field", id="a_single_field_native"),
            pytest.param("Note", "is declared with neither a structure nor refines", id="a_concept_described_only"),
            pytest.param("Dynamic", "is structureless by definition", id="dynamic"),
        ],
    )
    async def test_several_questions_into_an_output_without_a_structure_are_refused(self, output: str, shape: str) -> None:
        report = await _refusal_report(PipeJudgeSeveralQuestionsTestData.bundle(output=output))
        assert "fills a structure with one verdict per question, so its output must be a concept with a structure" in report
        assert shape in report
        assert "'inadequate_output_concept'" in report

    async def test_a_field_no_question_answers_is_refused(self) -> None:
        """Nothing could ever fill such a field, so the load refuses it, required or not."""
        structure = {**_STRUCTURE, "notes": '{ type = "text", description = "Notes" }'}
        report = await _refusal_report(PipeJudgeSeveralQuestionsTestData.bundle(structure=structure))
        assert "the field 'notes', which no question answers" in report
        assert "`judge_several.Triage`" in report

    async def test_a_question_with_no_field_is_refused(self) -> None:
        structure = {name: field for name, field in _STRUCTURE.items() if name != "severity"}
        report = await _refusal_report(PipeJudgeSeveralQuestionsTestData.bundle(structure=structure))
        assert "The question 'severity' has no field of `judge_several.Triage` to hold its verdict" in report

    @pytest.mark.parametrize(
        ("field", "complaint"),
        [
            pytest.param(
                '{ type = "list", item_type = "concept", item_concept_ref = "YesNo", description = "Verdicts", required = true }',
                "holds a list, and the question 'urgent' produces one verdict",
                id="a_list_of_verdicts",
            ),
            pytest.param(
                '{ type = "boolean", description = "Whether it is urgent", required = true }',
                "holds a plain value rather than a concept, and the question 'urgent' asks a yes/no question",
                id="a_plain_boolean",
            ),
            pytest.param(
                '{ type = "concept", concept_ref = "Choice", description = "A choice", required = true }',
                "The question 'urgent' asks a yes/no question, so its field must hold `native.YesNo` or a concept refining it, "
                "and it holds `native.Choice`",
                id="the_verdict_of_another_kind",
            ),
            pytest.param(
                '{ type = "concept", concept_ref = "Dynamic", description = "Anything at all", required = true }',
                "so its field must hold `native.YesNo` or a concept refining it, and it holds `native.Dynamic`",
                id="dynamic",
            ),
            pytest.param(
                '{ type = "concept", concept_ref = "Anything", description = "Any value at all", required = true }',
                "so its field must hold `native.YesNo` or a concept refining it, and it holds `native.Anything`",
                id="anything",
            ),
        ],
    )
    async def test_a_field_that_cannot_hold_its_question_verdict_is_refused(self, field: str, complaint: str) -> None:
        report = await _refusal_report(PipeJudgeSeveralQuestionsTestData.bundle(structure={**_STRUCTURE, "urgent": field}))
        assert complaint in report
        assert "'inadequate_output_concept'" in report

    @pytest.mark.usefixtures("class_backed_triages")
    async def test_a_class_field_no_concept_describes_is_refused(self) -> None:
        report = await _refusal_report(PipeJudgeClassBackedTestData.bundle(structure_class_name=ClassBackedOpenTriage.__name__))
        assert "holds a value no concept describes, since its Python type" in report
        assert "maps to no concept, and the question 'urgent' asks a yes/no question" in report
        assert "'inadequate_output_concept'" in report

    @pytest.mark.usefixtures("judgment_model_reading_files")
    async def test_a_file_read_by_one_of_several_questions_is_refused_naming_it(self) -> None:
        questions = {**_QUESTIONS, "urgent": 'question = "Is $photo showing an emergency?"'}
        report = await _refusal_report(PipeJudgeSeveralQuestionsTestData.bundle(inputs='{ message = "Text", photo = "Image" }', questions=questions))
        assert "reads 'photo' in its question 'urgent'" in report
        assert "only the prompt presents files" in report
        assert "'input_stuff_spec_mismatch'" in report

    async def test_an_unguarded_optional_input_in_one_of_several_questions_is_refused(self) -> None:
        questions = {**_QUESTIONS, "team": 'question = "Which team handles it, given $note?"\noptions = { billing = "", technical = "" }'}
        report = await _refusal_report(PipeJudgeSeveralQuestionsTestData.bundle(inputs='{ message = "Text", note = "Text?" }', questions=questions))
        assert "'optional_input_unguarded'" in report
        assert "note" in report
