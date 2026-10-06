import pytest

from pipelex.base_exceptions import ValidationErrorItem
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.validation_error_types import PipeValidationErrorType
from tests.integration.pipelex.pipes.operator.pipe_llm.test_data import LLMSettingCheckTestData

_WITHOUT_THINKING = LLMSettingCheckTestData.MODEL_WITHOUT_THINKING
_WITH_EFFORT = LLMSettingCheckTestData.MODEL_WITH_EFFORT


async def _the_refusal(bundle: str) -> ValidationErrorItem:
    with pytest.raises(ValidateBundleError) as exc_info:
        await validate_bundle(mthds_contents=[bundle])
    items = exc_info.value.validation_error_items()
    assert len(items) == 1, items
    item = items[0]
    assert item.error_type == PipeValidationErrorType.LLM_SETTING_REFUSED_BY_MODEL
    return item


@pytest.mark.asyncio(loop_scope="class")
class TestPipeLLMSettingRefusals:
    @pytest.mark.parametrize(
        ("output", "output_desc"),
        [
            pytest.param("Verdict", "a structured output", id="structured_output"),
            pytest.param("Text", "text", id="text_output"),
            pytest.param("Text[]", "a structured output", id="list_of_texts"),
        ],
    )
    async def test_a_reasoning_effort_on_a_model_without_thinking_is_refused_on_its_field(self, output: str, output_desc: str) -> None:
        bundle = LLMSettingCheckTestData.pipe_llm_bundle(
            output=output,
            model_fields=f'model = {{ model = "{_WITHOUT_THINKING}", temperature = 1, reasoning_effort = "high" }}',
        )
        item = await _the_refusal(bundle)
        assert item.pipe_code == "answer_it"
        assert item.field_name == "model"
        assert item.field_path == "pipe.answer_it.model"
        assert f"PipeLLM 'answer_it' generates {output_desc} with the model setting its `model` writes inline" in item.message
        assert "does not support reasoning (thinking_mode=none)" in item.message
        assert _WITHOUT_THINKING in item.message

    async def test_a_reasoning_budget_on_a_model_taking_an_effort_is_refused(self) -> None:
        bundle = LLMSettingCheckTestData.pipe_llm_bundle(
            output="Verdict",
            model_fields=f'model = {{ model = "{_WITH_EFFORT}", temperature = 1, reasoning_budget = 2048 }}',
        )
        item = await _the_refusal(bundle)
        assert "does not support reasoning_budget; OpenAI uses reasoning_effort instead" in item.message

    async def test_the_structuring_setting_is_checked_on_model_to_structure(self) -> None:
        bundle = LLMSettingCheckTestData.pipe_llm_bundle(
            output="Verdict",
            model_fields=(
                f'model = {{ model = "{_WITH_EFFORT}", temperature = 1, reasoning_effort = "high" }}\n'
                f'model_to_structure = {{ model = "{_WITHOUT_THINKING}", temperature = 1, reasoning_effort = "low" }}'
            ),
        )
        item = await _the_refusal(bundle)
        assert item.field_name == "model_to_structure"
        assert item.field_path == "pipe.answer_it.model_to_structure"

    async def test_a_text_output_is_not_checked_against_its_structuring_setting(self) -> None:
        bundle = LLMSettingCheckTestData.pipe_llm_bundle(
            output="Text",
            model_fields=(
                f'model = {{ model = "{_WITH_EFFORT}", temperature = 1, reasoning_effort = "high" }}\n'
                f'model_to_structure = {{ model = "{_WITHOUT_THINKING}", temperature = 1, reasoning_effort = "low" }}'
            ),
        )
        await validate_bundle(mthds_contents=[bundle])

    async def test_a_list_of_dynamic_outputs_is_checked_against_its_structuring_setting(self) -> None:
        bundle = LLMSettingCheckTestData.pipe_llm_bundle(
            output="Dynamic[]",
            model_fields=(
                f'model = {{ model = "{_WITH_EFFORT}", temperature = 1, reasoning_effort = "high" }}\n'
                f'model_to_structure = {{ model = "{_WITHOUT_THINKING}", temperature = 1, reasoning_effort = "low" }}'
            ),
        )
        item = await _the_refusal(bundle)
        assert item.field_name == "model_to_structure"
        assert "PipeLLM 'answer_it' generates a structured output" in item.message

    @pytest.mark.parametrize("output", ["Dynamic", "Text"])
    async def test_a_single_dynamic_or_text_output_is_checked_against_its_text_setting(self, output: str) -> None:
        bundle = LLMSettingCheckTestData.pipe_llm_bundle(
            output=output,
            model_fields=(
                f'model = {{ model = "{_WITHOUT_THINKING}", temperature = 1, reasoning_effort = "high" }}\n'
                f'model_to_structure = {{ model = "{_WITH_EFFORT}", temperature = 1, reasoning_effort = "low" }}'
            ),
        )
        item = await _the_refusal(bundle)
        assert item.field_name == "model"
        assert "PipeLLM 'answer_it' generates text" in item.message

    async def test_a_list_of_dynamic_outputs_is_not_checked_against_its_text_setting(self) -> None:
        bundle = LLMSettingCheckTestData.pipe_llm_bundle(
            output="Dynamic[]",
            model_fields=(
                f'model = {{ model = "{_WITHOUT_THINKING}", temperature = 1, reasoning_effort = "high" }}\n'
                f'model_to_structure = {{ model = "{_WITH_EFFORT}", temperature = 1, reasoning_effort = "low" }}'
            ),
        )
        await validate_bundle(mthds_contents=[bundle])

    @pytest.mark.parametrize("output", ["Verdict", "Text"])
    async def test_a_reasoning_effort_the_model_takes_validates(self, output: str) -> None:
        bundle = LLMSettingCheckTestData.pipe_llm_bundle(
            output=output,
            model_fields=f'model = {{ model = "{_WITH_EFFORT}", temperature = 1, reasoning_effort = "high" }}',
        )
        await validate_bundle(mthds_contents=[bundle])

    async def test_a_pipe_structure_setting_is_refused_on_its_field(self) -> None:
        bundle = LLMSettingCheckTestData.pipe_structure_bundle(
            model_fields=f'model = {{ model = "{_WITHOUT_THINKING}", temperature = 1, reasoning_effort = "medium" }}',
        )
        item = await _the_refusal(bundle)
        assert item.pipe_code == "structure_it"
        assert item.field_name == "model"
        assert "PipeStructure 'structure_it' generates a structured output" in item.message
