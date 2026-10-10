"""The evidence a judgment is asked over, the questions it asks, and the outcomes it gets back.

This is the judgment family's worker contract, and it speaks no vendor's vocabulary. The evidence is a
prompt: the rendered text and the files it presents, ordered as its `[Image N]` and `[Document N]`
tokens number them. The questions and the answers are discriminated unions over
:class:`JudgmentKind`, whose three kinds are the language's own words — yes/no, choice, rating —
never a vendor's. A backend translates into its own vocabulary inside its worker and nowhere else.

**Every uncertainty member is optional, and that is a contract rather than an oversight.** A backend
that measures a probability reports it; a backend that cannot — a generative model emulating a
judgment, say — leaves it absent rather than inventing a number. Only the verdict itself is required,
and :class:`YesNoAnswer` requires at least one of its two forms of verdict.

**A refusal is an outcome, not an error.** A model may decline to answer a question, and the worker
returns a :class:`JudgmentRefusal` for it, which discloses nothing. What a refusal means is the
operator's policy, decided above the worker, so a worker never turns one into an exception.
"""

from enum import StrEnum
from typing import Annotated, Literal, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pipelex.cogt.document.prompt_document import PromptDocument
from pipelex.cogt.image.prompt_image import PromptImage


class JudgmentPrompt(BaseModel):
    """The evidence a judgment is asked over: a rendered prompt and the files it presents.

    The images and the documents are ordered as the prompt's registry numbered them, so the n-th image
    is the one the text's `[Image n]` token names. A backend that lays images out beside the text reads
    that correspondence; a backend that reads text alone refuses any file.
    """

    model_config = ConfigDict(extra="forbid")

    text: str
    images: list[PromptImage] = []
    documents: list[PromptDocument] = []


class JudgmentKind(StrEnum):
    YES_NO = "yes_no"
    CHOICE = "choice"
    RATING = "rating"


class YesNoCriteria(BaseModel):
    """What a yes and a no mean. Both sides or none: a lone side cannot be carried with its meaning on every backend."""

    model_config = ConfigDict(extra="forbid")

    yes: str
    no: str


class YesNoQuestion(BaseModel):
    """Does this condition hold? The answer's probability is its confidence."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal[JudgmentKind.YES_NO] = JudgmentKind.YES_NO
    instructions: str
    criteria: YesNoCriteria | None = None


class ChoiceQuestion(BaseModel):
    """Which one of these options? An option may be declared without a description."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal[JudgmentKind.CHOICE] = JudgmentKind.CHOICE
    instructions: str
    options: dict[str, str | None] = Field(min_length=1)


class RatingLevel(BaseModel):
    """One level of a rating scale: a label naming it in a few words, a description of the situation it stands for, or both."""

    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    description: str | None = None

    @model_validator(mode="after")
    def validate_has_a_label_or_a_description(self) -> Self:
        if self.label is None and self.description is None:
            msg = "A rating level carries a label, a description or both, and this one carries neither"
            raise ValueError(msg)
        return self


class RatingQuestion(BaseModel):
    """Where on this scale? The levels are ordered from low to high.

    One level is the floor here because one is what a judgment needs to be answerable at all. The
    language's own minimum is two, and it belongs to the blueprint that authors write against; a
    backend's maximum is that backend's, and belongs to its worker. The labels are all or none, and
    distinct, because a label is what a rating verdict reports: two equal labels would make it ambiguous.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal[JudgmentKind.RATING] = JudgmentKind.RATING
    instructions: str
    levels: list[RatingLevel] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_labels_are_all_or_none_and_distinct(self) -> Self:
        labels = [level.label for level in self.levels if level.label is not None]
        if labels and len(labels) != len(self.levels):
            msg = "On a rating scale every level carries a label or none does, and this one mixes the two"
            raise ValueError(msg)
        duplicated_labels = sorted({label for label in labels if labels.count(label) > 1})
        if duplicated_labels:
            msg = f"The labels of a rating scale are distinct, and this one repeats {', '.join(repr(label) for label in duplicated_labels)}"
            raise ValueError(msg)
        return self


JudgmentQuestion: TypeAlias = Annotated[
    YesNoQuestion | ChoiceQuestion | RatingQuestion,
    Field(discriminator="kind"),
]


class YesNoAnswer(BaseModel):
    """A yes/no verdict, as a probability, as a boolean, or as both.

    The model validator is the contract: an answer carrying neither is not an answer. A backend that
    measured a probability leaves ``yes_no`` to whoever holds the threshold; a backend that could
    only decide reports ``yes_no`` alone, and a threshold applied to it has nothing to work on —
    which the caller reports rather than silently ignoring.
    """

    kind: Literal[JudgmentKind.YES_NO] = JudgmentKind.YES_NO
    probability: float | None = Field(default=None, ge=0, le=1)
    yes_no: bool | None = None

    @model_validator(mode="after")
    def validate_has_a_verdict(self) -> Self:
        if self.probability is None and self.yes_no is None:
            msg = "A YesNoAnswer must carry a probability, a yes_no, or both"
            raise ValueError(msg)
        return self


class ChoiceAnswer(BaseModel):
    """The option chosen, with the distribution it was chosen from when the backend measured one."""

    kind: Literal[JudgmentKind.CHOICE] = JudgmentKind.CHOICE
    choice: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    probabilities: dict[str, float] | None = None


class RatingAnswer(BaseModel):
    """The level reached, as a zero-based index into the question's levels.

    ``position`` is the probability-weighted position over those indices, which is what a backend
    that measured a distribution actually knows; ``level`` is the level a verdict has to name, and
    deriving it from the distribution is the worker's translation work, since only the worker knows
    what its backend measured.
    """

    kind: Literal[JudgmentKind.RATING] = JudgmentKind.RATING
    level: int = Field(ge=0)
    position: float | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    probabilities: dict[int, float] | None = None


JudgmentAnswer: TypeAlias = Annotated[
    YesNoAnswer | ChoiceAnswer | RatingAnswer,
    Field(discriminator="kind"),
]


class JudgmentRefusal(BaseModel):
    """The model declined to answer a question. It carries no score, because the one backend that refuses discloses none."""

    # A discriminator of its own beside the three kinds an answer carries: a refusal is no kind of answer.
    kind: Literal["refusal"] = "refusal"


# What a worker returns for each question: an answer of the question's kind, or a refusal.
JudgmentOutcome: TypeAlias = Annotated[
    YesNoAnswer | ChoiceAnswer | RatingAnswer | JudgmentRefusal,
    Field(discriminator="kind"),
]
