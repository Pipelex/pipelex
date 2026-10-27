"""Tests for quota, rate-limit and content-policy detection on ``ProviderErrorMetadata``.

The probes are exposed via the ``ProviderErrorMetadata.limit_verdict`` /
``is_throttle_on_another_status`` / ``is_content_policy_violation`` properties; the
helpers backing them are module-private. These tests pin each
provider's quota rule, which reads the status and the provider's structured code or
type, never its message, except for Anthropic's spend sentences on a 400, and the
content-policy phrase matching.
"""

from typing import Any, ClassVar

import pytest

from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, ProviderLimitVerdict
from pipelex.cogt.inference.provider_name import ProviderName
from tests.unit.pipelex.cogt.test_data import DirectProviderQuotaTestData, GatewayThrottleTestData

_Bodies = DirectProviderQuotaTestData


def _metadata(
    provider: ProviderName,
    message: str,
    status_code: int | None = None,
    *,
    provider_error_code: str | None = None,
    body: Any | None = None,
    retry_after_seconds: float | None = None,
) -> ProviderErrorMetadata:
    return ProviderErrorMetadata(
        provider=provider,
        sdk_exception_type="RateLimitError",
        message=message,
        status_code=status_code,
        provider_error_code=provider_error_code,
        body=body,
        retry_after_seconds=retry_after_seconds,
    )


