"""The two-way translation between the judgment family's vocabulary and TypeSafe's.

The family speaks yes/no, choice and rating; this vendor speaks *noul*, *choice* and *score*. The
mapping is one-to-one, and it lives here alone — nothing outside this module knows a vendor word.

**The vendor's bounds are enforced here, not in the blueprint.** A rating scale longer than this
API answers is legal MTHDS that this one backend refuses, exactly as the design's Part 5 says: the
language's own minimums belong to the question models, and a vendor's maximum belongs to the
vendor's worker, so a second judgment backend is free to accept what this one will not.
"""

from typing import Any, assert_never

from typesafe_sdk import (
    Choice as TypesafeChoice,
)
from typesafe_sdk import (
    ChoiceAnswer as TypesafeChoiceAnswer,
)
from typesafe_sdk import (
    Noul as TypesafeNoul,
)
from typesafe_sdk import (
    NoulAnswer as TypesafeNoulAnswer,
)
from typesafe_sdk import (
    NoulCriteria as TypesafeNoulCriteria,
)
from typesafe_sdk import (
    Question as TypesafeQuestion,
)
from typesafe_sdk import (
    Score as TypesafeScore,
)
from typesafe_sdk import (
    ScoreAnswer as TypesafeScoreAnswer,
)
from typesafe_sdk import (
    SystemOneResponse,
)

from pipelex.cogt.exceptions import InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
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
from pipelex.providers.typesafe.typesafe_exceptions import TypesafeJudgmentResponseError, TypesafeQuestionUnsupportedError

# The longest rating scale this API answers, probed at the boundary in the campaign's spike: ten
# levels are accepted and eleven are refused with a 400. The vendor's own advice explains why the
# cap is not a nuisance — at ten thin levels the model's confidence collapsed to 0.54 and spread
# across four of them, against 1.0 on a single level for a three-level scale over the same material.
TYPESAFE_MAX_RATING_LEVELS = 10


def to_typesafe_questions(*, questions: dict[str, JudgmentQuestion]) -> dict[str, TypesafeQuestion]:
    """Render every question of a job into the vendor's own question objects."""
    return {question_key: to_typesafe_question(question_key=question_key, question=question) for question_key, question in questions.items()}


def to_typesafe_question(*, question_key: str, question: JudgmentQuestion) -> TypesafeQuestion:
    """Render one question into the vendor's vocabulary, refusing what the vendor will not take."""
    match question:
        case YesNoQuestion():
            return TypesafeNoul(instructions=question.instructions, criteria=_noul_criteria(question=question))
        case ChoiceQuestion():
            return TypesafeChoice(instructions=question.instructions, criteria=dict(question.options))
        case RatingQuestion():
            nb_levels = len(question.levels)
            if nb_levels > TYPESAFE_MAX_RATING_LEVELS:
                msg = (
                    f"Judgment question '{question_key}' asks for a {nb_levels}-level rating, and this backend "
                    f"answers at most {TYPESAFE_MAX_RATING_LEVELS} levels"
                )
                raise TypesafeQuestionUnsupportedError(
                    msg,
                    error_category=InferenceErrorCategory.CONTENT,
                    user_action=UserAction(
                        kind=UserActionKind.CHANGE_INPUT,
                        detail=(
                            f"Shorten the rating scale to {TYPESAFE_MAX_RATING_LEVELS} levels or fewer — levels that "
                            "describe distinct situations read better than a long formulaic scale anyway."
                        ),
                    ),
                    provider_metadata=None,
                )
            return TypesafeScore(instructions=question.instructions, criteria=list(question.levels))
        case _:
            assert_never(question)


def _noul_criteria(*, question: YesNoQuestion) -> TypesafeNoulCriteria | None:
    """The vendor's yes/no criteria, or nothing at all when the question declared neither side.

    Both sides are individually optional and an absent map is legal as long as the instructions are
    there. A key the vendor does not know is accepted and silently ignored, so only the two names
    it does know are ever sent.
    """
    criteria: TypesafeNoulCriteria = {}
    if question.yes_criterion is not None:
        criteria["true"] = question.yes_criterion
    if question.no_criterion is not None:
        criteria["false"] = question.no_criterion
    return criteria or None


