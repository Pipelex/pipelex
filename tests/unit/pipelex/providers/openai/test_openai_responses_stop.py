from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from openai.types.responses import Response, ResponseOutputMessage, ResponseOutputText, ResponseUsage
from openai.types.responses.response import IncompleteDetails
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails

from pipelex.cogt.exceptions import LLMCompletionRefusedError, LLMCompletionTruncatedError
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from tests.helpers.completion_stop import STOP_TEST_PARTIAL_TEXT, STOP_TEST_PIPE_CODE, make_text_llm_job
from tests.helpers.openai_responses_request import make_worker

if TYPE_CHECKING:
    from typing import Literal

    from openai.types.responses import ResponseOutputItem
    from pytest_mock import MockerFixture


def _response(
    *,
    status: Literal["completed", "incomplete"],
    incomplete_reason: Literal["max_output_tokens", "content_filter"] | None,
    text: str,
) -> Response:
    output: list[ResponseOutputItem] = []
    if text:
        output.append(
            ResponseOutputMessage(
                id="msg_test",
                type="message",
                role="assistant",
                status=status,
                content=[ResponseOutputText(type="output_text", text=text, annotations=[])],
            )
        )
    return Response(
        id="resp_test",
        created_at=0,
        model="gpt-test",
        object="response",
        output=output,
        parallel_tool_calls=False,
        tool_choice="auto",
        tools=[],
        status=status,
        incomplete_details=IncompleteDetails(reason=incomplete_reason) if incomplete_reason else None,
        usage=ResponseUsage(
            input_tokens=40,
            input_tokens_details=InputTokensDetails(cached_tokens=0),
            output_tokens=512,
            output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
            total_tokens=552,
        ),
    )


@pytest.mark.asyncio(loop_scope="class")
class TestOpenAIResponsesStop:
    @pytest.mark.parametrize("text", [STOP_TEST_PARTIAL_TEXT, ""])
    async def test_an_answer_cut_at_its_output_limit_raises_the_truncation(self, mocker: MockerFixture, text: str) -> None:
        response = _response(status="incomplete", incomplete_reason="max_output_tokens", text=text)
        worker, _ = make_worker(mocker, thinking_mode=ThinkingMode.NONE, response=response)

        with pytest.raises(LLMCompletionTruncatedError) as exc_info:
            await worker._gen_text(llm_job=make_text_llm_job(max_tokens=512))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        error = exc_info.value
        assert error.stop_reason == "max_output_tokens"
        assert error.pipe_code == STOP_TEST_PIPE_CODE
        assert error.max_tokens == 512
        assert error.output_tokens == 512
        assert STOP_TEST_PARTIAL_TEXT not in error.message

    async def test_an_incomplete_answer_with_no_details_raises_the_truncation(self, mocker: MockerFixture) -> None:
        """The incomplete status alone says the partial text is unfinished, whether or not its details give a reason."""
        response = _response(status="incomplete", incomplete_reason=None, text=STOP_TEST_PARTIAL_TEXT)
        worker, _ = make_worker(mocker, thinking_mode=ThinkingMode.NONE, response=response)

        with pytest.raises(LLMCompletionTruncatedError) as exc_info:
            await worker._gen_text(llm_job=make_text_llm_job(max_tokens=512))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        error = exc_info.value
        assert error.stop_reason == "incomplete"
        assert error.pipe_code == STOP_TEST_PIPE_CODE
        assert error.output_tokens == 512
        assert STOP_TEST_PARTIAL_TEXT not in error.message

    async def test_a_filtered_answer_raises_the_refusal(self, mocker: MockerFixture) -> None:
        response = _response(status="incomplete", incomplete_reason="content_filter", text=STOP_TEST_PARTIAL_TEXT)
        worker, _ = make_worker(mocker, thinking_mode=ThinkingMode.NONE, response=response)

        with pytest.raises(LLMCompletionRefusedError) as exc_info:
            await worker._gen_text(llm_job=make_text_llm_job())  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.stop_reason == "content_filter"

    async def test_a_completed_answer_returns_the_text_unchanged(self, mocker: MockerFixture) -> None:
        response = _response(status="completed", incomplete_reason=None, text=STOP_TEST_PARTIAL_TEXT)
        worker, _ = make_worker(mocker, thinking_mode=ThinkingMode.NONE, response=response)

        text = await worker._gen_text(llm_job=make_text_llm_job())  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert text == STOP_TEST_PARTIAL_TEXT
