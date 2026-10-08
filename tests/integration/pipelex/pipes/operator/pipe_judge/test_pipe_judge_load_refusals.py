"""A PipeJudge step is refused when its method loads, before a run spends anything, for each thing it cannot do."""

import pytest

from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.runtime_hub import get_model_deck
from tests.integration.pipelex.pipes.operator.pipe_judge.test_data import PipeJudgeLoadTestData

_MODEL = f'model = "{PipeJudgeLoadTestData.JUDGMENT_MODEL}"'


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
    async def test_a_file_input_is_refused_for_a_text_only_model(self, inputs: str, file_kind: str) -> None:
        report = await _refusal_report(PipeJudgeLoadTestData.bundle(inputs=inputs, step_fields=_MODEL))
        assert f"does not read {file_kind}" in report
        assert "'photo'" in report
        assert PipeJudgeLoadTestData.JUDGMENT_MODEL in report

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
