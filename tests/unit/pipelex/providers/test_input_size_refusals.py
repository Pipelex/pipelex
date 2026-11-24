from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import openai
import pytest
from mthds.protocol.problem.registry import CoreCode, ProblemDomain, RetryVerdict

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
    extract_google_metadata,
    extract_openai_metadata,
)
from pipelex.cogt.inference.error_classify import InferenceErrorFamily, classify_inference_error
from pipelex.cogt.inference.error_render import render_inference_error
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.errors.problem import ProblemView
from pipelex.providers.openai.openai_completions_llm_worker import OpenAICompletionsLLMWorker
from tests.helpers.completion_stop import make_text_llm_job
from tests.unit.pipelex.providers.provider_refusals import (
    ORIGIN,
    Body,
    answering,
    anthropic_refusal,
    anthropic_status_refusal,
    gemini_refusal,
    openai_compatible_refusal,
    openai_refusal,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_mock import MockerFixture

    from pipelex.errors.error_codes import ErrorCode

# The advice every family gives a file over the provider's size limit
_SIZE_ADVICE = "A file in the inputs exceeds the provider's size limit — make it smaller, or split it."

# Each provider's refusal of a file, an image or a payload over its size limit, worded as the provider words it.
# Anthropic's, observed on dev on 2026-11-24, called directly
_ANTHROPIC_FILE_OVER_SIZE: Body = {
    "type": "error",
    "error": {"type": "invalid_request_error", "message": "The file exceeds the maximum allowed size."},
}
# The same refusal relayed by the Manifold gateway, as the dev worker's log shows its body
_MANIFOLD_RELAYED_FILE_OVER_SIZE: Body = {
    "error": {"message": "anthropic error: The file exceeds the maximum allowed size.", "type": "invalid_request_error"},
    "provider": "anthropic",
}
# Anthropic's refusal of one image over its 5 MB limit
_ANTHROPIC_IMAGE_OVER_SIZE: Body = {
    "type": "error",
    "error": {
        "type": "invalid_request_error",
        "message": "messages.0.content.1.image.source.base64: image exceeds 5 MB maximum: 5607404 bytes > 5242880 bytes",
    },
}
# Gemini's refusal of a request payload over its inline limit
_GEMINI_PAYLOAD_OVER_SIZE: Body = {
    "error": {"code": 400, "message": "Request payload size exceeds the limit: 20971520 bytes.", "status": "INVALID_ARGUMENT"}
}
# Anthropic's 413 for a request over its payload size, documented with this message and type
_ANTHROPIC_REQUEST_TOO_LARGE: Body = {
    "type": "error",
    "error": {"type": "request_too_large", "message": "Request exceeds the maximum allowed number of bytes."},
}

# Refusals that name a limit but not a file's size, which the size signal must leave alone.
# Anthropic's refusal of a max_tokens over the model's output bound, which is our request's fault
_ANTHROPIC_MAX_TOKENS_OVER_BOUND: Body = {
    "type": "error",
    "error": {
        "type": "invalid_request_error",
        "message": "max_tokens: 300000 > 64000, which is the maximum allowed number of output tokens for claude-sonnet-4-5",
    },
}
# OpenAI's refusal of the same
_OPENAI_MAX_TOKENS_OVER_BOUND: Body = {
    "error": {
        "message": "max_tokens is too large: 200000. This model supports at most 16384 completion tokens, whereas you provided 200000.",
        "type": "invalid_request_error",
        "param": "max_tokens",
        "code": "invalid_value",
    }
}
# Anthropic's refusal of a prompt over the context window, which keeps its own code
_ANTHROPIC_PROMPT_TOO_LONG: Body = {
    "type": "error",
    "error": {"type": "invalid_request_error", "message": "prompt is too long: 208310 tokens > 200000 maximum"},
}
# Gemini's answer to a document it could not read, which may be over its size or of a type it cannot open
_GEMINI_NO_PAGES: Body = {"error": {"code": 400, "message": "The document has no pages.", "status": "INVALID_ARGUMENT"}}


def _classify_and_render(
    metadata: ProviderErrorMetadata, *, family: InferenceErrorFamily = InferenceErrorFamily.LLM
) -> tuple[ErrorCode, InferenceErrorCategory, UserActionKind, CogtError]:
    classification = classify_inference_error(metadata, family=family)
    rendered = render_inference_error(
        metadata=metadata,
        classification=classification,
        family=family,
        model_desc="test-model-desc",
        model_handle="test-model",
    )
    return classification.error_code, classification.category, classification.user_action_kind, rendered


class TestInputSizeRefusals:
    @pytest.mark.parametrize(
        ("raise_refusal", "answer", "extract_metadata"),
        [
            pytest.param(anthropic_refusal, _ANTHROPIC_FILE_OVER_SIZE, extract_anthropic_metadata, id="anthropic-file-over-size"),
            pytest.param(anthropic_refusal, _MANIFOLD_RELAYED_FILE_OVER_SIZE, extract_anthropic_metadata, id="manifold-relayed-file-over-size"),
            pytest.param(anthropic_refusal, _ANTHROPIC_IMAGE_OVER_SIZE, extract_anthropic_metadata, id="anthropic-image-over-size"),
            pytest.param(gemini_refusal, _GEMINI_PAYLOAD_OVER_SIZE, extract_google_metadata, id="gemini-payload-over-size"),
            pytest.param(openai_refusal, _MANIFOLD_RELAYED_FILE_OVER_SIZE, extract_openai_metadata, id="gateway-openai-dialect-file-over-size"),
            pytest.param(anthropic_refusal, _ANTHROPIC_REQUEST_TOO_LARGE, extract_anthropic_metadata, id="anthropic-request-too-large-on-a-400"),
        ],
    )
    def test_a_provider_400_refusing_a_file_over_its_size_reads_input_too_large(
        self,
        raise_refusal: Callable[[Any], BaseException],
        answer: Any,
        extract_metadata: Callable[[BaseException], ProviderErrorMetadata],
    ) -> None:
        """The provider's own 400 about a file's size, extracted, classified and rendered as a worker does, is the caller's input."""
        metadata = extract_metadata(raise_refusal(answer))
        assert metadata.status_code == 400

        error_code, category, user_action_kind, rendered = _classify_and_render(metadata)

        assert error_code == CoreCode.INPUT_TOO_LARGE
        assert category is InferenceErrorCategory.CONTENT
        assert user_action_kind is UserActionKind.CHANGE_INPUT
        assert isinstance(rendered, LLMCompletionError)
        assert rendered.resolve_error_code() == CoreCode.INPUT_TOO_LARGE
        assert rendered.user_action is not None
        assert rendered.user_action.detail == _SIZE_ADVICE

    @pytest.mark.parametrize(
        ("raise_refusal", "answer", "extract_metadata", "expected_error_code"),
        [
            pytest.param(
                anthropic_refusal,
                _ANTHROPIC_MAX_TOKENS_OVER_BOUND,
                extract_anthropic_metadata,
                CoreCode.RUNTIME_UNEXPECTED,
                id="anthropic-max-tokens",
            ),
            pytest.param(openai_refusal, _OPENAI_MAX_TOKENS_OVER_BOUND, extract_openai_metadata, CoreCode.RUNTIME_UNEXPECTED, id="openai-max-tokens"),
            pytest.param(
                anthropic_refusal,
                _ANTHROPIC_PROMPT_TOO_LONG,
                extract_anthropic_metadata,
                CoreCode.MODEL_CONTEXT_EXCEEDED,
                id="anthropic-prompt-too-long",
            ),
            pytest.param(gemini_refusal, _GEMINI_NO_PAGES, extract_google_metadata, CoreCode.RUNTIME_UNEXPECTED, id="gemini-no-pages"),
        ],
    )
    def test_a_400_naming_another_limit_keeps_its_own_reading(
        self,
        raise_refusal: Callable[[Any], BaseException],
        answer: Any,
        extract_metadata: Callable[[BaseException], ProviderErrorMetadata],
        expected_error_code: ErrorCode,
    ) -> None:
        """A max_tokens over its bound is our request's, a prompt over the window is the window's, and Gemini's no-pages is ambiguous."""
        metadata = extract_metadata(raise_refusal(answer))
        assert metadata.status_code == 400

        error_code, _, _, rendered = _classify_and_render(metadata)

        assert error_code == expected_error_code
        assert rendered.user_action is not None
        assert rendered.user_action.detail != _SIZE_ADVICE

    @pytest.mark.parametrize(
        ("raise_refusal", "extract_metadata", "expected_category"),
        [
            pytest.param(
                lambda: openai_compatible_refusal(body=_MANIFOLD_RELAYED_FILE_OVER_SIZE, status_code=422),
                extract_openai_metadata,
                InferenceErrorCategory.CONTENT,
                id="gateway-422-file-over-size",
            ),
            pytest.param(
                lambda: anthropic_status_refusal(body=_ANTHROPIC_REQUEST_TOO_LARGE, status_code=413),
                extract_anthropic_metadata,
                InferenceErrorCategory.CONTENT,
                id="anthropic-413-request-too-large",
            ),
            pytest.param(
                lambda: openai_compatible_refusal(body={"error": {"message": "Payload Too Large", "type": "invalid_request_error"}}, status_code=413),
                extract_openai_metadata,
                InferenceErrorCategory.CONFIGURATION,
                id="gateway-bare-413",
            ),
        ],
    )
    def test_another_4xx_reads_the_size_as_a_400_does(
        self,
        raise_refusal: Callable[[], BaseException],
        extract_metadata: Callable[[BaseException], ProviderErrorMetadata],
        expected_category: InferenceErrorCategory,
    ) -> None:
        """A gateway may answer the size refusal with a 422 or a 413; a bare 413 keeps its configuration reading."""
        metadata = extract_metadata(raise_refusal())
        assert metadata.status_code != 400

        error_code, category, user_action_kind, rendered = _classify_and_render(metadata)

        assert error_code == CoreCode.INPUT_TOO_LARGE
        assert category is expected_category
        assert user_action_kind is UserActionKind.CHANGE_INPUT
        assert rendered.user_action is not None
        assert rendered.user_action.detail == _SIZE_ADVICE

    @pytest.mark.parametrize(
        ("family", "expected_class"),
        [
            (InferenceErrorFamily.IMG_GEN, ImgGenGenerationError),
            (InferenceErrorFamily.EXTRACT, ExtractJobFailureError),
            (InferenceErrorFamily.SEARCH, SearchJobFailureError),
            (InferenceErrorFamily.JUDGMENT, JudgmentJobFailureError),
        ],
    )
    def test_every_family_reads_the_size_refusal(self, family: InferenceErrorFamily, expected_class: type[CogtError]) -> None:
        """A file over the provider's size is the caller's whatever the model does with it."""
        metadata = extract_anthropic_metadata(anthropic_refusal(_ANTHROPIC_FILE_OVER_SIZE))

        error_code, category, _, rendered = _classify_and_render(metadata, family=family)

        assert error_code == CoreCode.INPUT_TOO_LARGE
        assert category is InferenceErrorCategory.CONTENT
        assert isinstance(rendered, expected_class)
        assert rendered.user_action is not None
        assert rendered.user_action.detail == _SIZE_ADVICE

    @pytest.mark.parametrize(
        ("status_code", "sdk_exception_type"),
        [
            (500, "InternalServerError"),
            (None, "ValidationError"),
        ],
    )
    def test_the_same_words_on_another_answer_never_read_as_the_size(self, status_code: int | None, sdk_exception_type: str) -> None:
        """Only a 4xx is read for the size: the words on a 5xx, or quoted in a parse failure, keep their own reading."""
        metadata = ProviderErrorMetadata(
            provider=ProviderName.ANTHROPIC,
            sdk_exception_type=sdk_exception_type,
            message="The file exceeds the maximum allowed size.",
            status_code=status_code,
        )

        error_code, _, _, rendered = _classify_and_render(metadata)

        assert error_code != CoreCode.INPUT_TOO_LARGE
        assert rendered.user_action is not None
        assert rendered.user_action.detail != _SIZE_ADVICE

    @pytest.mark.builds_problems_without_required_params(
        reason="a provider's size refusal in words names neither the input nor, reliably, its size and the limit, the parameters of input.too_large"
    )
    @pytest.mark.asyncio
    async def test_the_worker_reports_the_file_over_size_as_the_callers_input(self, mocker: MockerFixture) -> None:
        """End to end through a worker: the run report reads `input.too_large`, the caller's to fix, never our `runtime.unexpected`."""
        worker = object.__new__(OpenAICompletionsLLMWorker)
        inference_model = mocker.MagicMock()
        inference_model.name = "claude-4.5-haiku"
        inference_model.model_id = "claude-4.5-haiku"
        inference_model.desc = "claude-4.5-haiku → Model[claude-4.5-haiku]"
        inference_model.thinking_mode = None
        inference_model.accepts_temperature = True
        inference_model.listed_constraints = []
        worker.inference_model = inference_model
        completions_factory = mocker.MagicMock()
        completions_factory.make_simple_messages = mocker.AsyncMock(return_value=[{"role": "user", "content": "Summarize the contract."}])
        completions_factory.make_extras = mocker.MagicMock(return_value=({}, {}))
        worker.openai_completions_factory = completions_factory

        async with httpx.AsyncClient(transport=answering(body=_MANIFOLD_RELAYED_FILE_OVER_SIZE)) as http_client:
            worker.openai_client_for_text = openai.AsyncOpenAI(
                api_key="unused-in-this-test", base_url=f"{ORIGIN}/v1", max_retries=0, http_client=http_client
            )
            with pytest.raises(LLMCompletionError) as exc_info:
                await worker._gen_text(llm_job=make_text_llm_job())  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        caller = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert caller.code == CoreCode.INPUT_TOO_LARGE
        assert caller.domain == ProblemDomain.INPUT
        assert caller.retry == RetryVerdict.NO
        assert isinstance(exc_info.value.__cause__, openai.BadRequestError)