class _TestCases:
    # (topic, message, status_code, provider_error_code, body, expected_is_quota)
    # As the OpenAI client keeps it: `provider_error_code` is the type when there is one, the code otherwise, and the
    # body is the error section, which carries the code. A 429 is a quota on one of OpenAI's billing codes or types
    # alone, whatever its words; a 402 is a quota.
    OPENAI_QUOTA_CASES: ClassVar[list[tuple[str, str, int | None, str | None, Any, bool]]] = [
        (
            "insufficient_quota_type_and_code_429",
            GatewayThrottleTestData.OPENAI_QUOTA_MESSAGE,
            429,
            "insufficient_quota",
            _Bodies.OPENAI_INSUFFICIENT_QUOTA_BODY["error"],
            True,
        ),
        (
            "billing_code_beside_the_broad_type_429",
            "Your organization has no prepaid credits remaining.",
            429,
            "insufficient_quota",
            _Bodies.OPENAI_CREDIT_BALANCE_EXHAUSTED_BODY["error"],
            True,
        ),
        # The Extract step keeps the type, so the billing code is read from the body
        (
            "billing_code_beside_another_type_429",
            "Your organization reached its enforced spend limit.",
            429,
            "invalid_request_error",
            {
                "message": "Your organization reached its enforced spend limit.",
                "type": "invalid_request_error",
                "code": "organization_spend_limit_exceeded",
            },
            True,
        ),
        (
            "billing_code_with_no_type_429",
            "Your project reached its enforced spend limit.",
            429,
            "project_spend_limit_exceeded",
            _Bodies.OPENAI_PROJECT_SPEND_LIMIT_NO_TYPE_BODY["error"],
            True,
        ),
        (
            "usage_limit_code_429",
            "Your organization reached its OpenAI-assigned usage limit.",
            429,
            "organization_usage_limit_exceeded",
            {"code": "organization_usage_limit_exceeded"},
            True,
        ),
        ("payment_required_402", "Insufficient credits", 402, None, None, True),
        ("rate_limit_code_429", "Rate limit reached for gpt-4o", 429, "tokens", _Bodies.OPENAI_RATE_LIMIT_BODY["error"], False),
        ("slow_down_429", "Slow down", 429, "rate_limit_error", {"type": "rate_limit_error", "code": "slow_down"}, False),
        # Each message the former word list read as a quota, now a rate limit since no code says otherwise
        ("quota_wording_429_no_code", "You exceeded your current quota, please check your plan", 429, None, None, False),
        ("insufficient_quota_wording_429_no_code", "Error: insufficient_quota - you have exceeded your billing limit", 429, None, None, False),
        ("gemini_throttle_relayed_429", "You exceeded your current quota", 429, None, _Bodies.OPENAI_DIALECT_GEMINI_THROTTLE_BODY["error"], False),
        # The quota code decides a 429 only; on any other status the status ladder reads it
        ("quota_code_500_not_quota", "Internal server error", 500, "insufficient_quota", {"type": "insufficient_quota"}, False),
        ("no_status", "", None, None, None, False),
    ]

    # (topic, message, status_code, provider_error_code, body, expected_is_quota)
    # As the Anthropic client keeps it: `provider_error_code` is the error's type, and the body is the whole document.
    ANTHROPIC_QUOTA_CASES: ClassVar[list[tuple[str, str, int | None, str | None, Any, bool]]] = [
        ("billing_error_402", "Error code: 402", 402, "billing_error", _Bodies.ANTHROPIC_BILLING_ERROR_BODY, True),
        ("billing_error_type_on_another_status", "Error code: 400", 400, "billing_error", _Bodies.ANTHROPIC_BILLING_ERROR_BODY, True),
        ("payment_required_402_no_type", "Payment required", 402, None, None, True),
        ("spend_cap_code_429", "Error code: 429", 429, "rate_limit_error", _Bodies.ANTHROPIC_SPEND_CAP_BODY, True),
        ("credit_balance_400", "Error code: 400", 400, "invalid_request_error", _Bodies.ANTHROPIC_CREDIT_BALANCE_BODY, True),
        ("self_set_limit_400", "Error code: 400", 400, "invalid_request_error", _Bodies.ANTHROPIC_SELF_SET_LIMIT_BODY, True),
        ("workspace_limit_400", "Error code: 400", 400, "invalid_request_error", _Bodies.ANTHROPIC_WORKSPACE_LIMIT_BODY, True),
        ("rate_limit_429", "Error code: 429", 429, "rate_limit_error", _Bodies.ANTHROPIC_RATE_LIMIT_BODY, False),
        (
            "quota_wording_429_no_code",
            "Your account quota has been exceeded",
            429,
            "rate_limit_error",
            {"type": "error", "error": {"type": "rate_limit_error", "message": "Your account quota has been exceeded"}},
            False,
        ),
        ("malformed_request_400", "Error code: 400", 400, "invalid_request_error", _Bodies.ANTHROPIC_INVALID_REQUEST_BODY, False),
        # The spend sentences decide a 400 `invalid_request_error` alone, at the start of the body's message
        ("credit_sentence_on_a_403", "Error code: 403", 403, "invalid_request_error", _Bodies.ANTHROPIC_CREDIT_BALANCE_BODY, False),
        (
            "credit_sentence_on_another_type_400",
            "Error code: 400",
            400,
            "api_error",
            {"type": "error", "error": {"type": "api_error", "message": "Your credit balance is too low to access the Anthropic API."}},
            False,
        ),
        (
            "credit_sentence_not_at_the_start_400",
            "Error code: 400",
            400,
            "invalid_request_error",
            {"type": "error", "error": {"type": "invalid_request_error", "message": "messages.0: says your credit balance is too low"}},
            False,
        ),
        # The rendered message is not read: the sentence is the body's
        ("credit_sentence_in_the_message_alone_400", "Your credit balance is too low", 400, "invalid_request_error", None, False),
        ("no_status", "", None, None, None, False),
    ]

    # (topic, message, status_code, provider_error_code, expected_is_quota)
    # A 402 is a quota; every 429 RESOURCE_EXHAUSTED is a rate limit, whatever its message says.
    GOOGLE_QUOTA_CASES: ClassVar[list[tuple[str, str, int | None, str | None, bool]]] = [
        ("prepay_depleted_402", "402 None. Payment required.", 402, None, True),
        (
            "per_minute_throttle_429",
            _Bodies.GOOGLE_PER_MINUTE_THROTTLE_BODY["error"]["message"],
            429,
            "RESOURCE_EXHAUSTED",
            False,
        ),
        ("resource_exhausted_wording_429", "Resource has been exhausted (e.g. check quota)", 429, "RESOURCE_EXHAUSTED", False),
        ("billing_wording_429", "Billing quota exceeded for project foo", 429, "RESOURCE_EXHAUSTED", False),
        # The words decide nothing: a disabled billing account is read from its ErrorInfo reason, which a body carries
        ("billing_account_wording_403", "Billing account is not active", 403, "PERMISSION_DENIED", False),
        ("quota_wording_400", "Quota exceeded for aiplatform.googleapis.com", 400, "INVALID_ARGUMENT", False),
        ("no_status", "", None, None, False),
    ]

    # (topic, message, status_code, expected_is_quota)
    # A 402 is a quota; every 429 is a rate limit, the monthly token cap included, whatever its message says.
    MISTRAL_QUOTA_CASES: ClassVar[list[tuple[str, str, int, bool]]] = [
        ("payment_required_402", "Payment required", 402, True),
        ("payment_required_402_any_message", "anything at all", 402, True),
        ("quota_wording_429", "Quota exceeded for your account", 429, False),
        ("billing_wording_429", "Billing limit reached", 429, False),
        ("generic_rate_limit_429", "Rate limit exceeded. Please retry after 20s", 429, False),
        ("server_error_500", "Internal server error", 500, False),
        ("not_found_404", "Model not found", 404, False),
    ]

    # (topic, message, status_code, provider_error_code, expected_is_quota)
    # Bedrock is billed to the AWS account, with no balance to spend: none of its answers is a spent quota.
    BEDROCK_QUOTA_CASES: ClassVar[list[tuple[str, str, int, str | None, bool]]] = [
        ("daily_tokens_throttle_429", _Bodies.BEDROCK_DAILY_TOKENS_THROTTLE_MESSAGE, 429, "ThrottlingException", False),
        ("service_quota_exceeded_400", _Bodies.BEDROCK_SERVICE_QUOTA_MESSAGE, 400, "ServiceQuotaExceededException", False),
        ("input_overflow_validation_400", _Bodies.BEDROCK_NOVA_INPUT_OVERFLOW_MESSAGE, 400, "ValidationException", False),
        ("quota_wording_no_code_400", "Service quota exceeded for this account", 400, None, False),
    ]

    # (topic, provider, status_code, provider_error_code, body, retry_after_seconds, expected_is_throttle)
    THROTTLE_ON_ANOTHER_STATUS_CASES: ClassVar[list[tuple[str, ProviderName, int | None, str | None, Any, float | None, bool]]] = [
        # OpenRouter's in-flight budget, its error section as the OpenAI client keeps it, sent with its wait
        (
            "openrouter_in_flight_budget_with_its_wait",
            ProviderName.OPENAI,
            402,
            None,
            _Bodies.OPENROUTER_IN_FLIGHT_BUDGET_BODY["error"],
            2.0,
            True,
        ),
        (
            "openrouter_in_flight_budget_nested_with_its_wait",
            ProviderName.OPENAI,
            402,
            None,
            _Bodies.OPENROUTER_IN_FLIGHT_BUDGET_BODY,
            2.0,
            True,
        ),
        # The limit source decides; the header is the wait, not the verdict
        ("openrouter_in_flight_budget_with_no_wait", ProviderName.OPENAI, 402, None, _Bodies.OPENROUTER_IN_FLIGHT_BUDGET_BODY["error"], None, True),
        # The source is read in every section, past one whose metadata says something else
        (
            "openrouter_in_flight_budget_in_the_second_section",
            ProviderName.OPENAI,
            402,
            None,
            {"error": {"metadata": {"reason": "in_flight_budget_exhausted"}}, "metadata": {"limit_source": "openrouter_in_flight_budget"}},
            None,
            True,
        ),
        (
            "openrouter_insufficient_credits_with_a_wait",
            ProviderName.OPENAI,
            402,
            None,
            _Bodies.OPENROUTER_INSUFFICIENT_CREDITS_BODY["error"],
            2.0,
            False,
        ),
        ("openai_402_with_no_body", ProviderName.OPENAI, 402, None, None, 2.0, False),
        ("in_flight_budget_on_a_429", ProviderName.OPENAI, 429, None, _Bodies.OPENROUTER_IN_FLIGHT_BUDGET_BODY["error"], 2.0, False),
        # OpenRouter's structure from another provider says nothing
        ("in_flight_budget_from_anthropic", ProviderName.ANTHROPIC, 402, None, _Bodies.OPENROUTER_IN_FLIGHT_BUDGET_BODY, 2.0, False),
        ("bedrock_service_quota_exceeded", ProviderName.BEDROCK, 400, "ServiceQuotaExceededException", None, None, True),
        ("bedrock_throttling_is_a_plain_429", ProviderName.BEDROCK, 429, "ThrottlingException", None, None, False),
        # Claude on Bedrock, through the Anthropic SDK, carries Bedrock's code from its error-type header
        ("claude_on_bedrock_service_quota_exceeded", ProviderName.ANTHROPIC, 400, "ServiceQuotaExceededException", None, None, True),
        ("anthropic_invalid_request_is_no_throttle", ProviderName.ANTHROPIC, 400, "invalid_request_error", None, None, False),
        # Groq's flex tier at capacity, on its own status
        ("groq_flex_capacity_498", ProviderName.OPENAI, 498, None, _Bodies.GROQ_FLEX_CAPACITY_BODY["error"], None, True),
        ("a_498_from_another_dialect", ProviderName.MISTRAL, 498, None, None, None, False),
    ]

    CONTENT_POLICY_CASES: ClassVar[list[tuple[str, str, bool]]] = [
        ("content_policy", "Your request was rejected due to content_policy_violation", True),
        ("blocked_by_safety", "The response was blocked by safety systems", True),
        ("content_filter", "content_filter triggered for this request", True),
        ("safety_system", "Rejected by safety system", True),
        ("safety_filter", "Blocked by safety filter", True),
        ("generic_bad_request", "Invalid parameter: temperature must be between 0 and 2", False),
        ("empty_message", "", False),
        ("safety_word_alone_not_matched", "Please ensure thread safety when using this", False),
        ("case_insensitive", "Content_Policy violation detected", True),
    ]

    # (topic, message, status_code, provider_error_code, expected_is_quota)
    # A gateway's rule reads the status and the provider's code, never the message: a 402 is a quota whatever it says,
    # a 429 is a quota only on a documented quota code, and every other 429 is a rate limit, whatever its words.
    GATEWAY_QUOTA_CASES: ClassVar[list[tuple[str, str, int, str | None, bool]]] = [
        ("payment_required_402", "Payment required", 402, None, True),
        ("payment_required_402_any_message", "random text", 402, None, True),
        ("payment_required_402_any_code", "Payment required", 402, GatewayThrottleTestData.AZURE_RATE_LIMIT_CODE, True),
        ("openai_insufficient_quota_code_429", GatewayThrottleTestData.OPENAI_QUOTA_MESSAGE, 429, GatewayThrottleTestData.OPENAI_QUOTA_CODE, True),
        ("insufficient_quota_code_429_any_message", "random text", 429, GatewayThrottleTestData.OPENAI_QUOTA_CODE, True),
        # OpenAI's billing codes, each naming the cause of a spent quota in `error.code`
        (
            "openai_credit_balance_exhausted_code_429",
            "Credit balance exhausted",
            429,
            GatewayThrottleTestData.OPENAI_CREDIT_BALANCE_EXHAUSTED_CODE,
            True,
        ),
        ("openai_organization_spend_limit_code_429", "Organization spend limit reached", 429, "organization_spend_limit_exceeded", True),
        ("openai_project_spend_limit_code_429", "Project spend limit reached", 429, "project_spend_limit_exceeded", True),
        ("openai_organization_usage_limit_code_429", "Organization usage limit reached", 429, "organization_usage_limit_exceeded", True),
        (
            "azure_rate_limit_reached_429_linking_its_quota_increase_page",
            GatewayThrottleTestData.AZURE_RATE_LIMIT_MESSAGE,
            429,
            GatewayThrottleTestData.AZURE_RATE_LIMIT_CODE,
            False,
        ),
        ("azure_message_429_no_code", GatewayThrottleTestData.AZURE_RATE_LIMIT_MESSAGE, 429, None, False),
        ("generic_rate_limit_429_no_code", "Rate limit exceeded. Please retry", 429, None, False),
        # Each message the former word list read as a quota, now a rate limit since no code says otherwise
        ("quota_message_429_no_code", "Your quota has been exhausted", 429, None, False),
        ("billing_message_429_no_code", "Billing limit exceeded", 429, None, False),
        ("insufficient_credits_message_429_no_code", "Insufficient credits", 429, None, False),
        ("insufficient_quota_message_429_no_code", "insufficient_quota for this account", 429, None, False),
        ("insufficient_funds_message_429_no_code", "Insufficient funds in your account", 429, None, False),
        ("insufficient_balance_message_429_no_code", "Insufficient balance to complete request", 429, None, False),
        ("credits_exhausted_message_429_no_code", "Credits exhausted on this key", 429, None, False),
        # The quota code decides a 429 only; on any other status the status ladder reads it
        ("insufficient_quota_code_500_not_quota", "Internal server error", 500, GatewayThrottleTestData.OPENAI_QUOTA_CODE, False),
        ("server_error_500", "Internal server error", 500, None, False),
    ]


