import json
from typing import Any

import httpx2
import pytest
from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy

from pipelex.cogt.exceptions import CogtError
from pipelex.cogt.judgment.judgment_job_factory import JudgmentJobFactory
from pipelex.cogt.judgment.judgment_setting import JudgmentSetting
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.providers.typesafe.typesafe_judgment_worker import TypesafeJudgmentWorker
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from tests.unit.pipelex.providers.typesafe.test_data import WIRE_ERROR_MAPPINGS, WireCase, load_wire_case, wire_case_names

# Not a credential: the replay transport never leaves the process, and the SDK refuses to build a client without some key.
_REPLAY_ONLY_KEY = "wire-replay-sends-nothing"


class _VendorReplay:
    """An HTTP transport that answers TypeSafe's half of one recorded exchange and keeps the request it was sent."""

    def __init__(self, *, case: WireCase) -> None:
        self.case = case
        self.sent_bodies: list[Any] = []

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        self.sent_bodies.append(json.loads(request.content))
        vendor_response = self.case.vendor_response
        if vendor_response is None:
            msg = f"Wire case '{self.case.name}' records no vendor exchange, and the worker called the vendor"
            raise AssertionError(msg)
        return httpx2.Response(status_code=vendor_response.status, json=vendor_response.body, headers=vendor_response.headers)


def _worker(*, case: WireCase, replay: _VendorReplay) -> TypesafeJudgmentWorker:
    client = AsyncTypeSafeClient(api_key=_REPLAY_ONLY_KEY, transport=httpx2.MockTransport(replay.handle), retry=RetryPolicy(max_retries=0))
    inference_model = InferenceModelSpec(
        backend_name="typesafe",
        name="wire-replay-judgment-model",
        sdk="typesafe",
        model_type=ModelType.JUDGMENT,
        model_id=case.request.model,
        inputs=["text"],
        outputs=["judgments"],
        costs={CostCategory.INPUT: 0.042, CostCategory.OUTPUT: 0},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
    )
    return TypesafeJudgmentWorker(sdk_instance=client, inference_model=inference_model)


@pytest.mark.asyncio(loop_scope="class")
class TestTypesafeWireReplay:
    """Every shared wire case, replayed through the worker with a real SDK client over a recorded transport."""

    @pytest.mark.parametrize("case_name", wire_case_names())
    async def test_the_worker_sends_and_answers_exactly_what_the_case_records(self, case_name: str) -> None:
        case = load_wire_case(case_name)
        replay = _VendorReplay(case=case)
        worker = _worker(case=case, replay=replay)
        job = JudgmentJobFactory.make_judgment_job(
            prompt=case.request.prompt,
            questions=case.request.questions,
            judgment_setting=JudgmentSetting(model="wire-replay-judgment-model"),
            job_metadata=JobMetadata(
                run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="u", pipeline_run_id=f"run_wire_{case_name}")
            ),
        )
        expected = case.response

        if expected.error is not None:
            mapping = WIRE_ERROR_MAPPINGS[expected.error.code]
            assert expected.status == mapping.status
            with pytest.raises(CogtError) as exc_info:
                await worker.judge(job)
            assert type(exc_info.value) is mapping.error_class
            assert exc_info.value.error_category == mapping.category
            assert exc_info.value.user_action is not None
            assert exc_info.value.user_action.kind == mapping.user_action_kind
        else:
            assert expected.body is not None
            outcomes = await worker.judge(job)
            assert outcomes == expected.body.answers
            usage = job.job_report.judgment_tokens_usage
            assert usage is not None
            expected_tokens: dict[TokenCategory, int] = {}
            if expected.body.usage.input_tokens is not None:
                expected_tokens[TokenCategory.INPUT] = expected.body.usage.input_tokens
            if expected.body.usage.output_tokens is not None:
                expected_tokens[TokenCategory.OUTPUT] = expected.body.usage.output_tokens
            assert usage.nb_tokens_by_category == expected_tokens

        if case.vendor_request is None:
            assert replay.sent_bodies == []
        else:
            assert replay.sent_bodies == [case.vendor_request]
