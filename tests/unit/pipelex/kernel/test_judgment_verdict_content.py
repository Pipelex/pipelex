"""The verdict native an answer becomes, the label a rating takes from its scale, and what became of a declared threshold."""

from typing import ClassVar

import pytest

from pipelex.cogt.judgment.judgment_models import (
    ChoiceAnswer,
    ChoiceQuestion,
    RatingAnswer,
    RatingLevel,
    RatingQuestion,
    YesNoAnswer,
    YesNoQuestion,
)
from pipelex.core.stuffs.choice_content import ChoiceContent
from pipelex.core.stuffs.rating_content import RatingContent
from pipelex.core.stuffs.yes_no_content import YesNoContent
from pipelex.kernel.judgment_ops import make_verdict_content


class TestVerdictContent:
    _YES_NO: ClassVar[YesNoQuestion] = YesNoQuestion(instructions="Is it urgent?")
    _CHOICE: ClassVar[ChoiceQuestion] = ChoiceQuestion(instructions="Which team?", options={"billing": None, "technical": None})
    _UNLABELLED_SCALE: ClassVar[RatingQuestion] = RatingQuestion(
        instructions="How severe?", levels=[RatingLevel(description="mild"), RatingLevel(description="bad"), RatingLevel(description="critical")]
    )
    _LABELLED_SCALE: ClassVar[RatingQuestion] = RatingQuestion(
        instructions="How severe?",
        levels=[
            RatingLevel(label="Cosmetic", description="Appearance only"),
            RatingLevel(label="Workaround available"),
            RatingLevel(label="Fully blocked", description="A task fails with no workaround"),
        ],
    )

    @pytest.mark.parametrize(
        ("probability", "threshold", "expected_yes_no"),
        [
            pytest.param(0.7, 0.7, True, id="at_the_threshold"),
            pytest.param(0.6999, 0.7, False, id="just_under"),
            pytest.param(0.7001, 0.7, True, id="just_over"),
            pytest.param(0.5, None, True, id="at_the_default"),
            pytest.param(0.4999, None, False, id="just_under_the_default"),
        ],
    )
    def test_a_probability_decides_the_verdict_against_the_threshold(
        self, probability: float, threshold: float | None, expected_yes_no: bool
    ) -> None:
        content, threshold_applied = make_verdict_content(
            question=self._YES_NO, answer=YesNoAnswer(probability=probability), threshold=threshold, is_dry=False
        )

        assert content == YesNoContent(yes_no=expected_yes_no, probability=probability)
        assert threshold_applied is (True if threshold is not None else None)

    def test_a_probability_outranks_the_models_own_verdict(self) -> None:
        content, _ = make_verdict_content(question=self._YES_NO, answer=YesNoAnswer(probability=0.3, yes_no=True), threshold=0.5, is_dry=False)

        assert content == YesNoContent(yes_no=False, probability=0.3)

    @pytest.mark.parametrize(
        ("threshold", "is_dry", "expected_threshold_applied"),
        [
            pytest.param(0.8, False, False, id="declared_threshold_live"),
            pytest.param(0.8, True, None, id="declared_threshold_dry"),
            pytest.param(None, False, None, id="no_threshold_live"),
        ],
    )
    def test_without_a_probability_the_models_verdict_stands(
        self, threshold: float | None, is_dry: bool, expected_threshold_applied: bool | None
    ) -> None:
        content, threshold_applied = make_verdict_content(question=self._YES_NO, answer=YesNoAnswer(yes_no=False), threshold=threshold, is_dry=is_dry)

        assert content == YesNoContent(yes_no=False)
        assert threshold_applied is expected_threshold_applied

    def test_a_choice_is_carried_as_reported(self) -> None:
        answer = ChoiceAnswer(choice="billing", confidence=0.8, probabilities={"billing": 0.8, "technical": 0.2})

        content, threshold_applied = make_verdict_content(question=self._CHOICE, answer=answer, threshold=None, is_dry=False)

        assert content == ChoiceContent(choice="billing", confidence=0.8, probabilities={"billing": 0.8, "technical": 0.2})
        assert threshold_applied is None

    def test_a_ratings_distribution_is_keyed_by_the_level_index_as_text(self) -> None:
        answer = RatingAnswer(level=2, position=1.8, confidence=0.7, probabilities={0: 0.1, 1: 0.2, 2: 0.7})

        content, _ = make_verdict_content(question=self._UNLABELLED_SCALE, answer=answer, threshold=None, is_dry=False)

        assert content == RatingContent(level=2, position=1.8, confidence=0.7, probabilities={"0": 0.1, "1": 0.2, "2": 0.7})

    def test_nothing_absent_is_synthesised(self) -> None:
        content, _ = make_verdict_content(question=self._UNLABELLED_SCALE, answer=RatingAnswer(level=0), threshold=None, is_dry=False)

        assert content == RatingContent(level=0)

    @pytest.mark.parametrize(
        ("level", "expected_label"),
        [
            pytest.param(0, "Cosmetic", id="bottom"),
            pytest.param(1, "Workaround available", id="label_alone"),
            pytest.param(2, "Fully blocked", id="top"),
        ],
    )
    def test_a_rating_takes_the_label_of_the_declared_level_its_answer_names(self, level: int, expected_label: str) -> None:
        """No backend reports a label: the kernel looks it up on the scale the step declared."""
        content, _ = make_verdict_content(question=self._LABELLED_SCALE, answer=RatingAnswer(level=level), threshold=None, is_dry=False)

        assert content == RatingContent(level=level, label=expected_label)
