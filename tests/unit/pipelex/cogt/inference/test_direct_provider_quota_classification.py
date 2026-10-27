from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

import anthropic
import httpx
import openai
import pytest
from anthropic.lib.bedrock import AnthropicBedrock
from botocore.exceptions import ClientError
from google.genai import errors as genai_errors
from mistralai.client.errors import SDKError
from mthds.protocol.problem.registry import CoreCode

from pipelex.cogt.exceptions import InferenceErrorCategory
from pipelex.cogt.inference.error_classification import (
    ProviderErrorMetadata,
    UserActionKind,
    extract_anthropic_metadata,
    extract_azure_metadata,
    extract_bedrock_metadata,
    extract_google_metadata,
    extract_mistral_metadata,
    extract_openai_metadata,
)
from pipelex.cogt.inference.error_classify import ClassificationResult, InferenceErrorFamily, classify_inference_error
from pipelex.cogt.inference.error_render import render_inference_error
from pipelex.errors.problem import ProblemView
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from tests.unit.pipelex.cogt.test_data import DirectProviderQuotaTestData

if TYPE_CHECKING:
    from pipelex.errors.error_codes import ErrorCode

_TestData = DirectProviderQuotaTestData


def _response(*, url: str, status_code: int, content: str, headers: dict[str, str] | None = None) -> httpx.Response:
    request = httpx.Request("POST", url)
    return httpx.Response(
        status_code=status_code,
        request=request,
        content=content.encode(),
        headers={"content-type": "application/json", **(headers or {})},
    )


def _as_openai_raises_it(*, status_code: int, body: dict[str, Any], headers: dict[str, str] | None = None) -> BaseException:
    """Build the exception through the OpenAI client's own factory, which keeps the body's ``error`` section."""
    response = _response(url="https://api.openai.com/v1/chat/completions", status_code=status_code, content=json.dumps(body), headers=headers)
    client = openai.OpenAI(api_key="unused-in-this-test")
    return client._make_status_error_from_response(response)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]


def _as_anthropic_raises_it(*, status_code: int, body: dict[str, Any], headers: dict[str, str] | None = None) -> BaseException:
    """Build the exception through the Anthropic client's own factory, which keeps the whole body."""
    response = _response(url="https://api.anthropic.com/v1/messages", status_code=status_code, content=json.dumps(body), headers=headers)
    client = anthropic.Anthropic(api_key="unused-in-this-test")
    return client._make_status_error_from_response(response)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]


def _as_google_raises_it(*, status_code: int, body: dict[str, Any]) -> BaseException:
    """Build the exception as google-genai raises a client error, the response's JSON as its details."""
    response = _response(
        url="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
        status_code=status_code,
        content=json.dumps(body),
    )
    return genai_errors.ClientError(status_code, body, response)


def _as_mistral_raises_it(*, status_code: int, body: str) -> BaseException:
    """Build the exception as the Mistral SDK raises an error answer, with the response's text as its body."""
    response = _response(url="https://api.mistral.ai/v1/chat/completions", status_code=status_code, content=body)
    return SDKError("API error occurred", response, body)


def _as_botocore_raises_it(*, status_code: int, error_code: str, message: str) -> BaseException:
    """Build the ``ClientError`` botocore raises from Bedrock's parsed answer to ``Converse``."""
    error_response: dict[str, Any] = {
        "Error": {"Code": error_code, "Message": message},
        "ResponseMetadata": {"RequestId": "req-bedrock-1", "HTTPStatusCode": status_code, "HTTPHeaders": {}},
    }
    return ClientError(error_response=cast("Any", error_response), operation_name="Converse")


