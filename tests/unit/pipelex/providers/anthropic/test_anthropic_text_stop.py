from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from anthropic.types import ContentBlock, Message, TextBlock, ThinkingBlock, Usage

from pipelex.cogt.exceptions import LLMCompletionRefusedError, LLMCompletionTruncatedError
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.providers.anthropic.anthropic_config import AnthropicConfig
from pipelex.providers.anthropic.anthropic_llm_worker import AnthropicLLMWorker
from tests.helpers.anthropic_structured_request import ANTHROPIC_LEVEL_MAP, ANTHROPIC_MIN_THINKING_BUDGET, anthropic_budget
from tests.helpers.completion_stop import STOP_TEST_PARTIAL_TEXT, STOP_TEST_PIPE_CODE, make_text_llm_job

if TYPE_CHECKING:
    from anthropic.types import StopReason
    from pytest_mock import MockerFixture


def _final_message(*, stop_reason: StopReason, content: list[ContentBlock]) -> Message:
    return Message(
        id="msg_test",
        type="message",
        role="assistant",
        model="claude-test",
        content=content,
        stop_reason=stop_reason,
        stop_sequence=None,
        usage=Usage(input_tokens=120, output_tokens=4096),
    )


def _text_worker(mocker: MockerFixture, *, final_message: Message) -> AnthropicLLMWorker:
    """A worker whose streaming text call hands back the final message given."""
    stream = mocker.MagicMock()
    stream.get_final_message = mocker.AsyncMock(return_value=final_message)
    stream_context = mocker.MagicMock()
    stream_context.__aenter__ = mocker.AsyncMock(return_value=stream)
    stream_context.__aexit__ = mocker.AsyncMock(return_value=False)
    sdk_client = mocker.MagicMock()
    sdk_client.messages.stream = mocker.MagicMock(return_value=stream_context)

    worker = object.__new__(AnthropicLLMWorker)
    worker.extras_factory = None
    model = mocker.MagicMock()
    model.desc = "test-model-desc"
    model.model_id = "claude-test"
    model.name = "claude-test"
    model.thinking_mode = ThinkingMode.NONE
    model.accepts_temperature = True
    model.min_thinking_budget = ANTHROPIC_MIN_THINKING_BUDGET
    model.max_thinking_budget = None
    worker.inference_model = model
    worker.default_max_tokens = 4096
    worker.anthropic_async_client = sdk_client

    config = mocker.MagicMock()
    config.inference.llm.anthropic = AnthropicConfig(structured_output_timeout_seconds=1200, effort_to_level_map=ANTHROPIC_LEVEL_MAP)
    config.inference.llm.get_reasoning_budget = mocker.MagicMock(side_effect=anthropic_budget)
    mocker.patch("pipelex.providers.anthropic.anthropic_llm_worker.get_config", return_value=config)
    return worker


@pytest.mark.asyncio(loop_scope="class")
class TestAnthropicTextStop:
    @pytest.mark.parametrize(
        "content",
        [
            [TextBlock(type="text", text=STOP_TEST_PARTIAL_TEXT)],
            [],
            [ThinkingBlock(type="thinking", thinking="Weighing the clauses.", signature="sig")],
        ],
    )
    async def test_a_text_cut_at_max_tokens_raises_the_truncation(self, mocker: MockerFixture, content: list[ContentBlock]) -> None:
        """Partial text, no text, and only thinking with no text all stop on max_tokens and raise the truncation."""
        worker = _text_worker(mocker, final_message=_final_message(stop_reason="max_tokens", content=content))

        with pytest.raises(LLMCompletionTruncatedError) as exc_info:
            await worker._gen_text(llm_job=make_text_llm_job())  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        error = exc_info.value
        assert error.stop_reason == "max_tokens"
        assert error.pipe_code == STOP_TEST_PIPE_CODE
        assert error.max_tokens == 4096
        assert error.output_tokens == 4096
        assert STOP_TEST_PARTIAL_TEXT not in error.message

    async def test_a_refusal_raises_the_refusal(self, mocker: MockerFixture) -> None:
        final_message = _final_message(stop_reason="refusal", content=[TextBlock(type="text", text=STOP_TEST_PARTIAL_TEXT)])
        worker = _text_worker(mocker, final_message=final_message)

        with pytest.raises(LLMCompletionRefusedError) as exc_info:
            await worker._gen_text(llm_job=make_text_llm_job())  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.stop_reason == "refusal"

    async def test_a_normal_stop_returns_the_text_unchanged(self, mocker: MockerFixture) -> None:
        final_message = _final_message(stop_reason="end_turn", content=[TextBlock(type="text", text=STOP_TEST_PARTIAL_TEXT)])
        worker = _text_worker(mocker, final_message=final_message)

        text = await worker._gen_text(llm_job=make_text_llm_job())  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert text == STOP_TEST_PARTIAL_TEXT
