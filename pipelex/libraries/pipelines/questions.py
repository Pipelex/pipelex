from datetime import datetime
from typing import Generic, List, Literal, Optional, TypeVar, Union

from pydantic import Field, model_validator
from typing_extensions import Self, override

from pipelex.core.stuff_content import StructuredContent
from pipelex.types import StrEnum


class QuestionCategoryEnum(StrEnum):
    NOT_A_QUESTION = "not_a_question"
    TRICKY = "tricky"
    STRAIGHTFORWARD = "straightforward"
    OBVIOUS = "obvious"


class QuestionCategory(StructuredContent):
    category: QuestionCategoryEnum
    explanation: str


class QuestionAnalysis(StructuredContent):
    explanation: str
    trickiness_rating: int = Field(..., ge=1, le=100)
    deceptiveness_rating: int = Field(..., ge=1, le=100)


class QuestionWithExcerpt(StructuredContent):
    question: str
    excerpt: str


class RawQuestionWithExcerpt(StructuredContent):
    raw_question: str
    raw_excerpt: str


class AllowedTypes(StrEnum):
    STRING = "str"
    INTEGER = "int"
    FLOAT = "float"
    BOOLEAN = "bool"
    LIST = "list"
    DICT = "dict"
    TUPLE = "tuple"
    SET = "set"
    DATE = "date"


class TargetType(StructuredContent):
    target_type: AllowedTypes
    dimension: Optional[str] = None


class ThoughtfulAnswer(StructuredContent):
    the_trap: str
    the_counter: str
    the_lesson: str
    the_answer: str


T = TypeVar("T")


class BaseAnswer(StrEnum):
    NOT_APPLICABLE = "Not applicable"
    INDETERMINATE = "Indeterminate"


# TODO: we should make this system easy to apply using a simple parameter on a chosen structure
class SourcedAnswer(StructuredContent, Generic[T]):
    """
    This model represents an answer to a question given a excerpt of a text.
    Add a short comment explaining how you determined the answer.

    Make sure you return citations (taken from the text) in an array if you can answer the question.
    Do not force a citation if you cannot answer the question.
    """

    answer: Union[T, Literal[BaseAnswer.NOT_APPLICABLE, BaseAnswer.INDETERMINATE]] = Field(description="The answer to the question")
    short_comment: str = Field(..., description="A short comment explaining how you determined the answer.")
    citations: Optional[List[str]] = Field(default=None, description="The array of citations that contains the answer.")

    @property
    def indeterminate(self) -> bool:
        return self.answer == BaseAnswer.INDETERMINATE

    @property
    def not_applicable(self) -> bool:
        return self.answer == BaseAnswer.NOT_APPLICABLE

    @model_validator(mode="after")
    def validate_answer(self) -> Self:
        if not self.answer:
            raise ValueError("Answer must be provided")

        if not (self.indeterminate or self.answer) and not self.citations:
            raise ValueError("Citations must be provided when answer is not 'Indeterminate'")

        return self

    @override
    def render_spreadsheet(self) -> str:
        return str(self.answer)


C = TypeVar("C")


class MultipleChoiceAnswer(SourcedAnswer[C], Generic[C]):
    """A specialized answer type for multiple choice questions."""

    choices: List[str] = Field(default_factory=list, description="The list of choices for the multiple choice question.")


class YesNoChoices(StrEnum):
    YES = "Yes"
    NO = "No"


class YesNo(MultipleChoiceAnswer[Literal[YesNoChoices.YES, YesNoChoices.NO]]):
    """
    Answer by yes or no or not applicable or indeterminate.
    Make sure to extract the citation of the text that contains the arguments for providing the answer.
    If the answer is not existing, do not force a citation.
    """

    choices: List[str] = Field(default=[choice.value for choice in YesNoChoices], description="Yes/No choices")


class Date(SourcedAnswer[datetime]):
    """
    This model represents a date mentioned in a text.
    """


class BulletedList(SourcedAnswer[List[str]]):
    """
    Organize the information into a list of items, each item being a string, with a hyphen at the beginning of each item.
    """


class FreeText(SourcedAnswer[str]):
    """
    This model represents a free text.
    The answer can be a free text without format constraints.
    """


class TimeUnit(StrEnum):
    YEARS = "year(s)"
    MONTHS = "month(s)"
    DAYS = "day(s)"


class Duration(SourcedAnswer[int]):
    """
    This model represents a duration. A duration is made of a value and a unit.
    For instance, the duration "5 years" would be represented as "5 year(s)".
    Add the unit to the asnwer: (years, months, days, hours, minutes, seconds)
    """

    unit: Optional[str] = Field(default=None, description="The unit of the duration: year(s), month(s), day(s), hour(s), minute(s), second(s)")


class Numerical(SourcedAnswer[int]):
    """
    This model represents a number of items. Items can be of any kind.
    """


class TimeRange(SourcedAnswer[str]):
    """
    This model represents a time range. A time range is made of a start event and an end event.
    For instance the time range "from 2025 to 2030" would be represented as "2025 to 2030".
    """


class Location(SourcedAnswer[str]):
    """
    This model represents the location geographically of something
    """
