from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest
from openai import AsyncOpenAI

from pipelex.cogt.exceptions import LLMCompletionRefusedError, LLMCompletionTruncatedError
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.providers.openai.openai_completions_factory import OpenAICompletionsFactory
from pipelex.providers.openai.openai_completions_llm_worker import OpenAICompletionsLLMWorker
from tests.helpers.completion_stop import STOP_TEST_PIPE_CODE, make_text_llm_job
from tests.unit.pipelex.providers.openai.test_data import GatewayStopTestData

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

GATEWAY_MODEL_HANDLE = "claude-5-sonnet"


def _gateway_body(*, finish_reason: str, content: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl_gateway",
        "object": "chat.completion",
        "created": 0,
        "model": "claude-5-sonnet",
        "choices": [{"index": 0, "finish_reason": finish_reason, "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 5758, "completion_tokens": 4096, "total_tokens": 9854},
    }


def _gateway_worker(mocker: MockerFixture, *, finish_reason: str, content: str) -> OpenAICompletionsLLMWorker:
    """A completions worker over a real OpenAI SDK client, whose transport answers as a gateway in non-strict mode does.

    The SDK parses the body itself, so the finish reason reaches the worker exactly as the SDK hands it over,
    a value outside OpenAI's own vocabulary included.
    """
    body = _gateway_body(finish_reason=finish_reason, content=content)

    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body, request=request)

    sdk_client = AsyncOpenAI(
        api_key="test-key",
        base_url="https://gateway.test/v1",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(answer)),
    )
    worker = object.__new__(OpenAICompletionsLLMWorker)
    model = mocker.MagicMock()
    model.desc = "gateway-model-desc"
    model.model_id = "claude-5-sonnet"
    model.name = GATEWAY_MODEL_HANDLE
    model.thinking_mode = ThinkingMode.NONE
    model.accepts_temperature = True
    model.extra_headers = None
    worker.inference_model = model
    worker.openai_completions_factory = OpenAICompletionsFactory(is_http_url_enabled=False)
    worker.openai_client_for_text = sdk_client
    return worker


@pytest.mark.asyncio(loop_scope="class")
class TestOpenAICompletionsGatewayStop:
    @pytest.mark.parametrize(("_topic", "finish_reason", "content"), GatewayStopTestData.TRUNCATION_CASES)
    async def test_a_passed_through_truncation_raises_the_truncation(
        self, mocker: MockerFixture, _topic: str, finish_reason: str, content: str
    ) -> None:
        worker = _gateway_worker(mocker, finish_reason=finish_reason, content=content)

        with pytest.raises(LLMCompletionTruncatedError) as exc_info:
            await worker._gen_text(llm_job=make_text_llm_job(max_tokens=4096))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        error = exc_info.value
        assert error.stop_reason == finish_reason
        assert error.model_handle == GATEWAY_MODEL_HANDLE
        assert error.output_tokens == 4096
        assert error.message == (
            f"The model '{GATEWAY_MODEL_HANDLE}' was cut off before it finished the text of pipe '{STOP_TEST_PIPE_CODE}' "
            f"(stop reason '{finish_reason}', 4096 output tokens used, max_tokens set to 4096), so the text is incomplete. "
            "Raise the pipe's max_tokens, or shorten its input."
        )

    @pytest.mark.parametrize(("_topic", "finish_reason", "content"), GatewayStopTestData.REFUSAL_CASES)
    async def test_a_passed_through_refusal_or_filter_raises_the_refusal(
        self, mocker: MockerFixture, _topic: str, finish_reason: str, content: str
    ) -> None:
        worker = _gateway_worker(mocker, finish_reason=finish_reason, content=content)

        with pytest.raises(LLMCompletionRefusedError) as exc_info:
            await worker._gen_text(llm_job=make_text_llm_job())  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.stop_reason == finish_reason
        assert exc_info.value.pipe_code == STOP_TEST_PIPE_CODE

    async def test_a_passed_through_normal_stop_returns_the_text(self, mocker: MockerFixture) -> None:
        worker = _gateway_worker(mocker, finish_reason="end_turn", content="The whole summary.")

        text = await worker._gen_text(llm_job=make_text_llm_job())  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert text == "The whole summary."
