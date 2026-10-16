from __future__ import annotations

from typing import TYPE_CHECKING, Any

import anthropic
import botocore.session
import httpx
import openai
import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from google.genai import errors as genai_errors
from mistralai.client import Mistral
from mistralai.client.errors import MistralError
from mistralai.client.models import UserMessage
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import ErrorDomain
from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError
from pipelex.cogt.inference.error_classification import (
    ProviderErrorMetadata,
    UserActionKind,
    extract_anthropic_metadata,
    extract_bedrock_metadata,
    extract_google_metadata,
    extract_mistral_metadata,
    extract_openai_metadata,
)
from pipelex.cogt.inference.error_classify import InferenceErrorFamily, classify_inference_error
from pipelex.cogt.inference.error_render import render_inference_error
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.providers.openai.openai_completions_llm_worker import OpenAICompletionsLLMWorker
from tests.helpers.completion_stop import make_text_llm_job

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_mock import MockerFixture

    from pipelex.errors.error_codes import ErrorCode

_ORIGIN = "https://provider.example.com"

# The body of a provider's 400, as its API sends it.
_Body = dict[str, Any]

# Each provider's 400 for a prompt over the model's context window, worded as the provider words it.
_OPENAI_CONTEXT_LENGTH: _Body = {
    "error": {
        "message": (
            "This model's maximum context length is 128000 tokens. However, your messages resulted in 130412 tokens. "
            "Please reduce the length of the messages."
        ),
        "type": "invalid_request_error",
        "param": "messages",
        "code": "context_length_exceeded",
    }
}
_OPENAI_CONTEXT_WINDOW: _Body = {
    "error": {
        "message": "Your input exceeds the context window of this model. Please adjust your input and try again.",
        "type": "invalid_request_error",
        "param": "input",
        "code": "context_length_exceeded",
    }
}
_ANTHROPIC_PROMPT_TOO_LONG: _Body = {
    "type": "error",
    "error": {"type": "invalid_request_error", "message": "prompt is too long: 208310 tokens > 200000 maximum"},
}
_ANTHROPIC_INPUT_AND_MAX_TOKENS: _Body = {
    "type": "error",
    "error": {
        "type": "invalid_request_error",
        "message": "input length and `max_tokens` exceed context limit: 197202 + 8192 > 200000, decrease input length or `max_tokens` and try again",
    },
}
_MISTRAL_PROMPT_TOO_LARGE: _Body = {
    "object": "error",
    "message": "Prompt contains 140000 tokens and 0 draft tokens, too large for model with 131072 maximum context length",
    "type": "invalid_request_message_error",
    "param": None,
    "code": "3051",
}
_GEMINI_INPUT_TOKEN_COUNT: _Body = {
    "error": {
        "code": 400,
        "message": "The input token count (1234567) exceeds the maximum number of tokens allowed (1048576).",
        "status": "INVALID_ARGUMENT",
    }
}
_BEDROCK_INPUT_TOO_LONG = "Input is too long for requested model."

# The same providers' 400s for a request of ours they could not take, which say nothing about the context window.
_OPENAI_INVALID_TYPE: _Body = {
    "error": {
        "message": "Invalid type for 'messages[0].content': expected one of a string or array of objects, but got an integer instead.",
        "type": "invalid_request_error",
        "param": "messages[0].content",
        "code": "invalid_type",
    }
}
_ANTHROPIC_FIELD_REQUIRED: _Body = {"type": "error", "error": {"type": "invalid_request_error", "message": "max_tokens: Field required"}}
_MISTRAL_INVALID_MESSAGE: _Body = {
    "object": "error",
    "message": "Assistant message must have either content or tool_calls, but not none.",
    "type": "invalid_request_message_error",
    "param": None,
    "code": "3230",
}
_GEMINI_INVALID_PAYLOAD: _Body = {
    "error": {"code": 400, "message": 'Invalid JSON payload received. Unknown name "foo": Cannot find field.', "status": "INVALID_ARGUMENT"}
}
_BEDROCK_INVALID_MODEL = "The provided model identifier is invalid."


def _answering(*, body: _Body) -> httpx.MockTransport:
    """A transport whose every request the provider answers with a 400 carrying the body."""

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=400, json=body, request=request)

    return httpx.MockTransport(handle)


def _openai_refusal(body: _Body) -> BaseException:
    with httpx.Client(transport=_answering(body=body)) as http_client:
        client = openai.OpenAI(api_key="unused-in-this-test", base_url=f"{_ORIGIN}/v1", max_retries=0, http_client=http_client)
        with pytest.raises(openai.BadRequestError) as exc_info:
            client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": "Summarize the contract."}])
    return exc_info.value


