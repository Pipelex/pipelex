from abc import abstractmethod

from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import CogtError, JudgmentAnswerMismatchError, JudgmentCapabilityError
from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
from pipelex.cogt.inference.prompt_file_checks import check_prompt_documents_are_read, check_prompt_images_are_images
from pipelex.cogt.judgment.judgment_job import JudgmentJob
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
            self._check_can_read_files(judgment_job=judgment_job)
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

    def _check_can_read_files(self, *, judgment_job: JudgmentJob) -> None:
        """Refuse a job carrying files the model does not read, before the backend is called.

        The model's spec states what it reads in `inputs`, in the LLM vocabulary: `images` for vision,
        a document format key such as `pdf` for documents. A model that reads text alone refuses any
        file here, which is how a text-only backend is protected without a line of its own.
        """
        prompt_images = [image for images in judgment_job.images.values() for image in images]
        if prompt_images:
            if not self.inference_model.is_vision_supported:
                msg = f"Judgment model '{self.inference_model.tag}' does not read images, and the judgment was given {len(prompt_images)}."
                raise JudgmentCapabilityError(msg)
            max_prompt_images = self.inference_model.max_prompt_images
            if max_prompt_images is not None and len(prompt_images) > max_prompt_images:
                msg = (
                    f"Judgment model '{self.inference_model.tag}' reads at most {max_prompt_images} images, "
                    f"and the judgment was given {len(prompt_images)}."
                )
                raise JudgmentCapabilityError(msg)
            check_prompt_images_are_images(model_name=self.inference_model.name, prompt_images=prompt_images)

        prompt_documents = [document for documents in judgment_job.documents.values() for document in documents]
        if prompt_documents:
            if not self.inference_model.is_document_supported:
                msg = f"Judgment model '{self.inference_model.tag}' does not read documents, and the judgment was given {len(prompt_documents)}."
                raise JudgmentCapabilityError(msg)
            check_prompt_documents_are_read(
                model_name=self.inference_model.name,
                supported_document_types=self.inference_model.supported_document_types,
                prompt_documents=prompt_documents,
            )

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
        _check_answer_fits_question(question_key=question_key, question=question, answer=answers[question_key])


def _check_answer_fits_question(*, question_key: str, question: JudgmentQuestion, answer: JudgmentAnswer) -> None:
    """Refuse an answer of another kind than its question, or naming a verdict the question did not offer.

    The answer models cannot check this on their own, since they never see their question: this is
    the one place that holds both. The match is over the question alone, with no wildcard, so a new
    kind of question fails the type check here until its answer is checked too.
    """
    match question:
        case YesNoQuestion():
            if not isinstance(answer, YesNoAnswer):
                raise JudgmentAnswerMismatchError(_wrong_kind_message(question_key=question_key, question=question, answer=answer))
            # A yes/no answer names no option and no level, and its probability is bounded by its model.
        case ChoiceQuestion():
            if not isinstance(answer, ChoiceAnswer):
                raise JudgmentAnswerMismatchError(_wrong_kind_message(question_key=question_key, question=question, answer=answer))
            named_options = {answer.choice, *(answer.probabilities or {})}
            unoffered = sorted(named_options - set(question.options))
            if unoffered:
                msg = f"Judgment worker answered question '{question_key}' with options it does not offer: {unoffered}"
                raise JudgmentAnswerMismatchError(msg)
        case RatingQuestion():
            if not isinstance(answer, RatingAnswer):
                raise JudgmentAnswerMismatchError(_wrong_kind_message(question_key=question_key, question=question, answer=answer))
            nb_levels = len(question.levels)
            named_levels = {answer.level, *(answer.probabilities or {})}
            out_of_scale = sorted(level for level in named_levels if not 0 <= level < nb_levels)
            if out_of_scale:
                msg = (
                    f"Judgment worker answered question '{question_key}' with levels {out_of_scale}, "
                    f"outside its scale of {nb_levels} levels (0 to {nb_levels - 1})"
                )
                raise JudgmentAnswerMismatchError(msg)


def _wrong_kind_message(*, question_key: str, question: JudgmentQuestion, answer: JudgmentAnswer) -> str:
    return f"Judgment worker answered question '{question_key}' with a '{answer.kind}' answer, but it asked for '{question.kind}'"
