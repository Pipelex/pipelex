import pytest
from typesafe_sdk import Choice as TypesafeChoice
from typesafe_sdk import Noul as TypesafeNoul
from typesafe_sdk import Score as TypesafeScore
from typesafe_sdk import SystemOneResponse

from pipelex.cogt.judgment.judgment_models import (
    ChoiceAnswer,
    ChoiceQuestion,
    JudgmentQuestion,
    RatingAnswer,
    RatingQuestion,
    YesNoAnswer,
    YesNoQuestion,
)
from pipelex.providers.typesafe.typesafe_exceptions import TypesafeJudgmentResponseError, TypesafeQuestionUnsupportedError
from pipelex.providers.typesafe.typesafe_translation import (
    TYPESAFE_MAX_RATING_LEVELS,
    from_typesafe_response,
    to_typesafe_question,
)
from tests.unit.pipelex.providers.typesafe.test_data import TestData, load_recorded, load_recorded_response

SEVERITY_LEVELS = [
    "Cosmetic; no impact on functionality",
    "A feature is degraded, but a workaround exists",
    "Blocking issue; no workaround exists",
]


class TestTypesafeTranslation:
    def test_yes_no_sends_only_the_criteria_it_declares(self) -> None:
        """Both sides go out under the vendor's own keys, one side alone goes out alone, and neither sends no map at all."""
        both = to_typesafe_question(
            question_key="q", question=YesNoQuestion(instructions="Is it urgent?", yes_criterion="Needs attention now", no_criterion="Can wait")
        )
        yes_only = to_typesafe_question(question_key="q", question=YesNoQuestion(instructions="Is it urgent?", yes_criterion="Needs attention now"))
        neither = to_typesafe_question(question_key="q", question=YesNoQuestion(instructions="Is it urgent?"))

        assert isinstance(both, TypesafeNoul)
        assert both.model_dump()["criteria"] == {"true": "Needs attention now", "false": "Can wait"}
        assert isinstance(yes_only, TypesafeNoul)
        assert yes_only.model_dump()["criteria"] == {"true": "Needs attention now"}
        assert isinstance(neither, TypesafeNoul)
        assert "criteria" not in neither.model_dump()
        assert neither.model_dump()["instructions"] == "Is it urgent?"

    def test_choice_keeps_an_undescribed_option_as_null(self) -> None:
        question = ChoiceQuestion(instructions="What is the tone?", options={"calm": None, "angry": "Raised voice, blame"})
        rendered = to_typesafe_question(question_key="tone", question=question)

        assert isinstance(rendered, TypesafeChoice)
        assert rendered.model_dump()["criteria"] == {"calm": None, "angry": "Raised voice, blame"}

    def test_rating_goes_out_as_an_ordered_score(self) -> None:
        rendered = to_typesafe_question(question_key="severity", question=RatingQuestion(instructions="How severe?", levels=SEVERITY_LEVELS))

        assert isinstance(rendered, TypesafeScore)
        assert rendered.model_dump()["criteria"] == SEVERITY_LEVELS

    @pytest.mark.parametrize(
        ("nb_levels", "is_accepted"),
        [
            pytest.param(TYPESAFE_MAX_RATING_LEVELS, True, id="at_the_cap"),
            pytest.param(TYPESAFE_MAX_RATING_LEVELS + 1, False, id="one_past_the_cap"),
        ],
    )
    def test_the_vendor_rating_cap_is_enforced_at_its_boundary(self, nb_levels: int, is_accepted: bool) -> None:
        """Ten levels go out and eleven are refused before any request is built, as the live API refuses them."""
        question = RatingQuestion(instructions="How severe?", levels=[f"Level {index_level}" for index_level in range(nb_levels)])
        if is_accepted:
            assert isinstance(to_typesafe_question(question_key="q", question=question), TypesafeScore)
            return
        with pytest.raises(TypesafeQuestionUnsupportedError) as exc_info:
            to_typesafe_question(question_key="q", question=question)
        assert "'q'" in str(exc_info.value)
        assert f"{nb_levels}-level" in str(exc_info.value)

    def test_the_three_kinds_read_back_from_one_recorded_response(self) -> None:
        """The recorded three-question response maps back to the family's three answer kinds, value for value."""
        questions: dict[str, JudgmentQuestion] = {
            "is_urgent": YesNoQuestion(instructions=TestData.THREE_SHAPES_INSTRUCTIONS["is_urgent"]),
            "team": ChoiceQuestion(
                instructions=TestData.THREE_SHAPES_INSTRUCTIONS["team"],
                options={"payments": None, "shipping": None, "accounts": None, "other": None},
            ),
            "severity": RatingQuestion(instructions=TestData.THREE_SHAPES_INSTRUCTIONS["severity"], levels=SEVERITY_LEVELS),
        }
        answers = from_typesafe_response(questions=questions, response=load_recorded_response(TestData.THREE_SHAPES))

        assert answers["is_urgent"] == YesNoAnswer(probability=0.98)
        assert answers["team"] == ChoiceAnswer(
            choice="payments",
            confidence=1.0,
            probabilities={"accounts": 0.0, "other": 0.0, "payments": 1.0, "shipping": 0.0},
        )
        assert answers["severity"] == RatingAnswer(level=2, position=2.0, confidence=1.0, probabilities={0: 0.0, 1: 0.0, 2: 1.0})

    def test_a_yes_no_answer_leaves_the_verdict_to_the_threshold(self) -> None:
        """The backend measured a probability; the side of the threshold is the caller's decision, so ``yes_no`` stays absent."""
        answers = from_typesafe_response(
            questions={"is_urgent": YesNoQuestion(instructions="Is the message urgent?")},
            response=load_recorded_response(TestData.USAGE_ONE_QUESTION),
        )
        answer = answers["is_urgent"]
        assert isinstance(answer, YesNoAnswer)
        assert answer.yes_no is None
        assert answer.probability == 0.98

    def test_a_spread_rating_names_its_most_probable_level_not_its_position(self) -> None:
        """The recorded ten-level answer sits at position 7.86 but is most probable at level 9 — the verdict is 9."""
        answers = from_typesafe_response(
            questions={"q": RatingQuestion(instructions="How severe?", levels=[f"Severity level {index_level}" for index_level in range(10)])},
            response=load_recorded_response(TestData.SCORE_TEN_LEVELS),
        )
        answer = answers["q"]
        assert isinstance(answer, RatingAnswer)
        assert answer.level == 9
        assert answer.position == 7.86
        assert answer.confidence == 0.54
        assert answer.probabilities is not None
        assert answer.probabilities[9] == 0.43

    @pytest.mark.parametrize(
        ("wire_probabilities", "score", "expected_level"),
        [
            pytest.param('{"0": 0.2, "1": 0.5, "2": 0.3}', 1.1, 1, id="peak_in_the_middle"),
            pytest.param('{"0": 0.6, "1": 0.1, "2": 0.3}', 0.7, 0, id="peak_at_the_floor_above_the_position"),
            pytest.param('{"0": 0.4, "1": 0.4, "2": 0.2}', 0.8, 0, id="a_tie_goes_to_the_lower_level"),
        ],
    )
    def test_the_rating_verdict_is_the_most_probable_level(self, wire_probabilities: str, score: float, expected_level: int) -> None:
        """Not the top level and not the rounded position: the peak of the distribution, ties going low."""
        wire_body = (
            '{"model": "jev-1.13.0", "usage": {"input_tokens": 1, "output_tokens": 1}, "answers": {"q": '
            f'{{"type": "score", "score": {score}, "confidence": 0.5, "legend": {{"0": "a", "1": "b", "2": "c"}}, '
            f'"probabilities": {wire_probabilities}}}}}}}'
        )
        answers = from_typesafe_response(
            questions={"q": RatingQuestion(instructions="How severe?", levels=["a", "b", "c"])},
            response=SystemOneResponse.model_validate_json(wire_body),
        )
        answer = answers["q"]
        assert isinstance(answer, RatingAnswer)
        assert answer.level == expected_level
        assert answer.position == score

    def test_rating_keys_are_strings_on_the_wire_and_integers_once_read(self) -> None:
        """The replay fixture holds the wire form; the family's answer holds integer levels."""
        wire_probabilities = load_recorded(TestData.SCORE_TEN_LEVELS)["answers"]["q"]["probabilities"]
        assert all(isinstance(level, str) for level in wire_probabilities)

        answers = from_typesafe_response(
            questions={"q": RatingQuestion(instructions="How severe?", levels=[f"Severity level {index_level}" for index_level in range(10)])},
            response=load_recorded_response(TestData.SCORE_TEN_LEVELS),
        )
        answer = answers["q"]
        assert isinstance(answer, RatingAnswer)
        assert answer.probabilities is not None
        assert sorted(answer.probabilities) == list(range(10))

    def test_an_answer_of_the_wrong_kind_is_refused(self) -> None:
        """A choice answer read back for a question asked as a rating cannot be translated at all."""
        with pytest.raises(TypesafeJudgmentResponseError) as exc_info:
            from_typesafe_response(
                questions={"q": RatingQuestion(instructions="How severe?", levels=SEVERITY_LEVELS)},
                response=load_recorded_response(TestData.CHOICE_NULL_DESCRIPTIONS),
            )
        assert "'q'" in str(exc_info.value)
        assert "'choice'" in str(exc_info.value)
        assert "'rating'" in str(exc_info.value)

    def test_a_missing_answer_is_refused(self) -> None:
        with pytest.raises(TypesafeJudgmentResponseError) as exc_info:
            from_typesafe_response(
                questions={"never_answered": YesNoQuestion(instructions="Is it urgent?")},
                response=load_recorded_response(TestData.USAGE_ONE_QUESTION),
            )
        assert "'never_answered'" in str(exc_info.value)
        assert "without an answer" in str(exc_info.value)