def _assert_classified(*, metadata: ProviderErrorMetadata, family: InferenceErrorFamily, expected_error_code: ErrorCode) -> ClassificationResult:
    """Classify the metadata and assert the verdict the code implies: a spent quota or a rate limit, or neither."""
    classification = classify_inference_error(metadata, family=family)
    assert classification.error_code == expected_error_code
    match expected_error_code:
        case CoreCode.PROVIDER_QUOTA_EXHAUSTED:
            assert metadata.is_quota_exhaustion is True
            assert metadata.is_rate_limit is False
            assert classification.category == InferenceErrorCategory.CAPACITY
            assert classification.user_action_kind == UserActionKind.CHECK_BILLING
        case CoreCode.PROVIDER_RATE_LIMITED:
            assert metadata.is_quota_exhaustion is False
            assert metadata.is_rate_limit is True
            assert classification.category == InferenceErrorCategory.TRANSIENT
            assert classification.category.is_retryable is True
            assert classification.user_action_kind == UserActionKind.WAIT_AND_RETRY
        case CoreCode() | PipelexErrorCode():
            assert metadata.is_quota_exhaustion is False
            assert metadata.is_rate_limit is False
    return classification


class TestDirectProviderQuotaClassification:
    @pytest.mark.parametrize(
        ("_topic", "status_code", "body", "headers", "expected_error_code", "expected_retry_after"),
        [
            ("long_standing_insufficient_quota", 429, _TestData.OPENAI_INSUFFICIENT_QUOTA_BODY, None, CoreCode.PROVIDER_QUOTA_EXHAUSTED, None),
            # The billing code is in `code` beside the broad `type`, which the Extract step keeps: the rule reads both
            (
                "billing_code_beside_the_broad_type",
                429,
                _TestData.OPENAI_CREDIT_BALANCE_EXHAUSTED_BODY,
                None,
                CoreCode.PROVIDER_QUOTA_EXHAUSTED,
                None,
            ),
            ("billing_code_with_no_type", 429, _TestData.OPENAI_PROJECT_SPEND_LIMIT_NO_TYPE_BODY, None, CoreCode.PROVIDER_QUOTA_EXHAUSTED, None),
            ("per_minute_rate_limit", 429, _TestData.OPENAI_RATE_LIMIT_BODY, {"retry-after": "2"}, CoreCode.PROVIDER_RATE_LIMITED, 2),
            # The words say "exceeded your current quota", which the former word list read as a spent quota
            ("gemini_throttle_wording_with_no_code", 429, _TestData.OPENAI_DIALECT_GEMINI_THROTTLE_BODY, None, CoreCode.PROVIDER_RATE_LIMITED, None),
            (
                "openrouter_in_flight_budget_with_its_wait",
                402,
                _TestData.OPENROUTER_IN_FLIGHT_BUDGET_BODY,
                {"retry-after": _TestData.OPENROUTER_RETRY_AFTER},
                CoreCode.PROVIDER_RATE_LIMITED,
                2,
            ),
            # OpenRouter: "A 402 without the header is not a wait-and-retry case"
            (
                "openrouter_in_flight_budget_with_no_wait",
                402,
                _TestData.OPENROUTER_IN_FLIGHT_BUDGET_BODY,
                None,
                CoreCode.PROVIDER_QUOTA_EXHAUSTED,
                None,
            ),
            (
                "openrouter_insufficient_credits",
                402,
                _TestData.OPENROUTER_INSUFFICIENT_CREDITS_BODY,
                {"retry-after": _TestData.OPENROUTER_RETRY_AFTER},
                CoreCode.PROVIDER_QUOTA_EXHAUSTED,
                2,
            ),
            # Groq's own status for its flex tier at capacity, which it says to retry with backoff
            ("groq_flex_capacity_498", 498, _TestData.GROQ_FLEX_CAPACITY_BODY, None, CoreCode.PROVIDER_RATE_LIMITED, None),
            # Azure OpenAI's throttle, its delay read from the milliseconds before the rounded seconds
            (
                "azure_throttle_with_its_delay_in_milliseconds",
                429,
                _TestData.OPENAI_RATE_LIMIT_BODY,
                _TestData.AZURE_RETRY_AFTER_HEADERS,
                CoreCode.PROVIDER_RATE_LIMITED,
                _TestData.AZURE_RETRY_AFTER_MS_SECONDS,
            ),
        ],
    )
    def test_openai_dialect(
        self,
        _topic: str,
        status_code: int,
        body: dict[str, Any],
        headers: dict[str, str] | None,
        expected_error_code: ErrorCode,
        expected_retry_after: float | None,
    ) -> None:
        """An OpenAI-dialect 429 is a spent quota on one of OpenAI's billing codes or types alone; a 402 is one unless OpenRouter says it waits."""
        metadata = extract_openai_metadata(_as_openai_raises_it(status_code=status_code, body=body, headers=headers))

        _assert_classified(metadata=metadata, family=InferenceErrorFamily.LLM, expected_error_code=expected_error_code)
        assert metadata.retry_after_seconds == expected_retry_after

    @pytest.mark.parametrize(
        ("_topic", "status_code", "body", "expected_error_code"),
        [
            ("monthly_spend_cap_429", 429, _TestData.ANTHROPIC_SPEND_CAP_BODY, CoreCode.PROVIDER_QUOTA_EXHAUSTED),
            ("billing_error_402", 402, _TestData.ANTHROPIC_BILLING_ERROR_BODY, CoreCode.PROVIDER_QUOTA_EXHAUSTED),
            ("credit_balance_400", 400, _TestData.ANTHROPIC_CREDIT_BALANCE_BODY, CoreCode.PROVIDER_QUOTA_EXHAUSTED),
            ("self_set_spend_limit_400", 400, _TestData.ANTHROPIC_SELF_SET_LIMIT_BODY, CoreCode.PROVIDER_QUOTA_EXHAUSTED),
            ("workspace_spend_limit_400", 400, _TestData.ANTHROPIC_WORKSPACE_LIMIT_BODY, CoreCode.PROVIDER_QUOTA_EXHAUSTED),
            ("per_minute_rate_limit_429", 429, _TestData.ANTHROPIC_RATE_LIMIT_BODY, CoreCode.PROVIDER_RATE_LIMITED),
            ("malformed_request_400", 400, _TestData.ANTHROPIC_INVALID_REQUEST_BODY, CoreCode.RUNTIME_UNEXPECTED),
            # The credit sentence decides a 400 `invalid_request_error` alone: on a 403 it is a credential refusal
            ("credit_sentence_on_a_403", 403, _TestData.ANTHROPIC_CREDIT_BALANCE_BODY, CoreCode.PROVIDER_CREDENTIAL_REFUSED),
        ],
    )
    def test_anthropic(self, _topic: str, status_code: int, body: dict[str, Any], expected_error_code: ErrorCode) -> None:
        """Anthropic's quota is its 402 or `billing_error`, its spend cap's code on a 429, or one of its spend sentences on a 400."""
        metadata = extract_anthropic_metadata(_as_anthropic_raises_it(status_code=status_code, body=body))

        _assert_classified(metadata=metadata, family=InferenceErrorFamily.LLM, expected_error_code=expected_error_code)

    def test_anthropic_rate_limit_carries_its_wait(self) -> None:
        """A plain Anthropic 429 is a rate limit, and its `retry-after` reaches the metadata."""
        exc = _as_anthropic_raises_it(status_code=429, body=_TestData.ANTHROPIC_RATE_LIMIT_BODY, headers={"retry-after": "12"})

        metadata = extract_anthropic_metadata(exc)

        _assert_classified(metadata=metadata, family=InferenceErrorFamily.LLM, expected_error_code=CoreCode.PROVIDER_RATE_LIMITED)
        assert metadata.retry_after_seconds == 12

    def test_google_per_minute_throttle_is_a_rate_limit_waited_for_the_delay_it_asks(self) -> None:
        """Gemini's throttle, verbatim, is a rate limit whatever its words, and its `RetryInfo` wait reaches the problem."""
        exc = _as_google_raises_it(status_code=429, body=_TestData.GOOGLE_PER_MINUTE_THROTTLE_BODY)

        metadata = extract_google_metadata(exc)
        classification = _assert_classified(metadata=metadata, family=InferenceErrorFamily.LLM, expected_error_code=CoreCode.PROVIDER_RATE_LIMITED)

        assert metadata.provider_error_code == "RESOURCE_EXHAUSTED"
        assert "quota" in metadata.message
        assert metadata.retry_after_seconds == _TestData.GOOGLE_RETRY_DELAY_SECONDS

        rendered = render_inference_error(
            metadata=metadata,
            classification=classification,
            family=InferenceErrorFamily.LLM,
            model_desc="gemini-2.5-flash → Model[gemini-2.5-flash]",
            model_handle="gemini-2.5-flash",
        )
        # As the worker's error enrichment does, which names the model and the backend the problem's sentence reads
        rendered.fill_model_and_provider("gemini-2.5-flash", backend_name="google")
        problem = rendered.to_problem(view=ProblemView.OPERATOR)

        assert problem.code == CoreCode.PROVIDER_RATE_LIMITED
        assert problem.is_retryable is True
        assert problem.retry_after == _TestData.GOOGLE_RETRY_DELAY_SECONDS

    def test_google_spent_prepay_balance_is_a_spent_quota(self) -> None:
        """Gemini answers a Prepay balance at zero with a 402, which its status alone makes a spent quota."""
        metadata = extract_google_metadata(_as_google_raises_it(status_code=402, body=_TestData.GOOGLE_PREPAY_DEPLETED_BODY))

        _assert_classified(metadata=metadata, family=InferenceErrorFamily.LLM, expected_error_code=CoreCode.PROVIDER_QUOTA_EXHAUSTED)
        assert metadata.retry_after_seconds is None

    @pytest.mark.parametrize(
        ("_topic", "status_code", "body", "expected_error_code"),
        [
            ("capacity_429", 429, _TestData.MISTRAL_CAPACITY_BODY, CoreCode.PROVIDER_RATE_LIMITED),
            # The words name a quota, which the former word list read as a spent one
            ("quota_wording_429", 429, _TestData.MISTRAL_QUOTA_WORDING_BODY, CoreCode.PROVIDER_RATE_LIMITED),
            ("balance_depleted_402", 402, _TestData.MISTRAL_BALANCE_DEPLETED_BODY, CoreCode.PROVIDER_QUOTA_EXHAUSTED),
        ],
    )
    def test_mistral(self, _topic: str, status_code: int, body: str, expected_error_code: ErrorCode) -> None:
        """Mistral's spent balance is its 402, and every 429 is a rate limit."""
        metadata = extract_mistral_metadata(_as_mistral_raises_it(status_code=status_code, body=body))

        _assert_classified(metadata=metadata, family=InferenceErrorFamily.LLM, expected_error_code=expected_error_code)

    @pytest.mark.parametrize(
        ("_topic", "status_code", "error_code", "message", "expected_error_code"),
        [
            ("daily_tokens_throttle", 429, "ThrottlingException", _TestData.BEDROCK_DAILY_TOKENS_THROTTLE_MESSAGE, CoreCode.PROVIDER_RATE_LIMITED),
            # AWS documents it as resubmittable later, so it is a throttle on its 400
            ("service_quota_exceeded", 400, "ServiceQuotaExceededException", _TestData.BEDROCK_SERVICE_QUOTA_MESSAGE, CoreCode.PROVIDER_RATE_LIMITED),
            # An input over the model's window, which Bedrock words per model and signals no other way
            ("nova_input_overflow", 400, "ValidationException", _TestData.BEDROCK_NOVA_INPUT_OVERFLOW_MESSAGE, CoreCode.MODEL_CONTEXT_EXCEEDED),
            ("titan_input_overflow", 400, "ValidationException", _TestData.BEDROCK_TITAN_INPUT_OVERFLOW_MESSAGE, CoreCode.MODEL_CONTEXT_EXCEEDED),
            (
                "openai_engine_input_overflow",
                400,
                "ValidationException",
                _TestData.BEDROCK_OPENAI_ENGINE_INPUT_OVERFLOW_MESSAGE,
                CoreCode.MODEL_CONTEXT_EXCEEDED,
            ),
        ],
    )
    def test_bedrock(self, _topic: str, status_code: int, error_code: str, message: str, expected_error_code: ErrorCode) -> None:
        """Bedrock has no balance to spend, so none of its answers is a spent quota."""
        metadata = extract_bedrock_metadata(_as_botocore_raises_it(status_code=status_code, error_code=error_code, message=message))

        _assert_classified(metadata=metadata, family=InferenceErrorFamily.LLM, expected_error_code=expected_error_code)

    @pytest.mark.parametrize(
        ("_topic", "status_code", "error_type_header", "message", "expected_error_code", "expected_provider_error_code"),
        [
            # AWS documents it as resubmittable later: a throttle on its 400, read as the Bedrock worker reads it
            (
                "service_quota_exceeded",
                400,
                _TestData.BEDROCK_SERVICE_QUOTA_ERROR_TYPE_HEADER,
                _TestData.BEDROCK_SERVICE_QUOTA_MESSAGE,
                CoreCode.PROVIDER_RATE_LIMITED,
                "ServiceQuotaExceededException",
            ),
            (
                "throttling",
                429,
                _TestData.BEDROCK_THROTTLING_ERROR_TYPE_HEADER,
                _TestData.BEDROCK_DAILY_TOKENS_THROTTLE_MESSAGE,
                CoreCode.PROVIDER_RATE_LIMITED,
                "ThrottlingException",
            ),
        ],
    )
    def test_claude_on_bedrock(
        self,
        _topic: str,
        status_code: int,
        error_type_header: str,
        message: str,
        expected_error_code: ErrorCode,
        expected_provider_error_code: str,
    ) -> None:
        """Claude on Bedrock, through the Anthropic SDK, carries Bedrock's error code in a header, read as on Bedrock."""
        response = _response(
            url="https://bedrock-runtime.us-east-1.amazonaws.com/model/anthropic.claude-sonnet-4-5/invoke",
            status_code=status_code,
            content=json.dumps({"message": message}),
            headers={"x-amzn-errortype": error_type_header},
        )
        client = AnthropicBedrock(aws_region="us-east-1", api_key="unused-in-this-test")
        exc = client._make_status_error_from_response(response)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        metadata = extract_anthropic_metadata(exc)

        assert metadata.provider_error_code == expected_provider_error_code
        _assert_classified(metadata=metadata, family=InferenceErrorFamily.LLM, expected_error_code=expected_error_code)

    def test_azure_rest_reads_the_delay_in_milliseconds(self) -> None:
        """Azure OpenAI's REST answer, which no SDK wraps, carries its delay in milliseconds before its rounded seconds."""
        response = _response(
            url="https://test.openai.azure.com/openai/deployments/gpt-image-1/images/generations",
            status_code=429,
            content=json.dumps({"error": {"code": "429", "message": "Requests to the deployment have exceeded the rate limit."}}),
            headers=_TestData.AZURE_RETRY_AFTER_HEADERS,
        )
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            response.raise_for_status()

        metadata = extract_azure_metadata(exc_info.value)

        assert metadata.retry_after_seconds == _TestData.AZURE_RETRY_AFTER_MS_SECONDS
        _assert_classified(metadata=metadata, family=InferenceErrorFamily.IMG_GEN, expected_error_code=CoreCode.PROVIDER_RATE_LIMITED)
