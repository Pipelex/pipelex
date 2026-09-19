"""The questions a judgment asks and the answers it gets back.

Both are discriminated unions over :class:`JudgmentKind`, and the three kinds are the language's
own words — yes/no, choice, rating — never a vendor's. A backend translates into its own vocabulary
inside its worker and nowhere else.

**Every uncertainty member is optional, and that is a contract rather than an oversight.** A backend
that measures a probability reports it; a backend that cannot — a generative model emulating a
judgment, say — leaves it absent rather than inventing a number. Only the verdict itself is required,
and :class:`YesNoAnswer` requires at least one of its two forms of verdict.
"""

from enum import StrEnum
from typing import Annotated, Any, Literal, Self, TypeAlias

from pydantic import BaseModel, Field, model_validator

# The material a judgment is passed, as a JSON object with one member per name the questions refer
# to. An object rather than free text or an array on purpose: the vendor reads named fields as
# relationships, and the spike measured an array state — which drops the names — answering
# measurably worse. `Any` is the JSON value space, and the kernel is what fills it.
JudgmentState: TypeAlias = dict[str, Any]


class JudgmentKind(StrEnum):
    YES_NO = "yes_no"
    CHOICE = "choice"
    RATING = "rating"


class YesNoQuestion(BaseModel):
    """Does this condition hold? The answer's probability is its confidence."""

    kind: Literal[JudgmentKind.YES_NO] = JudgmentKind.YES_NO
    instructions: str
    yes_criterion: str | None = None
    no_criterion: str | None = None


class ChoiceQuestion(BaseModel):
    """Which one of these options? An option may be declared without a description."""

    kind: Literal[JudgmentKind.CHOICE] = JudgmentKind.CHOICE
    instructions: str
    options: dict[str, str | None] = Field(min_length=1)


class RatingQuestion(BaseModel):
    """Where on this scale? The levels are ordered from low to high, each describing a situation.

    One level is the floor here because one is what a judgment needs to be answerable at all. The
    language's own minimum is two, and it belongs to the blueprint that authors write against; a
    backend's maximum is that backend's, and belongs to its worker.
    """

    kind: Literal[JudgmentKind.RATING] = JudgmentKind.RATING
    instructions: str
    levels: list[str] = Field(min_length=1)


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
