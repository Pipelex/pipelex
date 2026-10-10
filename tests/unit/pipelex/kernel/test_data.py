from typing import ClassVar

from pydantic import Field

from pipelex.cogt.judgment.judgment_models import (
    ChoiceAnswer,
    ChoiceQuestion,
    JudgmentOutcome,
    RatingAnswer,
    RatingLevel,
    RatingQuestion,
    YesNoAnswer,
    YesNoQuestion,
)
from pipelex.core.stuffs.choice_content import ChoiceContent
from pipelex.core.stuffs.rating_content import RatingContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.yes_no_content import YesNoContent
from pipelex.kernel.judgment_ops import AskedQuestion


class JudgedTriage(StructuredContent):
    """The structure a triage judgment fills: two required verdicts and an optional one."""

    urgent: YesNoContent = Field(description="Whether the message is urgent")
    team: ChoiceContent = Field(description="The team that handles it")
    severity: RatingContent | None = Field(default=None, description="How severe the reported issue is")


class DefaultedTriage(StructuredContent):
    """A triage whose rating, left unrequired, carries a default verdict: a refusal must never fill it in."""

    urgent: YesNoContent = Field(description="Whether the message is urgent")
    team: ChoiceContent = Field(description="The team that handles it")
    severity: RatingContent | None = Field(default=RatingContent(level=0, label="Minor"), description="How severe the reported issue is")


def _blocking_rating() -> RatingContent:
    return RatingContent(level=1, label="Major")


class FactoryDefaultedTriage(StructuredContent):
    """A triage whose rating, left unrequired, gets a default verdict from a factory: a refusal must never fill it in."""

    urgent: YesNoContent = Field(description="Whether the message is urgent")
    team: ChoiceContent = Field(description="The team that handles it")
    severity: RatingContent = Field(default_factory=_blocking_rating, description="How severe the reported issue is")


class MultiJudgmentTestCases:
    """A triage asking three questions of a message, one of each kind, and the answers a worker gives them."""

    MESSAGE: ClassVar[str] = "The invoice page crashes for every customer."

    QUESTIONS: ClassVar[dict[str, AskedQuestion]] = {
        "urgent": AskedQuestion(question=YesNoQuestion(instructions="Is this urgent, given that it says '{{ message }}'?"), threshold=0.8),
        "team": AskedQuestion(question=ChoiceQuestion(instructions="Which team handles it?", options={"billing": None, "technical": "Errors"})),
        "severity": AskedQuestion(
            question=RatingQuestion(instructions="How severe is it?", levels=[RatingLevel(label="Minor"), RatingLevel(label="Major")])
        ),
    }

    ANSWERS: ClassVar[dict[str, JudgmentOutcome]] = {
        "urgent": YesNoAnswer(probability=0.9),
        "team": ChoiceAnswer(choice="technical", confidence=0.7),
        "severity": RatingAnswer(level=1, confidence=0.6),
    }