def _anthropic_refusal(body: _Body) -> BaseException:
    with httpx.Client(transport=_answering(body=body)) as http_client:
        client = anthropic.Anthropic(api_key="unused-in-this-test", base_url=_ORIGIN, max_retries=0, http_client=http_client)
        with pytest.raises(anthropic.BadRequestError) as exc_info:
            client.messages.create(model="claude-sonnet-4-5", max_tokens=8192, messages=[{"role": "user", "content": "Summarize the contract."}])
    return exc_info.value


def _mistral_refusal(body: _Body) -> BaseException:
    with httpx.Client(transport=_answering(body=body)) as http_client:
        client = Mistral(api_key="unused-in-this-test", server_url=_ORIGIN, client=http_client)
        with pytest.raises(MistralError) as exc_info:
            client.chat.complete(model="mistral-large-latest", messages=[UserMessage(content="Summarize the contract.")])
    return exc_info.value


def _gemini_refusal(body: _Body) -> BaseException:
    request = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent")
    with pytest.raises(genai_errors.ClientError) as exc_info:
        genai_errors.APIError.raise_for_response(httpx.Response(status_code=400, json=body, request=request))  # pyright: ignore[reportUnknownMemberType]
    return exc_info.value


def _bedrock_refusal(message: str) -> BaseException:
    """Bedrock's Converse refusal with the message, raised by a real bedrock-runtime client from a stubbed answer."""
    # The bedrock-runtime client botocore builds from its service model, whose operations it types as nothing
    client: Any = botocore.session.get_session().create_client(
        "bedrock-runtime", region_name="us-east-1", aws_access_key_id="unused-in-this-test", aws_secret_access_key="unused-in-this-test"
    )
    stubber = Stubber(client)
    stubber.add_client_error("converse", service_error_code="ValidationException", service_message=message, http_status_code=400)
    with stubber, pytest.raises(ClientError) as exc_info:
        client.converse(modelId="anthropic.claude-sonnet-4-5", messages=[{"role": "user", "content": [{"text": "Summarize the contract."}]}])
    return exc_info.value


# Each case: the provider's SDK raising its 400 from the provider's answer, the Extract step reading it, and the code
# the 400 must read.
_REFUSALS = [
    pytest.param(
        _openai_refusal, _OPENAI_CONTEXT_LENGTH, extract_openai_metadata, CoreCode.MODEL_CONTEXT_EXCEEDED, id="openai-maximum-context-length"
    ),
    pytest.param(_openai_refusal, _OPENAI_CONTEXT_WINDOW, extract_openai_metadata, CoreCode.MODEL_CONTEXT_EXCEEDED, id="openai-context-window"),
    pytest.param(
        _anthropic_refusal, _ANTHROPIC_PROMPT_TOO_LONG, extract_anthropic_metadata, CoreCode.MODEL_CONTEXT_EXCEEDED, id="anthropic-prompt-too-long"
    ),
    pytest.param(
        _anthropic_refusal,
        _ANTHROPIC_INPUT_AND_MAX_TOKENS,
        extract_anthropic_metadata,
        CoreCode.MODEL_CONTEXT_EXCEEDED,
        id="anthropic-input-and-max-tokens",
    ),
    pytest.param(
        _mistral_refusal, _MISTRAL_PROMPT_TOO_LARGE, extract_mistral_metadata, CoreCode.MODEL_CONTEXT_EXCEEDED, id="mistral-prompt-too-large"
    ),
    pytest.param(_gemini_refusal, _GEMINI_INPUT_TOKEN_COUNT, extract_google_metadata, CoreCode.MODEL_CONTEXT_EXCEEDED, id="gemini-input-token-count"),
    pytest.param(_bedrock_refusal, _BEDROCK_INPUT_TOO_LONG, extract_bedrock_metadata, CoreCode.MODEL_CONTEXT_EXCEEDED, id="bedrock-input-too-long"),
    pytest.param(_openai_refusal, _OPENAI_INVALID_TYPE, extract_openai_metadata, CoreCode.RUNTIME_UNEXPECTED, id="openai-invalid-type"),
    pytest.param(
        _anthropic_refusal, _ANTHROPIC_FIELD_REQUIRED, extract_anthropic_metadata, CoreCode.RUNTIME_UNEXPECTED, id="anthropic-field-required"
    ),
    pytest.param(_mistral_refusal, _MISTRAL_INVALID_MESSAGE, extract_mistral_metadata, CoreCode.RUNTIME_UNEXPECTED, id="mistral-invalid-message"),
    pytest.param(_gemini_refusal, _GEMINI_INVALID_PAYLOAD, extract_google_metadata, CoreCode.RUNTIME_UNEXPECTED, id="gemini-invalid-payload"),
    pytest.param(_bedrock_refusal, _BEDROCK_INVALID_MODEL, extract_bedrock_metadata, CoreCode.RUNTIME_UNEXPECTED, id="bedrock-invalid-model"),
]


