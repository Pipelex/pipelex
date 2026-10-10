from typing import ClassVar

from pydantic import Field, create_model

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
    """A triage whose rating, left unrequired, carries a default verdict, as a structure field with a `default_value` is generated.

    The field never holds nothing, so a refusal can neither empty it nor fill in its default, a verdict nobody gave.
    """

    urgent: YesNoContent = Field(description="Whether the message is urgent")
    team: ChoiceContent = Field(description="The team that handles it")
    severity: RatingContent = Field(default=RatingContent(level=0, label="Minor"), description="How severe the reported issue is")


class NullableRequiredTriage(StructuredContent):
    """A triage whose rating is required yet admits nothing, so a refusal stores nothing there."""

    urgent: YesNoContent = Field(description="Whether the message is urgent")
    team: ChoiceContent = Field(description="The team that handles it")
    severity: RatingContent | None = Field(description="How severe the reported issue is")


class NullableDefaultedTriage(StructuredContent):
    """A triage whose rating carries a default yet admits nothing, so a refusal stores nothing there rather than the default."""

    urgent: YesNoContent = Field(description="Whether the message is urgent")
    team: ChoiceContent = Field(description="The team that handles it")
    severity: RatingContent | None = Field(default=RatingContent(level=0, label="Minor"), description="How severe the reported issue is")


# A hand-written class may give a field `None` for default while typing it without `None`: the field may hold
# nothing, by its default, though `None` given outright is refused. Built dynamically, since a type checker
# rightly refuses that default written in a class body.
LooseDefaultTriage: type[StructuredContent] = create_model(
    "LooseDefaultTriage",
    __base__=StructuredContent,
    urgent=(YesNoContent, Field(description="Whether the message is urgent")),
    team=(ChoiceContent, Field(description="The team that handles it")),
    severity=(RatingContent, Field(default=None, description="How severe the reported issue is")),
)


class AliasedRequiredTriage(StructuredContent):
    """A triage whose required yes/no field goes by an alias: its answered verdict must land in it all the same."""

    urgent: YesNoContent = Field(alias="isUrgent", description="Whether the message is urgent")
    team: ChoiceContent = Field(description="The team that handles it")
    severity: RatingContent | None = Field(default=None, description="How severe the reported issue is")


class AliasedOptionalTriage(StructuredContent):
    """A triage whose optional choice field goes by an alias: its answered verdict must not be dropped for nothing."""

    urgent: YesNoContent = Field(description="Whether the message is urgent")
    team: ChoiceContent | None = Field(default=None, alias="handlingTeam", description="The team that handles it")
    severity: RatingContent | None = Field(default=None, description="How severe the reported issue is")


class AliasedDefaultedTriage(StructuredContent):
    """A triage whose defaulted rating field goes by an alias: its answered verdict must not be swapped for the default."""

    urgent: YesNoContent = Field(description="Whether the message is urgent")
    team: ChoiceContent = Field(description="The team that handles it")
    severity: RatingContent = Field(default=RatingContent(level=0, label="Minor"), alias="howSevere", description="How severe the reported issue is")


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
