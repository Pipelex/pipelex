from __future__ import annotations

from typing import TYPE_CHECKING

import anthropic
import httpx
import pytest

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.providers.anthropic import anthropic_llm_worker
from tests.helpers.anthropic_structured_request import make_structured_worker, sent_request
from tests.helpers.instructor_test_utils import DummySchema, make_llm_job, wrap_in_instructor_retry

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.providers.anthropic.anthropic_llm_worker import AnthropicLLMWorker

# What a 1200-second structured timeout lets the SDK's heuristic produce: 1200 * 128000 / 3600
TIMEOUT_SAFE_MAX_TOKENS = 42666
LOWERED_NOTE = f"The structured output's max_tokens was lowered from 64000 to {TIMEOUT_SAFE_MAX_TOKENS} to fit its 1200-second timeout."


def _rate_limit_error() -> anthropic.RateLimitError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.RateLimitError("Rate limit exceeded", response=httpx.Response(429, request=request), body=None)


def _fail_the_structured_call(mocker: MockerFixture, *, worker: AnthropicLLMWorker) -> None:
    """Make the structured call fail as instructor fails it on a rate-limited request: wrapped, after one attempt."""
    instructor_client = mocker.MagicMock()
    instructor_client.chat.completions.create_with_completion = mocker.AsyncMock(side_effect=wrap_in_instructor_retry(_rate_limit_error()))
    worker.instructor_for_objects = instructor_client


@pytest.mark.asyncio(loop_scope="class")
class TestAnthropicStructuredClamp:
    async def test_a_lowered_caller_max_tokens_is_logged_as_a_warning(self, mocker: MockerFixture) -> None:
        worker, create = make_structured_worker(mocker, structure_method=StructureMethod.INSTRUCTOR_ANTHROPIC_TOOLS)
        llm_job = make_llm_job(mocker)
        llm_job.job_params.max_tokens = 64000
        warning = mocker.patch.object(anthropic_llm_worker.log, "warning")

        result = await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert result.text == "answer"
        assert sent_request(create)["max_tokens"] == TIMEOUT_SAFE_MAX_TOKENS
        warning.assert_called_once_with(
            "A structured output's token limit was lowered to fit its timeout",
            fields={
                "model_handle": "claude-test",
                "requested_max_tokens": 64000,
                "effective_max_tokens": TIMEOUT_SAFE_MAX_TOKENS,
                "timeout_seconds": 1200,
            },
        )

    async def test_a_lowered_model_default_is_logged_at_debug_level(self, mocker: MockerFixture) -> None:
        """A model default above the timeout's limit is lowered on every structured call, so it does not warn."""
        worker, create = make_structured_worker(mocker, structure_method=StructureMethod.INSTRUCTOR_ANTHROPIC_TOOLS, default_max_tokens=64000)
        warning = mocker.patch.object(anthropic_llm_worker.log, "warning")
        debug = mocker.patch.object(anthropic_llm_worker.log, "debug")

        await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert sent_request(create)["max_tokens"] == TIMEOUT_SAFE_MAX_TOKENS
        warning.assert_not_called()
        lowered_calls = [
            call
            for call in debug.call_args_list
            if call.args == ("The model's default token limit was lowered to fit the structured output's timeout",)
        ]
        assert len(lowered_calls) == 1

    async def test_an_error_of_the_lowered_call_says_the_limit_was_lowered(self, mocker: MockerFixture) -> None:
        """The note is added to the error the call raises, whose class and retryable category stay as they were."""
        worker, _ = make_structured_worker(mocker, structure_method=StructureMethod.INSTRUCTOR_ANTHROPIC_TOOLS, default_max_tokens=64000)
        _fail_the_structured_call(mocker, worker=worker)

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        error = exc_info.value
        assert error.message.endswith(LOWERED_NOTE)
        assert str(error) == error.message
        assert error.error_category == InferenceErrorCategory.TRANSIENT
        assert error.to_error_report().retryable is True

    async def test_an_error_of_a_call_sent_as_given_carries_no_note(self, mocker: MockerFixture) -> None:
        worker, _ = make_structured_worker(mocker, structure_method=StructureMethod.INSTRUCTOR_ANTHROPIC_TOOLS)
        _fail_the_structured_call(mocker, worker=worker)

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert "was lowered" not in exc_info.value.message
