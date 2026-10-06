"""The Converse request the Bedrock clients send, and the temperature the Bedrock worker hands them.

Both clients build their request with ``make_converse_params``. A temperature is sent unless the model lists
`temperature_unsupported`, whose provider refuses one: the worker then hands the client none, and the request's
inference config carries no temperature key at all.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from pipelex.providers.bedrock.bedrock_client_boto3 import BedrockClientBoto3
from pipelex.providers.bedrock.bedrock_client_protocol import make_converse_params
from pipelex.providers.bedrock.bedrock_llm_worker import BedrockLLMWorker

if TYPE_CHECKING:
    from unittest.mock import AsyncMock

    from pytest_mock import MockerFixture

_MESSAGES: list[dict[str, Any]] = [{"role": "user", "content": [{"text": "Hello."}]}]


class _RecordingConverse:
    """Stands in for the boto3 runtime client: records the parameters ``converse`` receives."""

    def __init__(self) -> None:
        self.params: list[dict[str, Any]] = []

    def converse(self, **params: Any) -> dict[str, Any]:
        self.params.append(params)
        return {"usage": {"inputTokens": 1, "outputTokens": 2}, "output": {"message": {"content": [{"text": "answer"}]}}}


def _make_worker(mocker: MockerFixture, *, accepts_temperature: bool) -> tuple[BedrockLLMWorker, AsyncMock]:
    worker = object.__new__(BedrockLLMWorker)
    model = mocker.MagicMock()
    model.desc = "test-model-desc"
    model.model_id = "mistral.test"
    model.name = "mistral.test"
    model.accepts_temperature = accepts_temperature
    worker.inference_model = model
    worker.default_max_tokens = 4096
    chat = mocker.AsyncMock(return_value=("answer", {}))
    client = mocker.MagicMock()
    client.chat = chat
    worker.bedrock_client_for_text = client
    return worker, chat


def _make_llm_job(mocker: MockerFixture) -> Any:
    job = mocker.MagicMock()
    job.applied_job_params = None
    job.job_params.temperature = 0.5
    job.job_params.max_tokens = None
    job.job_params.reasoning_effort = None
    job.job_params.reasoning_budget = None
    job.job_report.llm_tokens_usage = None
    job.llm_prompt.system_text = "system"
    job.llm_prompt.user_text = "Hello."
    job.llm_prompt.user_images = []
    return job


class TestMakeConverseParams:
    def test_a_temperature_goes_in_the_inference_config(self) -> None:
        params = make_converse_params(messages=_MESSAGES, system_text="Be brief.", model="mistral.test", temperature=0.5, max_tokens=100)

        assert params == {
            "modelId": "mistral.test",
            "messages": _MESSAGES,
            "inferenceConfig": {"temperature": 0.5, "maxTokens": 100},
            "system": [{"text": "Be brief."}],
        }

    def test_without_a_temperature_the_inference_config_has_no_temperature_key(self) -> None:
        params = make_converse_params(messages=_MESSAGES, system_text=None, model="mistral.test", temperature=None, max_tokens=100)

        assert params == {"modelId": "mistral.test", "messages": _MESSAGES, "inferenceConfig": {"maxTokens": 100}}


@pytest.mark.asyncio(loop_scope="class")
class TestBedrockConverseRequest:
    async def test_the_boto3_client_sends_the_built_request(self) -> None:
        client = BedrockClientBoto3(aws_region="us-east-1")
        recording = _RecordingConverse()
        client.boto3_client = recording

        text, _ = await client.chat(messages=_MESSAGES, system_text=None, model="mistral.test", temperature=None, max_tokens=100)

        assert text == "answer"
        assert recording.params == [
            make_converse_params(messages=_MESSAGES, system_text=None, model="mistral.test", temperature=None, max_tokens=100)
        ]

    @pytest.mark.parametrize(("accepts_temperature", "expected_temperature"), [(True, 0.5), (False, None)])
    async def test_the_worker_hands_the_client_a_temperature_only_when_the_model_takes_one(
        self, mocker: MockerFixture, accepts_temperature: bool, expected_temperature: float | None
    ) -> None:
        worker, chat = _make_worker(mocker, accepts_temperature=accepts_temperature)

        await worker._gen_text(llm_job=_make_llm_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        chat.assert_awaited_once()
        assert chat.await_args is not None
        assert chat.await_args.kwargs["temperature"] == expected_temperature
