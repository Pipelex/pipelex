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
from pipelex.cogt.exceptions import (
    CogtError,
    ExtractJobFailureError,
    ImgGenGenerationError,
    InferenceErrorCategory,
    JudgmentJobFailureError,
    LLMCompletionError,
    SearchJobFailureError,
)
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
# OpenAI's refusal when the messages and the completion the request reserves with max_tokens together pass the window
_OPENAI_MESSAGES_AND_COMPLETION: _Body = {
    "error": {
        "message": (
            "This model's maximum context length is 128000 tokens. However, you requested 130000 tokens "
            "(10000 in the messages, 120000 in the completion). Please reduce the length of the messages or completion."
        ),
        "type": "invalid_request_error",
        "param": "messages",
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
# Anthropic's 413 for a request over its payload size, which says nothing about the context window
_ANTHROPIC_REQUEST_TOO_LARGE: _Body = {
    "type": "error",
    "error": {"type": "request_too_large", "message": "Request exceeds the maximum allowed number of bytes."},
}


def _answering(*, body: _Body, status_code: int = 400) -> httpx.MockTransport:
    """A transport whose every request the provider answers with the status, a 400 unless told, carrying the body."""

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=status_code, json=body, request=request)

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


def _openai_compatible_refusal(*, body: _Body, status_code: int) -> BaseException:
    """An OpenAI-compatible server, a gateway, answering with another 4xx than 400, raised by the OpenAI SDK."""
    with httpx.Client(transport=_answering(body=body, status_code=status_code)) as http_client:
        client = openai.OpenAI(api_key="unused-in-this-test", base_url=f"{_ORIGIN}/v1", max_retries=0, http_client=http_client)
        with pytest.raises(openai.APIStatusError) as exc_info:
            client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": "Summarize the contract."}])
    return exc_info.value


def _anthropic_status_refusal(*, body: _Body, status_code: int) -> BaseException:
    with httpx.Client(transport=_answering(body=body, status_code=status_code)) as http_client:
        client = anthropic.Anthropic(api_key="unused-in-this-test", base_url=_ORIGIN, max_retries=0, http_client=http_client)
        with pytest.raises(anthropic.APIStatusError) as exc_info:
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
        _openai_refusal,
        _OPENAI_MESSAGES_AND_COMPLETION,
        extract_openai_metadata,
        CoreCode.MODEL_CONTEXT_EXCEEDED,
        id="openai-messages-and-completion",
    ),
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
        ("raise_refusal", "answer", "extract_metadata"),
        [
            pytest.param(_anthropic_refusal, _ANTHROPIC_INPUT_AND_MAX_TOKENS, extract_anthropic_metadata, id="anthropic-input-and-max-tokens"),
            pytest.param(_openai_refusal, _OPENAI_MESSAGES_AND_COMPLETION, extract_openai_metadata, id="openai-messages-and-completion"),
            pytest.param(_anthropic_refusal, _ANTHROPIC_PROMPT_TOO_LONG, extract_anthropic_metadata, id="anthropic-prompt-too-long"),
        ],
    )
    def test_a_language_models_window_advice_names_the_input_and_max_tokens(
        self,
        raise_refusal: Callable[[Any], BaseException],
        answer: Any,
        extract_metadata: Callable[[BaseException], ProviderErrorMetadata],
    ) -> None:
        """The window holds the prompt and the output max_tokens reserves, which may be the deck's default: either can be reduced."""
        metadata = extract_metadata(raise_refusal(answer))
        classification = classify_inference_error(metadata, family=InferenceErrorFamily.LLM)
        rendered = render_inference_error(
            metadata=metadata,
            classification=classification,
            family=InferenceErrorFamily.LLM,
            model_desc="test-model-desc",
            model_handle="test-model",
        )

        assert rendered.resolve_error_code() == CoreCode.MODEL_CONTEXT_EXCEEDED
        assert rendered.user_action is not None
        assert rendered.user_action.detail == (
            "The prompt plus the output requested with max_tokens exceed the model's context window — shorten the input "
            "or lower max_tokens, or choose a model with a larger context window."
        )

    @pytest.mark.parametrize(
        ("family", "expected_class", "expected_detail"),
        [
            (
                InferenceErrorFamily.IMG_GEN,
                ImgGenGenerationError,
                "The prompt or its input images exceed what the image model can read — shorten the prompt or send fewer images.",
            ),
            (
                InferenceErrorFamily.EXTRACT,
                ExtractJobFailureError,
                "The document exceeds what the extraction model can read — send a shorter document, or split it.",
            ),
            (
                InferenceErrorFamily.SEARCH,
                SearchJobFailureError,
                "The query built from the inputs exceeds what the search model can read — shorten the inputs.",
            ),
            (
                InferenceErrorFamily.JUDGMENT,
                JudgmentJobFailureError,
                "The material to judge exceeds what the judgment model can read — shorten it.",
            ),
        ],
    )
    @pytest.mark.parametrize(
        ("raise_refusal", "answer", "extract_metadata"),
        [
            pytest.param(_gemini_refusal, _GEMINI_INPUT_TOKEN_COUNT, extract_google_metadata, id="gemini-input-token-count"),
            pytest.param(_anthropic_refusal, _ANTHROPIC_PROMPT_TOO_LONG, extract_anthropic_metadata, id="anthropic-prompt-too-long"),
            pytest.param(_bedrock_refusal, _BEDROCK_INPUT_TOO_LONG, extract_bedrock_metadata, id="bedrock-input-too-long"),
        ],
    )
    def test_another_familys_advice_fits_what_its_model_reads(
        self,
        raise_refusal: Callable[[Any], BaseException],
        answer: Any,
        extract_metadata: Callable[[BaseException], ProviderErrorMetadata],
        family: InferenceErrorFamily,
        expected_class: type[CogtError],
        expected_detail: str,
    ) -> None:
        """The inputs exceed what the model can read, whatever it does, but only a language model has max_tokens or a window to choose."""
        metadata = extract_metadata(raise_refusal(answer))
        classification = classify_inference_error(metadata, family=family)
        rendered = render_inference_error(
            metadata=metadata,
            classification=classification,
            family=family,
            model_desc="test-model-desc",
            model_handle="test-model",
        )

        assert isinstance(rendered, expected_class)
        assert rendered.resolve_error_code() == CoreCode.MODEL_CONTEXT_EXCEEDED
        assert rendered.user_action is not None
        assert rendered.user_action.kind is UserActionKind.CHANGE_INPUT
        assert rendered.user_action.detail == expected_detail
        assert "context window" not in rendered.user_action.detail
        assert "max_tokens" not in rendered.user_action.detail

    @pytest.mark.parametrize(
        ("raise_refusal", "extract_metadata", "expected_error_code"),
        [
            pytest.param(
                lambda: _openai_compatible_refusal(body=_OPENAI_CONTEXT_LENGTH, status_code=422),
                extract_openai_metadata,
                CoreCode.MODEL_CONTEXT_EXCEEDED,
                id="gateway-422-context-length",
            ),
            pytest.param(
                lambda: _openai_compatible_refusal(body=_OPENAI_CONTEXT_LENGTH, status_code=413),
                extract_openai_metadata,
                CoreCode.MODEL_CONTEXT_EXCEEDED,
                id="gateway-413-context-length",
            ),
            pytest.param(
                lambda: _anthropic_status_refusal(body=_ANTHROPIC_REQUEST_TOO_LARGE, status_code=413),
                extract_anthropic_metadata,
                CoreCode.INPUT_TOO_LARGE,
                id="anthropic-413-payload-size",
            ),
        ],
    )
    def test_another_4xx_reads_the_window_as_a_400_does(
        self,
        raise_refusal: Callable[[], BaseException],
        extract_metadata: Callable[[BaseException], ProviderErrorMetadata],
        expected_error_code: ErrorCode,
    ) -> None:
        """A gateway may answer the window's refusal with a 422 or a 413; a 413 over the payload size alone keeps its reading."""
        metadata = extract_metadata(raise_refusal())
        assert metadata.status_code != 400

        classification = classify_inference_error(metadata, family=InferenceErrorFamily.LLM)
        rendered = render_inference_error(
            metadata=metadata,
            classification=classification,
            family=InferenceErrorFamily.LLM,
            model_desc="test-model-desc",
            model_handle="test-model",
        )

        assert classification.error_code == expected_error_code
        assert classification.user_action_kind is UserActionKind.CHANGE_INPUT
        assert rendered.resolve_error_code() == expected_error_code
        assert rendered.user_action is not None
        assert ("context window" in rendered.user_action.detail) is (expected_error_code == CoreCode.MODEL_CONTEXT_EXCEEDED)

    @pytest.mark.parametrize(
        ("status_code", "sdk_exception_type"),
        [
            (500, "InternalServerError"),
            (None, "ValidationError"),
        ],
    )
    def test_the_same_words_on_another_answer_never_read_as_the_window(self, status_code: int | None, sdk_exception_type: str) -> None:
        """Only a 4xx is read for the window: the words on a 5xx, or quoted in a parse failure, keep their own reading."""
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
