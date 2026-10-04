"""E2E tests for the PipeJudge operator: one question of each kind, run on the deck's default judgment model."""

import pytest

from pipelex import pretty_print
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.e2e.pipelex.pipes.pipe_operators.pipe_judge.test_data import PipeJudgeTestCases

LIBRARY_DIRS = ["tests/e2e/pipelex/pipes/pipe_operators/pipe_judge"]

# A judgment model's probabilities drift a little between versions, never across a verdict.
PROBABILITY_TOLERANCE = 0.05


@pytest.mark.judgment
@pytest.mark.inference
@pytest.mark.dry_runnable
@pytest.mark.asyncio(loop_scope="class")
class TestPipeJudge:
    async def test_yes_no_question(self, pipe_run_mode: PipeRunMode) -> None:
        runner = PipelexMTHDSProtocol(library_dirs=LIBRARY_DIRS, pipe_run_mode=pipe_run_mode)
        pipeline_response = await runner.execute(
            pipe_code="judge_urgent_e2e",
            inputs={"message": TextContent(text=PipeJudgeTestCases.URGENT_MESSAGE)},
        )

        pipe_output = pipeline_response.pipe_output
        assert pipe_output is not None
        verdict = pipe_output.main_stuff_as_yes_no
        if pipe_run_mode.is_live:
            pretty_print(verdict, title="Yes/no judgment")
            # The declared threshold of 0.7 decides the verdict from the probability.
            assert verdict.yes_no is True
            assert verdict.probability is not None
            assert abs(verdict.probability - 0.98) <= PROBABILITY_TOLERANCE

    async def test_choice_question(self, pipe_run_mode: PipeRunMode) -> None:
        runner = PipelexMTHDSProtocol(library_dirs=LIBRARY_DIRS, pipe_run_mode=pipe_run_mode)
        pipeline_response = await runner.execute(
            pipe_code="judge_team_e2e",
            inputs={"ticket": TextContent(text=PipeJudgeTestCases.BILLING_TICKET)},
        )

        pipe_output = pipeline_response.pipe_output
        assert pipe_output is not None
        verdict = pipe_output.main_stuff_as_choice
        if pipe_run_mode.is_live:
            pretty_print(verdict, title="Choice judgment")
            assert verdict.choice == "billing"
            assert verdict.probabilities is not None
            assert set(verdict.probabilities) == {"billing", "technical", "other"}
            assert abs(verdict.probabilities["billing"] - 1.0) <= PROBABILITY_TOLERANCE

    async def test_choice_routes_a_condition(self, pipe_run_mode: PipeRunMode) -> None:
        runner = PipelexMTHDSProtocol(library_dirs=LIBRARY_DIRS, pipe_run_mode=pipe_run_mode)
        pipeline_response = await runner.execute(
            pipe_code="route_ticket_e2e",
            inputs={"ticket": TextContent(text=PipeJudgeTestCases.BILLING_TICKET)},
        )

        pipe_output = pipeline_response.pipe_output
        assert pipe_output is not None
        acknowledgement = pipe_output.main_stuff_as_text
        if pipe_run_mode.is_live:
            assert acknowledgement.text.startswith("Sent to billing:")

    async def test_rating_question(self, pipe_run_mode: PipeRunMode) -> None:
        runner = PipelexMTHDSProtocol(library_dirs=LIBRARY_DIRS, pipe_run_mode=pipe_run_mode)
        pipeline_response = await runner.execute(
            pipe_code="judge_severity_e2e",
            inputs={"report": TextContent(text=PipeJudgeTestCases.BLOCKING_REPORT)},
        )

        pipe_output = pipeline_response.pipe_output
        assert pipe_output is not None
        verdict = pipe_output.main_stuff_as_rating
        if pipe_run_mode.is_live:
            pretty_print(verdict, title="Rating judgment")
            assert verdict.level == 2
            assert verdict.probabilities is not None
            assert set(verdict.probabilities) == {"0", "1", "2"}
            assert verdict.position is not None
            assert abs(verdict.position - 2.0) <= PROBABILITY_TOLERANCE * 2
