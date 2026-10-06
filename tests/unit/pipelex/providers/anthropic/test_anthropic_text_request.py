"""The temperature the Anthropic worker's text call sends.

A temperature is sent unless thinking is on, or the model lists `temperature_unsupported`, whose provider
refuses one. The text call streams, so the SDK client's ``messages.stream`` is replaced by one that records its
arguments and hands back a final message.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from anthropic import Omit
from anthropic.types import TextBlock

from pipelex.cogt.llm.llm_job_components import ReasoningEffort
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.providers.anthropic.anthropic_config import AnthropicConfig
from pipelex.providers.anthropic.anthropic_llm_worker import AnthropicLLMWorker
from tests.helpers.anthropic_structured_request import ANTHROPIC_LEVEL_MAP, ANTHROPIC_MIN_THINKING_BUDGET, anthropic_budget, make_message
from tests.helpers.instructor_test_utils import make_llm_job

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from pytest_mock import MockerFixture


def _make_text_worker(
    mocker: MockerFixture,
    *,
    thinking_mode: ThinkingMode = ThinkingMode.NONE,
    accepts_temperature: bool = True,
) -> tuple[AnthropicLLMWorker, MagicMock]:
    """A worker whose streaming call records its arguments and answers with one text block."""
    stream = mocker.MagicMock()
    stream.get_final_message = mocker.AsyncMock(return_value=make_message(TextBlock(type="text", text="answer")))
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
    model.thinking_mode = thinking_mode
    model.accepts_temperature = accepts_temperature
    model.min_thinking_budget = ANTHROPIC_MIN_THINKING_BUDGET
    model.max_thinking_budget = None
    worker.inference_model = model
    worker.default_max_tokens = 4096
    worker.anthropic_async_client = sdk_client

    config = mocker.MagicMock()
    config.inference.llm.anthropic = AnthropicConfig(structured_output_timeout_seconds=1200, effort_to_level_map=ANTHROPIC_LEVEL_MAP)
    config.inference.llm.get_reasoning_budget = mocker.MagicMock(side_effect=anthropic_budget)
    mocker.patch("pipelex.providers.anthropic.anthropic_llm_worker.get_config", return_value=config)
    return worker, sdk_client.messages.stream


def _sent_request(stream: MagicMock) -> dict[str, Any]:
    stream.assert_called_once()
    return dict(stream.call_args.kwargs)


@pytest.mark.asyncio(loop_scope="class")
class TestAnthropicTextRequest:
    async def test_without_thinking_the_temperature_is_sent(self, mocker: MockerFixture) -> None:
        worker, stream = _make_text_worker(mocker)

        result = await worker._gen_text(llm_job=make_llm_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert result == "answer"
        assert _sent_request(stream)["temperature"] == 0.5

    async def test_thinking_drops_the_temperature(self, mocker: MockerFixture) -> None:
        worker, stream = _make_text_worker(mocker, thinking_mode=ThinkingMode.ADAPTIVE)
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.HIGH

        await worker._gen_text(llm_job=llm_job)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        request = _sent_request(stream)
        assert request["thinking"] == {"type": "adaptive"}
        assert isinstance(request["temperature"], Omit)

    async def test_a_model_refusing_temperature_omits_it_without_thinking(self, mocker: MockerFixture) -> None:
        worker, stream = _make_text_worker(mocker, accepts_temperature=False)

        await worker._gen_text(llm_job=make_llm_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert isinstance(_sent_request(stream)["temperature"], Omit)
