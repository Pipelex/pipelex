"""What a PipeJudge step may declare and still load."""

import pytest

from pipelex.pipeline.validate_bundle import validate_bundle
from tests.integration.pipelex.pipes.operator.pipe_judge.test_data import PipeJudgeLoadTestData

_MODEL = f'model = "{PipeJudgeLoadTestData.JUDGMENT_MODEL}"'


@pytest.mark.asyncio(loop_scope="class")
class TestPipeJudgeLoadAcceptances:
    async def test_an_output_refining_the_verdict_native_is_admitted(self) -> None:
        bundle = PipeJudgeLoadTestData.bundle(output="Team", step_fields=f'{_MODEL}\noptions = {{ billing = "", technical = "" }}')
        result = await validate_bundle(mthds_contents=[bundle])
        assert "judge_load.judge_it" in {pipe.pipe_ref for pipe in result.pipes}

    async def test_an_input_the_question_never_names_is_material(self) -> None:
        bundle = PipeJudgeLoadTestData.bundle(inputs='{ message = "Text", ticket = "Ticket" }', step_fields=_MODEL)
        await validate_bundle(mthds_contents=[bundle])

    @pytest.mark.usefixtures("judgment_model_reading_files")
    @pytest.mark.parametrize("inputs", ['{ photo = "Image" }', '{ photos = "Image[]", claim = "Document" }'])
    async def test_a_file_input_is_admitted_for_a_model_that_reads_files(self, inputs: str) -> None:
        await validate_bundle(mthds_contents=[PipeJudgeLoadTestData.bundle(inputs=inputs, step_fields=_MODEL)])

    async def test_a_dynamic_input_is_admitted_for_a_text_only_model(self) -> None:
        # `Dynamic` is compatible with every concept, `Image` included, so its value is checked when it runs, never at load.
        await validate_bundle(mthds_contents=[PipeJudgeLoadTestData.bundle(inputs='{ payload = "Dynamic" }', step_fields=_MODEL)])

    async def test_a_waterfall_no_backend_serves_is_left_to_the_run(self, unserved_judgment_waterfall: str) -> None:
        # Its model's spec is not on this boot, so whether it reads files is checked when the step runs, as on a keyless boot.
        bundle = PipeJudgeLoadTestData.bundle(inputs='{ photo = "Image" }', step_fields=f'model = "{unserved_judgment_waterfall}"')
        await validate_bundle(mthds_contents=[bundle])
