"""Fakes for driving the Anthropic worker's structured call through a real instructor client.

The worker is built as it builds itself, over an Anthropic SDK client whose ``messages.create`` records the
request and answers with a tool call, so a test asserts what instructor actually sends rather than the
arguments the worker hands it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from anthropic import AsyncAnthropic
from anthropic.types import ContentBlock, Message, ToolUseBlock, Usage

from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.providers.anthropic.anthropic_config import AnthropicConfig
from pipelex.providers.anthropic.anthropic_llm_worker import AnthropicLLMWorker

if TYPE_CHECKING:
    from unittest.mock import AsyncMock

    from pytest_mock import MockerFixture

    from pipelex.cogt.llm.structured_output import StructureMethod

ANTHROPIC_LEVEL_MAP: dict[str, str] = {
    "none": "disabled",
    "minimal": "low",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "xhigh",
    "max": "max",
}
ANTHROPIC_BUDGET_MAP: dict[str, int] = {"none": 0, "minimal": 512, "low": 1024, "medium": 5000, "high": 16384, "xhigh": 32768, "max": 65536}
# The minimum the kit's Anthropic backends declare as the model's min_thinking_budget
ANTHROPIC_MIN_THINKING_BUDGET = 1024

STEERING_LINE = "Return only the tool call and no additional text."
PROMPT_SYSTEM_TEXT = "You are a helpful test assistant."


def anthropic_budget(*, family: str, effort: str) -> int:
    assert family == "anthropic"
    return ANTHROPIC_BUDGET_MAP[effort]


def make_message(*content: ContentBlock) -> Message:
    return Message(
        id="msg_test",
        type="message",
        role="assistant",
        model="claude-test",
        content=list(content),
        stop_reason="tool_use",
        stop_sequence=None,
        usage=Usage(input_tokens=1, output_tokens=1),
    )


def tool_call_message() -> Message:
    return make_message(ToolUseBlock(type="tool_use", id="toolu_test", name="DummySchema", input={"text": "answer"}))


def make_structured_worker(
    mocker: MockerFixture,
    *,
    structure_method: StructureMethod,
    thinking_mode: ThinkingMode = ThinkingMode.NONE,
    default_max_tokens: int = 4096,
    responses: list[Message] | None = None,
    accepts_temperature: bool = True,
) -> tuple[AnthropicLLMWorker, AsyncMock]:
    """A worker whose instructor client is built as the worker builds it, over an SDK call that records the request."""
    from instructor import from_anthropic  # ruff: ignore[import-outside-top-level]

    sdk_client = AsyncAnthropic(api_key="test-key")
    if responses is None:
        create = mocker.AsyncMock(return_value=tool_call_message())
    else:
        create = mocker.AsyncMock(side_effect=responses)
    mocker.patch.object(sdk_client.messages, "create", new=create)

    worker = object.__new__(AnthropicLLMWorker)

    worker.extras_factory = None
    model = mocker.MagicMock()
    model.desc = "test-model-desc"
    model.model_id = "claude-test"
    model.name = "claude-test"
    model.accepts_temperature = accepts_temperature
    model.structure_method = structure_method
    model.thinking_mode = thinking_mode
    model.min_thinking_budget = ANTHROPIC_MIN_THINKING_BUDGET
    model.max_thinking_budget = None
    worker.inference_model = model
    worker.default_max_tokens = default_max_tokens
    worker.instructor_for_objects = from_anthropic(client=sdk_client, mode=structure_method.as_instructor_mode())

    config = mocker.MagicMock()
    config.inference.llm.anthropic = AnthropicConfig(structured_output_timeout_seconds=1200, effort_to_level_map=ANTHROPIC_LEVEL_MAP)
    config.inference.llm.get_reasoning_budget = mocker.MagicMock(side_effect=anthropic_budget)
    mocker.patch("pipelex.providers.anthropic.anthropic_llm_worker.get_config", return_value=config)
    return worker, create


def sent_request(create: AsyncMock) -> dict[str, Any]:
    create.assert_awaited_once()
    await_args = create.await_args
    assert await_args is not None
    return dict(await_args.kwargs)


def system_texts(request: dict[str, Any]) -> list[str]:
    system = request["system"]
    if isinstance(system, str):
        return [system]
    return [block["text"] for block in system]
