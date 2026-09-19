"""The ``run_mode == DRY`` branch in the judgment leaf.

Contract: under DRY the leaf mints a deterministic verdict per question without resolving any worker
or touching the model deck, and — the part that matters most for this family — it reports no
uncertainty at all. LIVE keeps the real path.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.assignment_models import JudgmentAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.judgment_generate import judgment_gen_answers
from pipelex.cogt.judgment.judgment_models import (
    ChoiceAnswer,
    ChoiceQuestion,
    RatingAnswer,
    RatingQuestion,
    YesNoAnswer,
    YesNoQuestion,
)
from pipelex.cogt.judgment.judgment_setting import JudgmentSetting
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode


class TestJudgmentGenerateDryBranch:
    def _assignment(self, *, run_mode: PipeRunMode) -> JudgmentAssignment:
        return JudgmentAssignment(
            job_metadata=JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", user_id="u", pipeline_run_id="run_judgment_dry")),
            cogt_run_params=CogtRunParams(run_mode=run_mode),
            state={"message": "the roof is on fire"},
            questions={
                "is_urgent": YesNoQuestion(instructions="Does this need an answer today?"),
                "topic": ChoiceQuestion(instructions="What is this about?", options={"fire": None, "flood": "water damage"}),
                "severity": RatingQuestion(instructions="How severe?", levels=["mild", "bad", "critical"]),
            },
            judgment_setting=JudgmentSetting(model="mock-judgment-handle"),
        )

    @pytest.mark.asyncio
    async def test_dry_mints_answers_without_worker(self, mocker: MockerFixture) -> None:
        """DRY: one deterministic answer per question; the model deck is never resolved."""
        deck_spy = mocker.patch("pipelex.cogt.content_generation.judgment_generate.get_model_deck")

        answers = await judgment_gen_answers(self._assignment(run_mode=PipeRunMode.DRY))

        deck_spy.assert_not_called()
        assert set(answers) == {"is_urgent", "topic", "severity"}
        yes_no = answers["is_urgent"]
        choice = answers["topic"]
        rating = answers["severity"]
        assert isinstance(yes_no, YesNoAnswer)
        assert isinstance(choice, ChoiceAnswer)
        assert isinstance(rating, RatingAnswer)
        assert yes_no.yes_no is True
        assert choice.choice == "fire"
        assert rating.level == 0

    @pytest.mark.asyncio
    async def test_dry_reports_no_uncertainty(self) -> None:
        """Nothing measured anything, so every uncertainty member is absent rather than invented."""
        answers = await judgment_gen_answers(self._assignment(run_mode=PipeRunMode.DRY))

        yes_no = answers["is_urgent"]
        choice = answers["topic"]
        rating = answers["severity"]
        assert isinstance(yes_no, YesNoAnswer)
        assert isinstance(choice, ChoiceAnswer)
        assert isinstance(rating, RatingAnswer)
        assert yes_no.probability is None
        assert choice.confidence is None
        assert choice.probabilities is None
        assert rating.position is None
        assert rating.confidence is None
        assert rating.probabilities is None

    @pytest.mark.asyncio
    async def test_live_resolves_worker(self, mocker: MockerFixture) -> None:
        """LIVE keeps the real path: the worker is resolved from the deck and runs the judgment."""
        sentinel = mocker.MagicMock()
        worker = mocker.MagicMock()
        worker.judge = mocker.AsyncMock(return_value=sentinel)
        mocker.patch("pipelex.cogt.content_generation.judgment_generate._make_judgment_worker", return_value=worker)
        mocker.patch("pipelex.cogt.content_generation.judgment_generate._make_judgment_job", return_value=mocker.MagicMock())

        result = await judgment_gen_answers(self._assignment(run_mode=PipeRunMode.LIVE))

        worker.judge.assert_awaited_once()
        assert result is sentinel
