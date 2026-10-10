from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError, LLMCompletionRefusedError, LLMCompletionTruncatedError
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.providers.bedrock.bedrock_client_boto3 import BedrockClientBoto3
from pipelex.providers.bedrock.bedrock_llm_worker import BedrockLLMWorker
from tests.helpers.completion_stop import STOP_TEST_PARTIAL_TEXT, STOP_TEST_PIPE_CODE, make_text_llm_job

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class _AnsweringConverse:
    """A boto3 Bedrock runtime whose Converse call answers with the response given."""

    def __init__(self, *, response: dict[str, Any]) -> None:
        self.response = response

    def converse(self, **params: Any) -> dict[str, Any]:  # ruff: ignore[unused-method-argument]
        return self.response


def _converse_response(*, stop_reason: str, text: str) -> dict[str, Any]:
    content: list[dict[str, Any]] = [{"text": text}] if text else []
    return {
        "usage": {"inputTokens": 30, "outputTokens": 2048},
        "output": {"message": {"role": "assistant", "content": content}},
        "stopReason": stop_reason,
    }


def _worker(mocker: MockerFixture, *, stop_reason: str, text: str) -> BedrockLLMWorker:
    """A worker over the real boto3 client, so the stop reason travels the client's own reading of the Converse answer."""
    client = BedrockClientBoto3(aws_region="us-east-1")
    client.boto3_client = _AnsweringConverse(response=_converse_response(stop_reason=stop_reason, text=text))
    worker = object.__new__(BedrockLLMWorker)
    model = mocker.MagicMock()
    model.desc = "test-model-desc"
    model.model_id = "mistral.test"
    model.name = "mistral-bedrock"
    model.accepts_temperature = True
    worker.inference_model = model
    worker.default_max_tokens = 2048
    worker.bedrock_client_for_text = client
    return worker


@pytest.mark.asyncio(loop_scope="class")
class TestBedrockWorkerStop:
    @pytest.mark.parametrize("text", [STOP_TEST_PARTIAL_TEXT, ""])
    async def test_a_text_cut_at_max_tokens_raises_the_truncation(self, mocker: MockerFixture, text: str) -> None:
        worker = _worker(mocker, stop_reason="max_tokens", text=text)
        llm_job = make_text_llm_job()

        with pytest.raises(LLMCompletionTruncatedError) as exc_info:
            await worker._gen_text(llm_job=llm_job)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        error = exc_info.value
        assert error.stop_reason == "max_tokens"
        assert error.pipe_code == STOP_TEST_PIPE_CODE
        assert error.max_tokens == 2048
        assert error.output_tokens == 2048
        assert STOP_TEST_PARTIAL_TEXT not in error.message
        assert llm_job.job_report.llm_tokens_usage is not None
        assert llm_job.job_report.llm_tokens_usage.nb_tokens_by_category == {TokenCategory.INPUT: 30, TokenCategory.OUTPUT: 2048}

    @pytest.mark.parametrize("stop_reason", ["content_filtered", "guardrail_intervened"])
    async def test_a_filtered_text_raises_the_refusal(self, mocker: MockerFixture, stop_reason: str) -> None:
        worker = _worker(mocker, stop_reason=stop_reason, text="")

        with pytest.raises(LLMCompletionRefusedError) as exc_info:
            await worker._gen_text(llm_job=make_text_llm_job())  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.stop_reason == stop_reason

    async def test_a_normal_stop_returns_the_text_unchanged(self, mocker: MockerFixture) -> None:
        worker = _worker(mocker, stop_reason="end_turn", text=STOP_TEST_PARTIAL_TEXT)

        text = await worker._gen_text(llm_job=make_text_llm_job())  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert text == STOP_TEST_PARTIAL_TEXT

    async def test_a_normal_stop_with_no_text_is_an_empty_text_error(self, mocker: MockerFixture) -> None:
        """An answer with no text block no longer crashes the client: the worker refuses the empty text as other workers do."""
        worker = _worker(mocker, stop_reason="end_turn", text="")

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=make_text_llm_job())  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert type(exc_info.value) is LLMCompletionError
        assert exc_info.value.error_category == InferenceErrorCategory.CONTENT
