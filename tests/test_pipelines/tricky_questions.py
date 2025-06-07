from pydantic import Field

from pipelex.core.stuff_content import StructuredContent


class QuestionAnalysis(StructuredContent):
    explanation: str
    trickiness_rating: int = Field(..., ge=1, le=100)
    deceptiveness_rating: int = Field(..., ge=1, le=100)


class ThoughtfulAnswer(StructuredContent):
    the_trap: str
    the_counter: str
    the_lesson: str
    the_answer: str