class TestContextWindowRefusals:
    @pytest.mark.parametrize(("raise_refusal", "answer", "extract_metadata", "expected_error_code"), _REFUSALS)
    def test_a_provider_400_reads_context_exceeded_only_when_it_says_so(
        self,
        raise_refusal: Callable[[Any], BaseException],
        answer: Any,
        extract_metadata: Callable[[BaseException], ProviderErrorMetadata],
        expected_error_code: ErrorCode,
    ) -> None:
        """The provider's own 400, extracted, classified and rendered as a worker does, carries the code its wording earns."""
        sdk_exc = raise_refusal(answer)
        metadata = extract_metadata(sdk_exc)
        assert metadata.status_code == 400

        classification = classify_inference_error(metadata, family=InferenceErrorFamily.LLM)
        rendered = render_inference_error(
            metadata=metadata,
            classification=classification,
            family=InferenceErrorFamily.LLM,
            model_desc="test-model-desc",
            model_handle="test-model",
        )

        assert classification.category is InferenceErrorCategory.CONTENT
        assert classification.user_action_kind is UserActionKind.CHANGE_INPUT
        assert classification.error_code == expected_error_code
        assert isinstance(rendered, LLMCompletionError)
        assert rendered.resolve_error_code() == expected_error_code
        assert rendered.user_action is not None
        assert ("context window" in rendered.user_action.detail) is (expected_error_code == CoreCode.MODEL_CONTEXT_EXCEEDED)

    @pytest.mark.parametrize(
        ("status_code", "sdk_exception_type"),
        [
            (422, "UnprocessableEntityError"),
            (None, "ValidationError"),
        ],
    )
    def test_the_same_words_on_another_answer_never_read_as_the_window(self, status_code: int | None, sdk_exception_type: str) -> None:
        """Only a 400 is read for the window: the words on a 422, or quoted in a parse failure, keep their own reading."""
        metadata = ProviderErrorMetadata(
            provider=ProviderName.OPENAI,
            sdk_exception_type=sdk_exception_type,
            message="prompt is too long: 208310 tokens > 200000 maximum",
            status_code=status_code,
        )

        classification = classify_inference_error(metadata, family=InferenceErrorFamily.LLM)
        rendered = render_inference_error(
            metadata=metadata,
            classification=classification,
            family=InferenceErrorFamily.LLM,
            model_desc="test-model-desc",
            model_handle="test-model",
        )

        assert classification.error_code != CoreCode.MODEL_CONTEXT_EXCEEDED
        assert rendered.user_action is not None
        assert "context window" not in rendered.user_action.detail

    @pytest.mark.asyncio
    async def test_the_worker_reports_the_prompt_over_the_window_as_the_callers_input(self, mocker: MockerFixture) -> None:
        """End to end through a worker: the run report reads `model.context_exceeded`, the caller's to fix, answered 422."""
        worker = object.__new__(OpenAICompletionsLLMWorker)
        inference_model = mocker.MagicMock()
        inference_model.name = "gpt-4o"
        inference_model.model_id = "gpt-4o-2024-08-06"
        inference_model.desc = "gpt-4o → Model[gpt-4o-2024-08-06]"
        inference_model.thinking_mode = None
        inference_model.accepts_temperature = True
        inference_model.listed_constraints = []
        worker.inference_model = inference_model
        completions_factory = mocker.MagicMock()
        completions_factory.make_simple_messages = mocker.AsyncMock(return_value=[{"role": "user", "content": "Summarize the contract."}])
        completions_factory.make_extras = mocker.MagicMock(return_value=({}, {}))
        worker.openai_completions_factory = completions_factory

        async with httpx.AsyncClient(transport=_answering(body=_OPENAI_CONTEXT_LENGTH)) as http_client:
            worker.openai_client_for_text = openai.AsyncOpenAI(
                api_key="unused-in-this-test", base_url=f"{_ORIGIN}/v1", max_retries=0, http_client=http_client
            )
            with pytest.raises(LLMCompletionError) as exc_info:
                await worker._gen_text(llm_job=make_text_llm_job())  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        report = exc_info.value.to_error_report()
        assert report.code == CoreCode.MODEL_CONTEXT_EXCEEDED
        assert report.error_domain == ErrorDomain.INPUT
        assert report.retryable is False
        assert report.http_status == 422
        assert isinstance(exc_info.value.__cause__, openai.BadRequestError)