def from_typesafe_response(*, questions: dict[str, JudgmentQuestion], response: SystemOneResponse) -> dict[str, JudgmentAnswer]:
    """Read every answer back into the family's vocabulary, keyed as the questions were."""
    answers: dict[str, JudgmentAnswer] = {}
    for question_key, question in questions.items():
        typesafe_answer = response.answers.get(question_key)
        if typesafe_answer is None:
            msg = f"TypeSafe answered a judgment without an answer for question '{question_key}'"
            raise _response_error(msg=msg)
        answers[question_key] = _from_typesafe_answer(question_key=question_key, question=question, typesafe_answer=typesafe_answer)
    return answers


def _from_typesafe_answer(*, question_key: str, question: JudgmentQuestion, typesafe_answer: Any) -> JudgmentAnswer:
    """Read one answer back, refusing one that does not match the kind its question asked for."""
    match question:
        case YesNoQuestion():
            if not isinstance(typesafe_answer, TypesafeNoulAnswer):
                raise _wrong_kind_error(question_key=question_key, question=question, typesafe_answer=typesafe_answer)
            # The probability *is* the confidence for this kind, and the verdict is deliberately
            # left absent: whoever holds the threshold decides which side of it this falls on.
            return YesNoAnswer(probability=typesafe_answer.noul)
        case ChoiceQuestion():
            if not isinstance(typesafe_answer, TypesafeChoiceAnswer):
                raise _wrong_kind_error(question_key=question_key, question=question, typesafe_answer=typesafe_answer)
            return ChoiceAnswer(
                choice=typesafe_answer.choice,
                confidence=typesafe_answer.confidence,
                probabilities=dict(typesafe_answer.probabilities),
            )
        case RatingQuestion():
            if not isinstance(typesafe_answer, TypesafeScoreAnswer):
                raise _wrong_kind_error(question_key=question_key, question=question, typesafe_answer=typesafe_answer)
            probabilities = dict(typesafe_answer.probabilities)
            return RatingAnswer(
                level=_most_probable_level(probabilities=probabilities, score=typesafe_answer.score, nb_levels=len(question.levels)),
                position=typesafe_answer.score,
                confidence=typesafe_answer.confidence,
                probabilities=probabilities or None,
            )
        case _:
            assert_never(question)


def _most_probable_level(*, probabilities: dict[int, float], score: float, nb_levels: int) -> int:
    """The level a rating verdict names, derived from what the backend actually measured.

    This vendor reports a distribution and a ``score`` that is its probability-weighted position, so
    the score usually falls *between* levels and is not itself a verdict. The verdict is the most
    probable level, and deriving it is the worker's job because only the worker knows what its
    backend measured. Ties go to the lower level, so the same distribution always names the same
    verdict. With no distribution at all — which this API has never been seen to do — the weighted
    position rounded to the nearest level is the best remaining reading.
    """
    highest_level = max(nb_levels - 1, 0)
    if probabilities:
        return min(max(probabilities, key=lambda level: (probabilities[level], -level)), highest_level)
    return min(max(round(score), 0), highest_level)


def _wrong_kind_error(*, question_key: str, question: JudgmentQuestion, typesafe_answer: Any) -> TypesafeJudgmentResponseError:
    msg = (
        f"TypeSafe answered question '{question_key}' with a '{getattr(typesafe_answer, 'type', type(typesafe_answer).__name__)}' "
        f"answer, but it asked for a '{question.kind}'"
    )
    return _response_error(msg=msg)


def _response_error(*, msg: str) -> TypesafeJudgmentResponseError:
    return TypesafeJudgmentResponseError(
        msg,
        error_category=InferenceErrorCategory.UNKNOWN,
        user_action=UserAction(
            kind=UserActionKind.CHANGE_MODEL,
            detail="TypeSafe returned a malformed judgment response — try a different judgment model.",
        ),
        provider_metadata=None,
    )
