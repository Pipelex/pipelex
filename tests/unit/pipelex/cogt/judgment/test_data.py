from typing import ClassVar

from pipelex.cogt.judgment.judgment_models import (
    ChoiceAnswer,
    ChoiceQuestion,
    JudgmentAnswer,
    JudgmentQuestion,
    RatingAnswer,
    RatingQuestion,
    YesNoAnswer,
    YesNoQuestion,
)


class JudgmentTestCases:
    THREE_QUESTIONS: ClassVar[dict[str, JudgmentQuestion]] = {
        "is_urgent": YesNoQuestion(instructions="Does this message need an answer today?"),
        "topic": ChoiceQuestion(instructions="What is this message about?", options={"fire": None, "flood": "water damage"}),
        "severity": RatingQuestion(instructions="How severe is the situation?", levels=["mild", "bad", "critical"]),
    }

    THREE_ANSWERS: ClassVar[dict[str, JudgmentAnswer]] = {
        "is_urgent": YesNoAnswer(probability=0.93),
        "topic": ChoiceAnswer(choice="fire", confidence=0.88, probabilities={"fire": 0.88, "flood": 0.12}),
        "severity": RatingAnswer(level=2, position=1.82, confidence=0.7, probabilities={0: 0.02, 1: 0.14, 2: 0.84}),
    }
