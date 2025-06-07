from datetime import datetime
from typing import Generic, List, Literal, Optional, TypeVar, Union

from pydantic import Field, model_validator
from typing_extensions import Self, override

from pipelex.core.stuff_content import StructuredContent
from pipelex.types import StrEnum


class QuestionAnalysis(StructuredContent):
    explanation: str
    trickiness_rating: int = Field(..., ge=1, le=100)
    deceptiveness_rating: int = Field(..., ge=1, le=100)


class ThoughtfulAnswer(StructuredContent):
    the_trap: str
    the_counter: str
    the_lesson: str
    the_answer: str
