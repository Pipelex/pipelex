from abc import abstractmethod

from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import CogtError, JudgmentAnswerMismatchError
from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.judgment.judgment_job import JudgmentJob
from pipelex.cogt.judgment.judgment_models import ChoiceAnswer, ChoiceQuestion, JudgmentAnswer, JudgmentQuestion, RatingAnswer, RatingQuestion
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.system.job_metadata import UnitJobId


class JudgmentWorkerAbstract(InferenceWorkerAbstract):
    def __init__(
        self,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        InferenceWorkerAbstract.__init__(self, reporting_delegate=reporting_delegate)
        self.inference_model = inference_model

    @property
    @override
    def desc(self) -> str:
        return f"Judgment using {self.inference_model.desc}"

    async def judge(
        self,
        judgment_job: JudgmentJob,
    ) -> dict[str, JudgmentAnswer]:
        """Answer every question in the job over its state, keyed as the questions were."""
        log.dev(f"✨ {self.desc} ✨")
        judgment_job.validate_before_execution()
        judgment_job.job_metadata.unit_job_id = UnitJobId.JUDGMENT_ANSWER
        judgment_job.judgment_job_before_start(inference_model=self.inference_model)

        try:
            answers = await self._judge(judgment_job=judgment_job)
            _check_answers_match_questions(judgment_job=judgment_job, answers=answers)
        except CogtError as exc:
            exc.fill_model_and_provider(model_handle=self.inference_model.name, backend_name=self.inference_model.backend_name)
            raise
        finally:
            # Completion and reporting belong on *every* way out, not just the happy one. The
            # answer-shape guard above raises after the provider already answered and after usage was
            # recorded, so that call is billed — reporting only on success would make the spend vanish
            # from the run's cost report. A failure that never reached the provider recorded no tokens
            # (`judgment_job_before_start` initialises `nb_tokens_by_category` empty), so it reports as
            # the zero-cost attempt it was rather than inventing a charge.
            judgment_job.judgment_job_after_complete()
            if self.reporting_delegate:
                self.reporting_delegate.report_inference_job(inference_job=judgment_job)

        return answers

    @abstractmethod
    async def _judge(
        self,
        judgment_job: JudgmentJob,
    ) -> dict[str, JudgmentAnswer]:
        pass


def _check_answers_match_questions(*, judgment_job: JudgmentJob, answers: dict[str, JudgmentAnswer]) -> None:
    """Refuse an answer set that does not correspond, question for question, to what was asked.

    Three ways a backend can get this wrong, and all are silent without this check: answering a
    question nobody asked (or dropping one), answering the right question in the wrong shape — a
    choice where a rating was asked for — and naming a verdict the question never offered, such as
    an option it does not list or a level beyond its scale. The caller reads the answers by key, by
    kind and by the option or level they name, so any of them would surface much later, as a
    missing key, a verdict of the wrong type or a verdict routed nowhere.
    """
    asked = set(judgment_job.questions)
    answered = set(answers)
    if asked != answered:
        missing = sorted(asked - answered)
        unasked = sorted(answered - asked)
        msg = f"Judgment worker answered the wrong set of questions: missing {missing}, unasked {unasked}"
        raise JudgmentAnswerMismatchError(msg)
    for question_key, question in judgment_job.questions.items():
        answer = answers[question_key]
        if answer.kind != question.kind:
            msg = f"Judgment worker answered question '{question_key}' with a '{answer.kind}' answer, but it asked for '{question.kind}'"
            raise JudgmentAnswerMismatchError(msg)
        _check_answer_is_offered(question_key=question_key, question=question, answer=answer)


def _check_answer_is_offered(*, question_key: str, question: JudgmentQuestion, answer: JudgmentAnswer) -> None:
    """Refuse a verdict the question did not offer, in the answer itself or in its distribution.

    The answer models cannot check this on their own, since they never see their question: this is
    the one place that holds both.
    """
    match question, answer:
        case ChoiceQuestion(), ChoiceAnswer():
            named_options = {answer.choice, *(answer.probabilities or {})}
            unoffered = sorted(named_options - set(question.options))
            if unoffered:
                msg = f"Judgment worker answered question '{question_key}' with options it does not offer: {unoffered}"
                raise JudgmentAnswerMismatchError(msg)
        case RatingQuestion(), RatingAnswer():
            nb_levels = len(question.levels)
            named_levels = {answer.level, *(answer.probabilities or {})}
            out_of_scale = sorted(level for level in named_levels if not 0 <= level < nb_levels)
            if out_of_scale:
                msg = (
                    f"Judgment worker answered question '{question_key}' with levels {out_of_scale}, "
                    f"outside its scale of {nb_levels} levels (0 to {nb_levels - 1})"
                )
                raise JudgmentAnswerMismatchError(msg)
        case _:
            # A yes/no answer names no option and no level, and its probability is bounded by its model.
            pass
