"""Only the hosted dialect sends `x-pipelex-metadata`: no direct-provider or Portkey path does.

The run's identity and the host's labels are forwarded to our own gateway, which bills and logs the
call; a vendor reached directly with the caller's own key has no use for them and must not receive
them. The Anthropic worker is the path most at risk, because it serves both a direct Anthropic
backend and Claude behind the Pipelex service from the same code: only the extras factory the hosted package
builds it with adds the header, so a worker built without one sends nothing, whatever its backend.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from anthropic import AsyncAnthropic
from anthropic.types import Message, ToolUseBlock, Usage

from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams, LLMJobReport
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.providers.anthropic.anthropic_llm_worker import AnthropicLLMWorker
from pipelex.providers.openai.openai_completions_factory import OpenAICompletionsFactory
from pipelex.providers.openai.openai_responses_factory import OpenAIResponsesFactory
from pipelex.providers.pipelex_hosted.pipelex_hosted_constants import PIPELEX_HOSTED_METADATA_HEADER
from pipelex.providers.portkey.portkey_factory import PortkeyFactory
from tests.helpers.instructor_test_utils import DummySchema
from tests.unit.pipelex.providers.pipelex_hosted.test_data import PipelexHostedMetadataTestData

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class _RequestCapturedError(Exception):
    """Raised by a stubbed SDK call once it has recorded its arguments."""


def _llm_job() -> LLMJob:
    return LLMJob(
        job_metadata=PipelexHostedMetadataTestData.JOB_METADATA,
        llm_prompt=LLMPrompt(user_text="ping"),
        job_params=LLMJobParams(temperature=0.5),
        job_config=LLMJobConfig(schema_reask_max_attempts=1),
        job_report=LLMJobReport(),
    )


def _model(mocker: MockerFixture, *, backend_name: str) -> Any:
    model = mocker.MagicMock()
    model.desc = "test-model-desc"
    model.model_id = "claude-test"
    model.name = "claude-test"
    model.backend_name = backend_name
    model.thinking_mode = None
    model.listed_constraints = []
    model.extra_headers = None
    model.structure_method = StructureMethod.INSTRUCTOR_ANTHROPIC_TOOLS
    return model


def _anthropic_worker(mocker: MockerFixture, *, sdk_client: AsyncAnthropic, backend_name: str) -> AnthropicLLMWorker:
    from instructor import from_anthropic  # ruff: ignore[import-outside-top-level]

    worker = object.__new__(AnthropicLLMWorker)
    worker.inference_model = _model(mocker, backend_name=backend_name)
    worker.extras_factory = None
    worker.default_max_tokens = 4096
    worker.anthropic_async_client = sdk_client
    worker.instructor_for_objects = from_anthropic(client=sdk_client, mode=StructureMethod.INSTRUCTOR_ANTHROPIC_TOOLS.as_instructor_mode())
    config = mocker.MagicMock()
    config.inference.llm.anthropic.structured_output_timeout_seconds = 1200
    mocker.patch("pipelex.providers.anthropic.anthropic_llm_worker.get_config", return_value=config)
    return worker


def _tool_call_message() -> Message:
    return Message(
        id="msg_test",
        type="message",
        role="assistant",
        model="claude-test",
        content=[ToolUseBlock(type="tool_use", id="toolu_test", name="DummySchema", input={"text": "answer"})],
        stop_reason="tool_use",
        stop_sequence=None,
        usage=Usage(input_tokens=1, output_tokens=1),
    )


@pytest.mark.asyncio(loop_scope="class")
class TestPipelexHostedMetadataScope:
    @pytest.mark.parametrize(
        "factory",
        [
            OpenAICompletionsFactory(is_http_url_enabled=False),
            OpenAIResponsesFactory(is_http_url_enabled=False),
            PortkeyFactory,
        ],
        ids=["openai-completions", "openai-responses", "portkey"],
    )
    async def test_other_backends_extras_carry_no_metadata_header(self, mocker: MockerFixture, factory: Any) -> None:
        model = _model(mocker, backend_name="openai")
        model.model_id = "gpt-4o"

        extra_headers, _ = factory.make_extras(inference_model=model, inference_job=_llm_job(), output_desc="text")

        assert PIPELEX_HOSTED_METADATA_HEADER not in extra_headers
        assert "x-portkey-metadata" not in extra_headers

    @pytest.mark.parametrize("backend_name", ["anthropic", "bedrock", "pipelex_hosted"])
    async def test_a_plain_anthropic_worker_sends_no_headers_on_the_text_call(self, mocker: MockerFixture, backend_name: str) -> None:
        sdk_client = AsyncAnthropic(api_key="test-key")
        stream = mocker.MagicMock(side_effect=_RequestCapturedError)
        mocker.patch.object(sdk_client.messages, "stream", new=stream)
        worker = _anthropic_worker(mocker, sdk_client=sdk_client, backend_name=backend_name)

        with pytest.raises(_RequestCapturedError):
            await worker._gen_text(_llm_job())  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert "extra_headers" not in stream.call_args.kwargs

    @pytest.mark.parametrize("backend_name", ["anthropic", "pipelex_hosted"])
    async def test_a_plain_anthropic_worker_sends_no_headers_on_the_structured_call(self, mocker: MockerFixture, backend_name: str) -> None:
        sdk_client = AsyncAnthropic(api_key="test-key")
        create = mocker.AsyncMock(return_value=_tool_call_message())
        mocker.patch.object(sdk_client.messages, "create", new=create)
        worker = _anthropic_worker(mocker, sdk_client=sdk_client, backend_name=backend_name)

        await worker._gen_object(_llm_job(), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        await_args = create.await_args
        assert await_args is not None
        assert PIPELEX_HOSTED_METADATA_HEADER not in str(await_args.kwargs.get("extra_headers"))
