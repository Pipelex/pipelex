import pytest

from pipelex import pretty_print
from pipelex.cogt.exceptions import JudgmentModelNotFoundError
from pipelex.cogt.judgment.judgment_job import JudgmentJob
from pipelex.cogt.judgment.judgment_job_factory import JudgmentJobFactory
from pipelex.cogt.judgment.judgment_models import (
    ChoiceAnswer,
    JudgmentAnswer,
    JudgmentKind,
    JudgmentQuestion,
    RatingAnswer,
    YesNoAnswer,
)
from pipelex.cogt.judgment.judgment_setting import JudgmentSetting
from pipelex.cogt.judgment.judgment_worker_factory import JudgmentWorkerFactory
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.runtime_hub import get_model_deck
from pipelex.system.job_metadata import JobMetadata
from tests.integration.pipelex.cogt.test_data import JudgmentTestCases
from tests.integration.pipelex.fixtures.model_combo import ModelCombo


def _inference_model(judgment_combo: ModelCombo) -> InferenceModelSpec:
    return get_model_deck().get_required_inference_model(model_handle=judgment_combo.handle, model_type=ModelType.JUDGMENT)


def _job(*, judgment_combo: ModelCombo, job_metadata: JobMetadata, questions: dict[str, JudgmentQuestion]) -> JudgmentJob:
    return JudgmentJobFactory.make_judgment_job(
        state=JudgmentTestCases.STATE,
        questions=questions,
        judgment_setting=JudgmentSetting(model=judgment_combo.handle),
        job_metadata=job_metadata,
    )


def _assert_expected_verdict(*, answer: JudgmentAnswer) -> None:
    """The verdict exactly, the probability within the margin the spike's stability measure sets."""
    match answer:
        case YesNoAnswer():
            assert answer.probability is not None, "TypeSafe measures a probability for every yes/no answer"
            assert answer.probability > 0.5, "The unambiguous case must land on the yes side"
            assert abs(answer.probability - JudgmentTestCases.EXPECTED_IS_URGENT_PROBABILITY) <= JudgmentTestCases.PROBABILITY_MARGIN
        case ChoiceAnswer():
            assert answer.choice == JudgmentTestCases.EXPECTED_TEAM
            assert answer.probabilities is not None
            assert set(answer.probabilities) == set(JudgmentTestCases.TEAM.options)
        case RatingAnswer():
            assert answer.level == JudgmentTestCases.EXPECTED_SEVERITY_LEVEL
            assert answer.probabilities is not None
            assert set(answer.probabilities) == set(range(len(JudgmentTestCases.SEVERITY.levels)))


@pytest.mark.judgment
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestJudgment:
    @pytest.mark.parametrize(("topic", "question", "kind"), JudgmentTestCases.EACH_KIND)
    async def test_each_kind_on_an_unambiguous_case(
        self,
        judgment_combo: ModelCombo,
        job_metadata: JobMetadata,
        topic: str,
        question: JudgmentQuestion,
        kind: JudgmentKind,
    ) -> None:
        """Each question kind alone, as a batch of one, answers the same verdict the spike recorded."""
        worker = JudgmentWorkerFactory.make_judgment_worker(_inference_model(judgment_combo))
        answers = await worker.judge(_job(judgment_combo=judgment_combo, job_metadata=job_metadata, questions={topic: question}))
        pretty_print(answers, title=f"Judgment answer ({topic})")

        assert set(answers) == {topic}
        assert answers[topic].kind == kind
        _assert_expected_verdict(answer=answers[topic])

    async def test_several_questions_in_one_job(self, judgment_combo: ModelCombo, job_metadata: JobMetadata) -> None:
        """The three kinds in one request, each answered under its own key, with real usage and the pinned model on the report."""
        inference_model = _inference_model(judgment_combo)
        worker = JudgmentWorkerFactory.make_judgment_worker(inference_model)
        job = _job(judgment_combo=judgment_combo, job_metadata=job_metadata, questions=JudgmentTestCases.THREE_QUESTIONS)

        answers = await worker.judge(job)
        pretty_print(answers, title="Judgment answers (three questions, one request)")

        assert set(answers) == set(JudgmentTestCases.THREE_QUESTIONS)
        for answer in answers.values():
            _assert_expected_verdict(answer=answer)

        usage = job.job_report.judgment_tokens_usage
        assert usage is not None
        assert usage.nb_tokens_by_category.get(TokenCategory.INPUT, 0) > 0, "Usage is per request and the API has always reported it"
        assert TokenCategory.OUTPUT in usage.nb_tokens_by_category
        assert usage.inference_model_id == inference_model.model_id
        assert usage.inference_model_id.startswith("jev-")
        assert usage.inference_model_id != "jev-latest", "The deck pins a versioned id"

    async def test_an_unknown_model_is_a_missing_model(self, judgment_combo: ModelCombo, job_metadata: JobMetadata) -> None:
        """A model id this API does not serve comes back as a 400 and is rendered as the family's model-not-found error."""
        inference_model = _inference_model(judgment_combo).model_copy(update={"model_id": "jev-does-not-exist"})
        worker = JudgmentWorkerFactory.make_judgment_worker(inference_model)

        with pytest.raises(JudgmentModelNotFoundError) as exc_info:
            await worker.judge(_job(judgment_combo=judgment_combo, job_metadata=job_metadata, questions={"is_urgent": JudgmentTestCases.IS_URGENT}))

        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.status_code == 400
        assert exc_info.value.provider_metadata.request_id is not None
