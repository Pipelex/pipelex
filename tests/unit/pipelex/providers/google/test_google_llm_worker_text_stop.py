from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from google import genai
from google.genai import types as genai_types

from pipelex.cogt.exceptions import LLMCompletionRefusedError, LLMCompletionTruncatedError
from pipelex.providers.google.google_config import GoogleConfig
from pipelex.providers.google.google_llm_worker import GoogleLLMWorker
from tests.helpers.completion_stop import STOP_TEST_PARTIAL_TEXT, STOP_TEST_PIPE_CODE, make_text_llm_job
from tests.helpers.google_structured_request import GOOGLE_LEVEL_MAP

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _response(*, finish_reason: genai_types.FinishReason, text: str) -> genai_types.GenerateContentResponse:
    content = genai_types.Content(role="model", parts=[genai_types.Part(text=text)]) if text else None
    return genai_types.GenerateContentResponse(
        candidates=[genai_types.Candidate(content=content, finish_reason=finish_reason)],
        usage_metadata=genai_types.GenerateContentResponseUsageMetadata(prompt_token_count=80, candidates_token_count=1024),
    )


def _text_worker(mocker: MockerFixture, *, response: genai_types.GenerateContentResponse) -> GoogleLLMWorker:
    """A worker whose text call answers with the response given."""
    client = genai.Client(api_key="test-key")
    mocker.patch.object(client.aio.models, "generate_content", new_callable=mocker.AsyncMock, return_value=response)
    worker = object.__new__(GoogleLLMWorker)
    model = mocker.MagicMock()
    model.desc = "test-model-desc"
    model.model_id = "gemini-pro"
    model.name = "gemini-pro"
    model.thinking_mode = None
    model.accepts_temperature = True
    worker.inference_model = model
    worker.genai_async_client = client.aio

    config = mocker.MagicMock()
    config.inference.llm.google = GoogleConfig(effort_to_level_map=GOOGLE_LEVEL_MAP)
    mocker.patch("pipelex.providers.google.google_llm_worker.get_config", return_value=config)
    return worker


@pytest.mark.asyncio(loop_scope="class")
class TestGoogleLLMWorkerTextStop:
    @pytest.mark.parametrize("text", [STOP_TEST_PARTIAL_TEXT, ""])
    async def test_a_candidate_cut_at_max_tokens_raises_the_truncation(self, mocker: MockerFixture, text: str) -> None:
        worker = _text_worker(mocker, response=_response(finish_reason=genai_types.FinishReason.MAX_TOKENS, text=text))

        with pytest.raises(LLMCompletionTruncatedError) as exc_info:
            await worker._gen_text(llm_job=make_text_llm_job(max_tokens=1024))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        error = exc_info.value
        assert error.stop_reason == "MAX_TOKENS"
        assert error.pipe_code == STOP_TEST_PIPE_CODE
        assert error.max_tokens == 1024
        assert error.output_tokens == 1024
        assert STOP_TEST_PARTIAL_TEXT not in error.message

    async def test_a_safety_stop_after_partial_text_raises_the_refusal(self, mocker: MockerFixture) -> None:
        worker = _text_worker(mocker, response=_response(finish_reason=genai_types.FinishReason.SAFETY, text=STOP_TEST_PARTIAL_TEXT))

        with pytest.raises(LLMCompletionRefusedError) as exc_info:
            await worker._gen_text(llm_job=make_text_llm_job())  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.stop_reason == "SAFETY"

    async def test_a_normal_stop_returns_the_text_unchanged(self, mocker: MockerFixture) -> None:
        worker = _text_worker(mocker, response=_response(finish_reason=genai_types.FinishReason.STOP, text=STOP_TEST_PARTIAL_TEXT))

        text = await worker._gen_text(llm_job=make_text_llm_job())  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert text == STOP_TEST_PARTIAL_TEXT
