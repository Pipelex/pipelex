"""What the question and answer models refuse.

The one rule that is not a type is ``YesNoAnswer``'s: an answer carrying neither a probability nor a
boolean is not an answer at all. Everything else here pins the optionality that lets a backend which
measured nothing stay honest.
"""

import pytest
from pydantic import TypeAdapter, ValidationError

from pipelex.cogt.content_generation.assignment_models import JudgmentAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.judgment.judgment_models import (
    ChoiceAnswer,
    ChoiceQuestion,
    JudgmentAnswer,
    JudgmentKind,
    RatingAnswer,
    RatingQuestion,
    YesNoAnswer,
    YesNoQuestion,
)
from pipelex.cogt.judgment.judgment_setting import JudgmentSetting
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode


class TestJudgmentModels:
    def test_a_yes_no_answer_needs_at_least_one_verdict(self) -> None:
        with pytest.raises(ValidationError):
            YesNoAnswer()

    @pytest.mark.parametrize(
        "answer",
        [
            YesNoAnswer(probability=0.9),
            YesNoAnswer(yes_no=True),
            YesNoAnswer(probability=0.9, yes_no=True),
        ],
        ids=["probability_only", "boolean_only", "both"],
    )
    def test_a_yes_no_answer_accepts_either_form(self, answer: YesNoAnswer) -> None:
        assert answer.kind == JudgmentKind.YES_NO

    def test_a_probability_outside_zero_to_one_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            YesNoAnswer(probability=1.5)

    def test_a_choice_question_needs_an_option(self) -> None:
        with pytest.raises(ValidationError):
            ChoiceQuestion(instructions="Which one?", options={})

    def test_a_rating_question_needs_a_level(self) -> None:
        with pytest.raises(ValidationError):
            RatingQuestion(instructions="How much?", levels=[])

    def test_an_option_may_be_declared_without_a_description(self) -> None:
        question = ChoiceQuestion(instructions="Which one?", options={"fire": None, "flood": "water damage"})
        assert question.options["fire"] is None

    def test_a_choice_answer_may_carry_only_its_verdict(self) -> None:
        answer = ChoiceAnswer(choice="fire")
        assert answer.confidence is None
        assert answer.probabilities is None

    def test_a_rating_answer_keys_its_distribution_by_level_index(self) -> None:
        answer = RatingAnswer(level=2, probabilities={0: 0.02, 1: 0.14, 2: 0.84})
        assert answer.probabilities is not None
        assert sorted(answer.probabilities) == [0, 1, 2]

    def test_a_rating_answer_coerces_the_wire_string_keys_it_is_handed(self) -> None:
        """The vendor's wire form keys a distribution by strings; the model holds integers."""
        answer = RatingAnswer.model_validate({"level": 2, "probabilities": {"0": 0.02, "2": 0.98}})
        assert answer.probabilities == {0: 0.02, 2: 0.98}

    def test_every_question_carries_its_kind(self) -> None:
        assert YesNoQuestion(instructions="?").kind == JudgmentKind.YES_NO
        assert ChoiceQuestion(instructions="?", options={"a": None}).kind == JudgmentKind.CHOICE
        assert RatingQuestion(instructions="?", levels=["low"]).kind == JudgmentKind.RATING

    def test_an_assignment_survives_the_round_trip_a_distributed_boundary_makes_it_take(self) -> None:
        """Questions and answers are the whole wire payload, so the discriminator must work both ways.

        Nothing else guards this: under a distributed orchestrator the assignment is dumped on the
        submitter and validated on a worker, and a discriminated union that dumps but does not
        re-validate would fail there and nowhere else.
        """
        assignment = JudgmentAssignment(
            job_metadata=JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", user_id="u", pipeline_run_id="run_judgment_wire")),
            cogt_run_params=CogtRunParams(run_mode=PipeRunMode.LIVE),
            state={"message": "the roof is on fire", "read_count": 3, "starred": True, "labels": ["home", "urgent"]},
            questions={
                "is_urgent": YesNoQuestion(instructions="Does this need an answer today?"),
                "topic": ChoiceQuestion(instructions="What is this about?", options={"fire": None, "flood": "water damage"}),
                "severity": RatingQuestion(instructions="How severe?", levels=["mild", "bad", "critical"]),
            },
            judgment_setting=JudgmentSetting(model="some-judgment-handle"),
        )

        restored = JudgmentAssignment.model_validate(assignment.model_dump(mode="json"))

        assert restored.state == assignment.state
        assert isinstance(restored.questions["is_urgent"], YesNoQuestion)
        assert isinstance(restored.questions["topic"], ChoiceQuestion)
        assert isinstance(restored.questions["severity"], RatingQuestion)
        assert restored.judgment_handle == "some-judgment-handle"

    def test_answers_survive_the_same_round_trip(self) -> None:
        answers: dict[str, JudgmentAnswer] = {
            "is_urgent": YesNoAnswer(probability=0.93),
            "topic": ChoiceAnswer(choice="fire", confidence=0.88, probabilities={"fire": 0.88, "flood": 0.12}),
            "severity": RatingAnswer(level=2, position=1.82, confidence=0.7, probabilities={0: 0.02, 1: 0.14, 2: 0.84}),
        }
        adapter: TypeAdapter[dict[str, JudgmentAnswer]] = TypeAdapter(dict[str, JudgmentAnswer])

        restored = adapter.validate_python(adapter.dump_python(answers, mode="json"))

        assert isinstance(restored["is_urgent"], YesNoAnswer)
        assert isinstance(restored["topic"], ChoiceAnswer)
        severity = restored["severity"]
        assert isinstance(severity, RatingAnswer)
        assert severity.probabilities == {0: 0.02, 1: 0.14, 2: 0.84}
