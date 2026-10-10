"""E2E tests for PipeJudge: one question of each kind, asked about the evidence its prompt presents, on the default judgment model."""

import pytest

from pipelex import pretty_print
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.e2e.pipelex.pipes.pipe_operators.pipe_judge.test_data import PipeJudgeTestCases

LIBRARY_DIRS = ["tests/e2e/pipelex/pipes/pipe_operators/pipe_judge"]

# A judgment model's probabilities drift a little between versions, never across a verdict.
PROBABILITY_TOLERANCE = 0.05


def _assert_sent(*, pipe_output: PipeOutput, pipe_code: str, evidence: str, question: str) -> None:
    """The judge sent exactly this evidence and this question, as its execution data records them."""
    graph_spec = pipe_output.graph_spec
    assert graph_spec is not None
    (judge_node,) = [node for node in graph_spec.nodes if node.pipe_code == pipe_code]
    assert judge_node.execution_data["rendered_prompt"] == evidence
    assert judge_node.execution_data["rendered_question"] == question
    assert judge_node.execution_data["nb_prompt_images"] == 0
    assert judge_node.execution_data["nb_prompt_documents"] == 0


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
        _assert_sent(
            pipe_output=pipe_output,
            pipe_code="judge_urgent_e2e",
            evidence=PipeJudgeTestCases.URGENT_EVIDENCE,
            question=PipeJudgeTestCases.URGENT_QUESTION,
        )
        verdict = pipe_output.main_stuff_as_yes_no
        if pipe_run_mode.is_live:
            pretty_print(verdict, title="Yes/no judgment")
            # The declared threshold of 0.7 decides the verdict from the probability.
            assert verdict.yes_no is True
            assert verdict.probability is not None
            assert abs(verdict.probability - PipeJudgeTestCases.EXPECTED_URGENT_PROBABILITY) <= PROBABILITY_TOLERANCE

    async def test_choice_question(self, pipe_run_mode: PipeRunMode) -> None:
        runner = PipelexMTHDSProtocol(library_dirs=LIBRARY_DIRS, pipe_run_mode=pipe_run_mode)
        pipeline_response = await runner.execute(
            pipe_code="judge_team_e2e",
            inputs={"ticket": TextContent(text=PipeJudgeTestCases.BILLING_TICKET)},
        )

        pipe_output = pipeline_response.pipe_output
        assert pipe_output is not None
        _assert_sent(
            pipe_output=pipe_output,
            pipe_code="judge_team_e2e",
            evidence=PipeJudgeTestCases.BILLING_EVIDENCE,
            question=PipeJudgeTestCases.BILLING_QUESTION,
        )
        verdict = pipe_output.main_stuff_as_choice
        if pipe_run_mode.is_live:
            pretty_print(verdict, title="Choice judgment")
            assert verdict.choice == "billing"
            assert verdict.probabilities is not None
            assert set(verdict.probabilities) == {"billing", "technical", "other"}
            assert abs(verdict.probabilities["billing"] - PipeJudgeTestCases.EXPECTED_BILLING_PROBABILITY) <= PROBABILITY_TOLERANCE

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

    async def test_rating_question_on_a_labelled_scale(self, pipe_run_mode: PipeRunMode) -> None:
        runner = PipelexMTHDSProtocol(library_dirs=LIBRARY_DIRS, pipe_run_mode=pipe_run_mode)
        pipeline_response = await runner.execute(
            pipe_code="judge_severity_e2e",
            inputs={"report": TextContent(text=PipeJudgeTestCases.BLOCKING_REPORT)},
        )

        pipe_output = pipeline_response.pipe_output
        assert pipe_output is not None
        _assert_sent(
            pipe_output=pipe_output,
            pipe_code="judge_severity_e2e",
            evidence=PipeJudgeTestCases.BLOCKING_EVIDENCE,
            question=PipeJudgeTestCases.BLOCKING_QUESTION,
        )
        verdict = pipe_output.main_stuff_as_rating
        # Dry or live, the verdict carries the label the scale declares for the level it lands on.
        assert verdict.label == PipeJudgeTestCases.SEVERITY_LABELS[verdict.level]
        if pipe_run_mode.is_live:
            pretty_print(verdict, title="Rating judgment")
            assert verdict.level == PipeJudgeTestCases.EXPECTED_BLOCKING_LEVEL
            assert verdict.label == "Blocking"
            assert verdict.probabilities is not None
            assert set(verdict.probabilities) == {"0", "1", "2"}
            assert verdict.position is not None
            assert abs(verdict.position - PipeJudgeTestCases.EXPECTED_BLOCKING_POSITION) <= PROBABILITY_TOLERANCE * 2
