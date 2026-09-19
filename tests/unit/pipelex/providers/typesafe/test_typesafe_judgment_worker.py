from typing import cast

import pytest
from pytest_mock import MockerFixture
from typesafe_sdk import AsyncTypeSafeClient, SystemOneResponse
from typesafe_sdk import Noul as TypesafeNoul
from typing_extensions import override

from pipelex.cogt.exceptions import JudgmentModelNotFoundError
from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
from pipelex.cogt.judgment.judgment_job import JudgmentJob
from pipelex.cogt.judgment.judgment_job_factory import JudgmentJobFactory
from pipelex.cogt.judgment.judgment_models import ChoiceQuestion, JudgmentQuestion, RatingQuestion, YesNoAnswer, YesNoQuestion
from pipelex.cogt.judgment.judgment_setting import JudgmentSetting
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.providers.typesafe.typesafe_judgment_worker import TypesafeJudgmentWorker
from pipelex.reporting.reporting_protocol import ReportingNoOp
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from tests.unit.pipelex.providers.typesafe.test_data import TestData, load_recorded_response, rebuild_recorded_exception

THREE_SHAPES_QUESTIONS: dict[str, JudgmentQuestion] = {
    "is_urgent": YesNoQuestion(instructions=TestData.THREE_SHAPES_INSTRUCTIONS["is_urgent"]),
    "team": ChoiceQuestion(
        instructions=TestData.THREE_SHAPES_INSTRUCTIONS["team"],
        options={"payments": None, "shipping": None, "accounts": None, "other": None},
    ),
    "severity": RatingQuestion(
        instructions=TestData.THREE_SHAPES_INSTRUCTIONS["severity"],
        levels=["Cosmetic", "Degraded with a workaround", "Blocking"],
    ),
}


class _RecordingDelegate(ReportingNoOp):
    def __init__(self) -> None:
        self.reported: list[InferenceJobAbstract] = []

    @override
    def report_inference_job(self, inference_job: InferenceJobAbstract) -> None:
        self.reported.append(inference_job)


def _model() -> InferenceModelSpec:
    return InferenceModelSpec(
        backend_name="typesafe",
        name="jev-1.13.0",
        sdk="typesafe",
        model_type=ModelType.JUDGMENT,
        model_id="jev-1.13.0",
        inputs=["text"],
        outputs=["judgments"],
        costs={CostCategory.INPUT: 0.042, CostCategory.OUTPUT: 0},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
    )


def _job(questions: dict[str, JudgmentQuestion]) -> JudgmentJob:
    return JudgmentJobFactory.make_judgment_job(
        state={"message": "Our production checkout has been returning 500s for every card payment since 09:14 UTC."},
        questions=questions,
        judgment_setting=JudgmentSetting(model="jev-1.13.0"),
        job_metadata=JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", user_id="u", pipeline_run_id="run_typesafe")),
    )


@pytest.mark.asyncio
class TestTypesafeJudgmentWorker:
    async def test_one_request_carries_the_whole_job_and_its_usage_is_recorded(self, mocker: MockerFixture) -> None:
        """The job goes out as a single request under the pinned model id, and the billed tokens land on the report."""
        client = mocker.Mock(spec=AsyncTypeSafeClient)
        client.system_one = mocker.AsyncMock(return_value=load_recorded_response(TestData.THREE_SHAPES))
        delegate = _RecordingDelegate()
        worker = TypesafeJudgmentWorker(sdk_instance=cast("AsyncTypeSafeClient", client), inference_model=_model(), reporting_delegate=delegate)
        job = _job(THREE_SHAPES_QUESTIONS)

        answers = await worker.judge(job)

        client.system_one.assert_awaited_once()
        call = client.system_one.await_args
        assert call is not None
        sent_state, sent_questions = call.args
        assert sent_state == job.state
        assert set(sent_questions) == set(THREE_SHAPES_QUESTIONS)
        assert isinstance(sent_questions["is_urgent"], TypesafeNoul)
        assert call.kwargs == {"model": "jev-1.13.0"}

        assert answers["is_urgent"] == YesNoAnswer(probability=0.98)
        usage = job.job_report.judgment_tokens_usage
        assert usage is not None
        assert usage.nb_tokens_by_category == {TokenCategory.INPUT: 506, TokenCategory.OUTPUT: 78}
        assert delegate.reported == [job]

    async def test_absent_usage_records_no_tokens_rather_than_a_guess(self, mocker: MockerFixture) -> None:
        response = load_recorded_response(TestData.USAGE_ONE_QUESTION)
        response_without_usage = SystemOneResponse.model_validate_json(
            response.model_dump_json().replace('"input_tokens":354', '"input_tokens":null').replace('"output_tokens":23', '"output_tokens":null')
        )
        client = mocker.Mock(spec=AsyncTypeSafeClient)
        client.system_one = mocker.AsyncMock(return_value=response_without_usage)
        worker = TypesafeJudgmentWorker(sdk_instance=cast("AsyncTypeSafeClient", client), inference_model=_model())
        job = _job({"is_urgent": YesNoQuestion(instructions="Is the message urgent?")})

        await worker.judge(job)

        usage = job.job_report.judgment_tokens_usage
        assert usage is not None
        assert usage.nb_tokens_by_category == {}

    async def test_a_refusal_is_classified_rendered_and_still_reported(self, mocker: MockerFixture) -> None:
        """An unknown model surfaces as the family's model-not-found error, carrying this backend, and the attempt is reported."""
        client = mocker.Mock(spec=AsyncTypeSafeClient)
        client.system_one = mocker.AsyncMock(side_effect=rebuild_recorded_exception(TestData.UNKNOWN_MODEL))
        delegate = _RecordingDelegate()
        worker = TypesafeJudgmentWorker(sdk_instance=cast("AsyncTypeSafeClient", client), inference_model=_model(), reporting_delegate=delegate)
        job = _job({"is_urgent": YesNoQuestion(instructions="Is the message urgent?")})

        with pytest.raises(JudgmentModelNotFoundError) as exc_info:
            await worker.judge(job)

        assert exc_info.value.backend_name == "typesafe"
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.request_id == "req_01a0b97aa532770083aece1331cb7c76"
        assert delegate.reported == [job]
        usage = job.job_report.judgment_tokens_usage
        assert usage is not None
        assert usage.nb_tokens_by_category == {}

    @pytest.mark.parametrize(
        ("requested_model_id", "expects_warning"),
        [
            pytest.param("jev-1.13.0", False, id="pin_honoured"),
            pytest.param("jev-latest", True, id="another_model_answered"),
        ],
    )
    async def test_it_warns_when_another_model_answered(self, mocker: MockerFixture, requested_model_id: str, expects_warning: bool) -> None:
        """The recorded response names ``jev-1.13.0``; asking for anything else is a pin the API did not honour."""
        warning = mocker.patch("pipelex.providers.typesafe.typesafe_judgment_worker.log.warning")
        client = mocker.Mock(spec=AsyncTypeSafeClient)
        client.system_one = mocker.AsyncMock(return_value=load_recorded_response(TestData.USAGE_ONE_QUESTION))
        worker = TypesafeJudgmentWorker(
            sdk_instance=cast("AsyncTypeSafeClient", client),
            inference_model=_model().model_copy(update={"model_id": requested_model_id}),
        )

        await worker.judge(_job({"is_urgent": YesNoQuestion(instructions="Is the message urgent?")}))

        if expects_warning:
            warning.assert_called_once()
            assert "'jev-latest'" in warning.call_args.args[0]
            assert "'jev-1.13.0'" in warning.call_args.args[0]
        else:
            warning.assert_not_called()