class TestErrorClassification:
    """Tests for quota, rate-limit and content-policy detection via the public ``ProviderErrorMetadata`` properties."""

    @pytest.mark.parametrize(
        ("_topic", "error_message", "status_code", "provider_error_code", "body", "expected"),
        _TestCases.OPENAI_QUOTA_CASES,
    )
    def test_is_quota_exhaustion_openai(
        self, _topic: str, error_message: str, status_code: int | None, provider_error_code: str | None, body: Any, expected: bool
    ) -> None:
        """Discriminate an OpenAI-dialect spent quota from a rate limit by the status and the error code or type alone."""
        metadata = _metadata(ProviderName.OPENAI, error_message, status_code, provider_error_code=provider_error_code, body=body)
        assert (metadata.limit_verdict is ProviderLimitVerdict.QUOTA_EXHAUSTED) == expected

    @pytest.mark.parametrize(
        ("_topic", "error_message", "status_code", "provider_error_code", "body", "expected"),
        _TestCases.ANTHROPIC_QUOTA_CASES,
    )
    def test_is_quota_exhaustion_anthropic(
        self, _topic: str, error_message: str, status_code: int | None, provider_error_code: str | None, body: Any, expected: bool
    ) -> None:
        """Discriminate an Anthropic spent quota or credit by its status, its type, its spend cap's code and its spend sentences on a 400."""
        metadata = _metadata(ProviderName.ANTHROPIC, error_message, status_code, provider_error_code=provider_error_code, body=body)
        assert (metadata.limit_verdict is ProviderLimitVerdict.QUOTA_EXHAUSTED) == expected

    @pytest.mark.parametrize(
        ("_topic", "error_message", "expected"),
        _TestCases.CONTENT_POLICY_CASES,
    )
    def test_is_content_policy_violation(self, _topic: str, error_message: str, expected: bool) -> None:
        """Detect content policy and safety filter violations (provider-agnostic)."""
        assert _metadata(ProviderName.OPENAI, error_message).is_content_policy_violation == expected

    @pytest.mark.parametrize(
        ("_topic", "error_message", "status_code", "provider_error_code", "expected"),
        _TestCases.GOOGLE_QUOTA_CASES,
    )
    def test_is_quota_exhaustion_google(
        self, _topic: str, error_message: str, status_code: int | None, provider_error_code: str | None, expected: bool
    ) -> None:
        """A Google spent quota is its 402 or a detail of its body; with no body, every 429 is a rate limit, whatever it says."""
        metadata = _metadata(ProviderName.GOOGLE, error_message, status_code, provider_error_code=provider_error_code)
        assert (metadata.limit_verdict is ProviderLimitVerdict.QUOTA_EXHAUSTED) == expected

    @pytest.mark.parametrize(
        ("_topic", "error_message", "status_code", "expected"),
        _TestCases.MISTRAL_QUOTA_CASES,
    )
    def test_is_quota_exhaustion_mistral(self, _topic: str, error_message: str, status_code: int, expected: bool) -> None:
        """A Mistral spent balance is its 402; every 429 is a rate limit, whatever it says."""
        assert (_metadata(ProviderName.MISTRAL, error_message, status_code).limit_verdict is ProviderLimitVerdict.QUOTA_EXHAUSTED) == expected

    @pytest.mark.parametrize(
        ("_topic", "error_message", "status_code", "provider_error_code", "expected"),
        _TestCases.BEDROCK_QUOTA_CASES,
    )
    def test_is_quota_exhaustion_bedrock(
        self, _topic: str, error_message: str, status_code: int, provider_error_code: str | None, expected: bool
    ) -> None:
        """No Bedrock answer is a spent quota, whatever its code or its words."""
        metadata = _metadata(ProviderName.BEDROCK, error_message, status_code, provider_error_code=provider_error_code)
        assert (metadata.limit_verdict is ProviderLimitVerdict.QUOTA_EXHAUSTED) == expected

    @pytest.mark.parametrize(
        ("_topic", "provider", "status_code", "provider_error_code", "body", "retry_after_seconds", "expected"),
        _TestCases.THROTTLE_ON_ANOTHER_STATUS_CASES,
    )
    def test_is_throttle_on_another_status(
        self,
        _topic: str,
        provider: ProviderName,
        status_code: int | None,
        provider_error_code: str | None,
        body: Any,
        retry_after_seconds: float | None,
        expected: bool,
    ) -> None:
        """A throttle a provider documents on another status than 429 is a rate limit, never a spent quota."""
        metadata = _metadata(
            provider,
            "Error",
            status_code,
            provider_error_code=provider_error_code,
            body=body,
            retry_after_seconds=retry_after_seconds,
        )
        assert metadata.is_throttle_on_another_status == expected
        if expected:
            assert metadata.limit_verdict is ProviderLimitVerdict.RATE_LIMITED

    @pytest.mark.parametrize(
        ("_topic", "error_message", "status_code", "provider_error_code", "expected"),
        _TestCases.GATEWAY_QUOTA_CASES,
    )
    def test_is_quota_exhaustion_gateway(
        self, _topic: str, error_message: str, status_code: int, provider_error_code: str | None, expected: bool
    ) -> None:
        """Discriminate Gateway quota exhaustion from rate limiting by the status and the provider's code alone."""
        metadata = _metadata(ProviderName.GATEWAY, error_message, status_code, provider_error_code=provider_error_code)
        assert (metadata.limit_verdict is ProviderLimitVerdict.QUOTA_EXHAUSTED) == expected

    @pytest.mark.parametrize(
        ("_topic", "provider", "status_code", "provider_error_code", "expected"),
        [
            ("openai_plain_429", ProviderName.OPENAI, 429, None, ProviderLimitVerdict.RATE_LIMITED),
            ("openai_quota_code_429", ProviderName.OPENAI, 429, "insufficient_quota", ProviderLimitVerdict.QUOTA_EXHAUSTED),
            ("google_resource_exhausted_429", ProviderName.GOOGLE, 429, "RESOURCE_EXHAUSTED", ProviderLimitVerdict.RATE_LIMITED),
            ("mistral_402", ProviderName.MISTRAL, 402, None, ProviderLimitVerdict.QUOTA_EXHAUSTED),
            ("bedrock_throttling_429", ProviderName.BEDROCK, 429, "ThrottlingException", ProviderLimitVerdict.RATE_LIMITED),
            ("anthropic_400", ProviderName.ANTHROPIC, 400, "invalid_request_error", ProviderLimitVerdict.NEITHER),
            ("no_status", ProviderName.OPENAI, None, None, ProviderLimitVerdict.NEITHER),
        ],
    )
    def test_limit_verdict(
        self,
        _topic: str,
        provider: ProviderName,
        status_code: int | None,
        provider_error_code: str | None,
        expected: ProviderLimitVerdict,
    ) -> None:
        """Every 429 with no spent-quota signal is a rate limit, and nothing else is unless its provider documents a throttle."""
        metadata = _metadata(provider, "Too many requests", status_code, provider_error_code=provider_error_code)
        assert metadata.limit_verdict is expected
