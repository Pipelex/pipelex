"""A PipeJudge whose evidence prompt reads an optional file runs whether the file is given or not."""

from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.assignment_models import JudgmentAssignment
from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.cogt.judgment.judgment_models import JudgmentOutcome, YesNoAnswer
from pipelex.core.stuffs.text_content import TextContent
from pipelex.kernel import judgment_ops
from pipelex.kernel.prompt_assembly import AssembledUserPrompt
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.pipes.operator.pipe_judge.test_data import PipeJudgeOptionalFileTestData


def _answer_yes(*, judgment_assignment: JudgmentAssignment) -> dict[str, JudgmentOutcome]:
    return dict.fromkeys(judgment_assignment.questions, YesNoAnswer(probability=0.9))


@pytest.mark.usefixtures("judgment_model_reading_files")
@pytest.mark.asyncio(loop_scope="class")
class TestPipeJudgeOptionalFiles:
    @pytest.mark.parametrize("pipe_run_mode", [PipeRunMode.DRY, PipeRunMode.LIVE])
    @pytest.mark.parametrize(("topic", "optional_input", "prompt"), PipeJudgeOptionalFileTestData.ABSENT_CASES)
    async def test_an_absent_optional_file_is_left_out_of_the_evidence(
        self,
        mocker: MockerFixture,
        pipe_run_mode: PipeRunMode,
        topic: str,  # ruff: ignore[unused-method-argument]
        optional_input: str,
        prompt: str,
    ) -> None:
        """The guard renders the absent file out, and the judgment runs over the rest of the evidence with no file to present."""
        assembly_spy = mocker.spy(judgment_ops, "assemble_user_prompt")
        if pipe_run_mode.is_live:
            # The live run's content generator answers here without calling any model; the dry run keeps its own mock.
            mocker.patch.object(ContentGenerator, "make_judgment_answers", side_effect=_answer_yes)

        response = await PipelexMTHDSProtocol(pipe_run_mode=pipe_run_mode).execute(
            mthds_contents=[PipeJudgeOptionalFileTestData.bundle(optional_input=optional_input, prompt=prompt)],
            pipe_code=PipeJudgeOptionalFileTestData.PIPE_CODE,
            inputs={"note": TextContent(text=PipeJudgeOptionalFileTestData.NOTE)},
        )

        evidence = assembly_spy.spy_return
        assert isinstance(evidence, AssembledUserPrompt)
        assert evidence.text.strip() == f"A claim note: {PipeJudgeOptionalFileTestData.NOTE}"
        assert evidence.images == []
        assert evidence.documents == []
        assert response.pipe_output is not None
        verdict = response.pipe_output.main_stuff_as_yes_no
        if pipe_run_mode.is_live:
            assert verdict.yes_no is True

    async def test_a_present_optional_file_is_attached_and_numbered(self, mocker: MockerFixture) -> None:
        assembly_spy = mocker.spy(judgment_ops, "assemble_user_prompt")
        _topic, optional_input, prompt = PipeJudgeOptionalFileTestData.ABSENT_CASES[0]
        inputs: dict[str, Any] = {
            "note": TextContent(text=PipeJudgeOptionalFileTestData.NOTE),
            "photo": {"concept": "native.Image", "content": {"url": PipeJudgeOptionalFileTestData.PHOTO_URL}},
        }

        await PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY).execute(
            mthds_contents=[PipeJudgeOptionalFileTestData.bundle(optional_input=optional_input, prompt=prompt)],
            pipe_code=PipeJudgeOptionalFileTestData.PIPE_CODE,
            inputs=inputs,
        )

        evidence = assembly_spy.spy_return
        assert isinstance(evidence, AssembledUserPrompt)
        assert "[Image 1]" in evidence.text
        assert len(evidence.images) == 1

    @pytest.mark.parametrize("pipe_run_mode", [PipeRunMode.DRY, PipeRunMode.LIVE])
    async def test_a_missing_required_file_is_refused(self, mocker: MockerFixture, pipe_run_mode: PipeRunMode) -> None:
        judge_spy = mocker.patch.object(ContentGenerator, "make_judgment_answers", side_effect=_answer_yes)
        with pytest.raises(PipelineExecutionError) as exc_info:
            await PipelexMTHDSProtocol(pipe_run_mode=pipe_run_mode).execute(
                mthds_contents=[PipeJudgeOptionalFileTestData.bundle(optional_input='photo = "Image"', prompt="A claim note: $note\n@photo\n")],
                pipe_code=PipeJudgeOptionalFileTestData.PIPE_CODE,
                inputs={"note": TextContent(text=PipeJudgeOptionalFileTestData.NOTE)},
            )
        assert "missing required inputs: photo" in str(exc_info.value)
        judge_spy.assert_not_called()
