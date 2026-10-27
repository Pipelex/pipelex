from typing import Any, ClassVar

from mthds.protocol.problem.registry import CoreCode, ProblemDomain

from pipelex.cogt.exceptions import InferenceErrorCategory
from pipelex.errors.error_codes import ErrorCode


class ExceptionTestData:
    # (topic, category, expected_is_retryable)
    CATEGORY_RETRYABLE_CASES: ClassVar[list[tuple[str, InferenceErrorCategory, bool]]] = [
        ("transient_is_retryable", InferenceErrorCategory.TRANSIENT, True),
        ("configuration_not_retryable", InferenceErrorCategory.CONFIGURATION, False),
        ("content_not_retryable", InferenceErrorCategory.CONTENT, False),
        ("capacity_not_retryable", InferenceErrorCategory.CAPACITY, False),
        ("ambiguous_not_retryable", InferenceErrorCategory.AMBIGUOUS, False),
    ]

    # (topic, category, expected_code, expected_domain, expected_retryable)
    # What a failure built by hand with a category and no code reports. Exhaustive over InferenceErrorCategory — the
    # exhaustiveness itself is asserted by ``test_category_code_cases_cover_every_category``, so a new category cannot
    # be added without deciding what such a failure reports.
    CATEGORY_CODE_CASES: ClassVar[list[tuple[str, InferenceErrorCategory, ErrorCode, ProblemDomain, bool]]] = [
        ("transient_invites_a_retry", InferenceErrorCategory.TRANSIENT, CoreCode.PROVIDER_UNAVAILABLE, ProblemDomain.RUNTIME, True),
        ("configuration_is_the_operator_s", InferenceErrorCategory.CONFIGURATION, CoreCode.RUNTIME_MISCONFIGURED, ProblemDomain.OPERATOR, False),
        ("content_keeps_the_fallback", InferenceErrorCategory.CONTENT, CoreCode.RUNTIME_UNEXPECTED, ProblemDomain.RUNTIME, False),
        ("capacity_is_the_quota", InferenceErrorCategory.CAPACITY, CoreCode.PROVIDER_QUOTA_EXHAUSTED, ProblemDomain.OPERATOR, False),
        ("ambiguous_is_an_unknown_outcome", InferenceErrorCategory.AMBIGUOUS, CoreCode.PROVIDER_OUTCOME_UNKNOWN, ProblemDomain.RUNTIME, True),
        ("unknown_keeps_the_fallback", InferenceErrorCategory.UNKNOWN, CoreCode.RUNTIME_UNEXPECTED, ProblemDomain.RUNTIME, False),
    ]


class GatewayThrottleTestData:
    # Azure OpenAI's refusal of a `gpt-image-2` call over its deployment's call rate, verbatim as a run on the hosted API
    # received it through the gateway, which prefixes the provider's message with the provider's name. Its code is
    # Azure's rate-limit code, and its last sentence links to Azure's quota-increase page, whose address holds the word
    # "quota": a rule reading the message for that word took this throttle for a spent quota.
    AZURE_RATE_LIMIT_MESSAGE: ClassVar[str] = (
        "azure-openai error: Your requests to gpt-image-2 for gpt-image-2 in East US 2 have exceeded the call rate limit "
        "for your current AIServices S0 pricing tier. This request was for ImageGenerations_Create under Azure OpenAI API "
        "version 2025-04-01-preview. Please retry after 57 seconds. To increase your default rate limit, visit: "
        "https://aka.ms/oai/quotaincrease."
    )
    AZURE_RATE_LIMIT_CODE: ClassVar[str] = "RateLimitReached"
    # The delay the gateway forwards from Azure in the `retry-after` header
    AZURE_RETRY_AFTER: ClassVar[str] = "57"
    # The whole body the gateway answered with, at HTTP 429
    AZURE_RATE_LIMIT_BODY: ClassVar[dict[str, Any]] = {
        "error": {
            "message": AZURE_RATE_LIMIT_MESSAGE,
            "type": None,
            "param": None,
            "code": AZURE_RATE_LIMIT_CODE,
        },
        "provider": "azure-openai",
    }

    # OpenAI's broad code for a spent quota on a 429, which Azure OpenAI and the OpenAI-compatible providers relay
    OPENAI_QUOTA_CODE: ClassVar[str] = "insufficient_quota"
    OPENAI_QUOTA_MESSAGE: ClassVar[str] = "You exceeded your current quota, please check your plan and billing details."
    # One of the billing codes OpenAI's error-code guide documents for a 429 in `error.code`, whose `error.type` can
    # still be `insufficient_quota`
    OPENAI_CREDIT_BALANCE_EXHAUSTED_CODE: ClassVar[str] = "credit_balance_exhausted"
