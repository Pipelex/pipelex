"""What the question and answer models refuse.

The rules that are not types: ``YesNoAnswer`` carries a verdict in one form or the other, a yes/no
question's criteria declare both sides or none, a level carries a label, a description or both, and
a scale's labels are all or none and distinct. Everything else here pins the optionality that lets a
backend which measured nothing stay honest, and the wire round trip a distributed run makes.
"""

import pytest
from pydantic import TypeAdapter, ValidationError

from pipelex.cogt.content_generation.assignment_models import JudgmentAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.document.prompt_document import PromptDocumentUri
from pipelex.cogt.image.prompt_image import PromptImageUri
from pipelex.cogt.judgment.judgment_models import (
    ChoiceAnswer,
    ChoiceQuestion,
    JudgmentKind,
    JudgmentOutcome,
    JudgmentPrompt,
    JudgmentRefusal,
    RatingAnswer,
    RatingLevel,
    RatingQuestion,
    YesNoAnswer,
    YesNoCriteria,
    YesNoQuestion,
)
from pipelex.cogt.judgment.judgment_setting import JudgmentSetting
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.unit.pipelex.cogt.judgment.test_data import JudgmentTestCases


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

    @pytest.mark.parametrize(
        "criteria",
        [
            pytest.param({"yes": "The customer needs an answer today"}, id="yes_alone"),
            pytest.param({"no": "The message can wait"}, id="no_alone"),
        ],
    )
    def test_a_lone_criterion_cannot_be_constructed(self, criteria: dict[str, str]) -> None:
        """Criteria describe both answers, so no worker ever meets a lone side."""
        with pytest.raises(ValidationError):
            YesNoQuestion.model_validate({"instructions": "Is it urgent?", "criteria": criteria})

    def test_a_yes_no_question_carries_both_criteria_or_none(self) -> None:
        bare = YesNoQuestion(instructions="Is it urgent?")
        with_criteria = YesNoQuestion(instructions="Is it urgent?", criteria=YesNoCriteria(yes="today", no="can wait"))

        assert bare.criteria is None
        assert with_criteria.criteria == YesNoCriteria(yes="today", no="can wait")

    def test_a_choice_question_needs_an_option(self) -> None:
        with pytest.raises(ValidationError):
            ChoiceQuestion(instructions="Which one?", options={})

    def test_a_rating_question_needs_a_level(self) -> None:
        with pytest.raises(ValidationError):
            RatingQuestion(instructions="How much?", levels=[])

    def test_a_level_carries_a_label_a_description_or_both(self) -> None:
        with pytest.raises(ValidationError, match="label, a description or both"):
            RatingLevel()

    @pytest.mark.parametrize(
        ("levels", "message_fragment"),
        [
            pytest.param([RatingLevel(label="Low"), RatingLevel(description="High")], "every level carries a label or none does", id="mixed"),
            pytest.param([RatingLevel(label="Low"), RatingLevel(label="Low")], "'Low'", id="duplicated_label"),
        ],
    )
    def test_a_scales_labels_are_all_or_none_and_distinct(self, levels: list[RatingLevel], message_fragment: str) -> None:
        """The label is what a rating verdict reports, so two equal labels would make it ambiguous."""
        with pytest.raises(ValidationError, match=message_fragment):
            RatingQuestion(instructions="How much?", levels=levels)

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
        """The wire keys a distribution by strings; the model holds integers."""
        answer = RatingAnswer.model_validate({"level": 2, "probabilities": {"0": 0.02, "2": 0.98}})
        assert answer.probabilities == {0: 0.02, 2: 0.98}

    def test_every_question_carries_its_kind(self) -> None:
        assert YesNoQuestion(instructions="?").kind == JudgmentKind.YES_NO
        assert ChoiceQuestion(instructions="?", options={"a": None}).kind == JudgmentKind.CHOICE
        assert RatingQuestion(instructions="?", levels=[RatingLevel(description="low")]).kind == JudgmentKind.RATING

    def test_a_prompt_defaults_to_no_files(self) -> None:
        """The wire leaves `images` out of a text-only prompt, and the prompt reads it as no files."""
        prompt = JudgmentPrompt.model_validate({"text": "A message from a customer"})
        assert prompt.images == []
        assert prompt.documents == []

    def test_an_assignment_survives_the_round_trip_a_distributed_boundary_makes_it_take(self) -> None:
        """The prompt, its files and the questions are the whole wire payload, so the discriminators must work both ways.

        Nothing else guards this: under a distributed orchestrator the assignment is dumped on the
        submitter and validated on a worker, and a discriminated union that dumps but does not
        re-validate would fail there and nowhere else.
        """
        assignment = JudgmentAssignment(
            job_metadata=JobMetadata(
                run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="u", pipeline_run_id="run_judgment_wire")
            ),
            cogt_run_params=CogtRunParams(run_mode=PipeRunMode.LIVE),
            prompt=JudgmentPrompt(
                text="Inspect the product in this photo: [Image 1]\nIts claim form: [Document 1]",
                images=[PromptImageUri(uri="pipelex-storage://s/photo.png", mime_type="image/png")],
                documents=[PromptDocumentUri(uri="pipelex-storage://s/claim.pdf", mime_type="application/pdf")],
            ),
            questions=JudgmentTestCases.THREE_QUESTIONS,
            judgment_setting=JudgmentSetting(model="some-judgment-handle"),
        )

        restored = JudgmentAssignment.model_validate(assignment.model_dump(mode="json"))

        assert restored == assignment
        assert isinstance(restored.questions["is_urgent"], YesNoQuestion)
        assert isinstance(restored.questions["topic"], ChoiceQuestion)
        assert isinstance(restored.questions["severity"], RatingQuestion)
        assert restored.judgment_handle == "some-judgment-handle"

    def test_outcomes_survive_the_same_round_trip_a_refusal_included(self) -> None:
        outcomes: dict[str, JudgmentOutcome] = {**JudgmentTestCases.THREE_ANSWERS, "refused": JudgmentRefusal()}
        adapter: TypeAdapter[dict[str, JudgmentOutcome]] = TypeAdapter(dict[str, JudgmentOutcome])

        restored = adapter.validate_python(adapter.dump_python(outcomes, mode="json"))

        assert restored == outcomes
        assert isinstance(restored["refused"], JudgmentRefusal)
        severity = restored["severity"]
        assert isinstance(severity, RatingAnswer)
        assert severity.probabilities == {0: 0.02, 1: 0.14, 2: 0.84}

    def test_a_refusal_carries_nothing_but_its_kind(self) -> None:
        assert JudgmentRefusal().model_dump(mode="json") == {"kind": "refusal"}
