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


class DirectProviderQuotaTestData:
    """Error bodies of the providers Pipelex calls directly, each as the provider sends it over the wire.

    Each one is a real answer a user posted or a body the provider documents, with its source named; where neither
    exists, the comment says what the body was built from. They pin how each provider tells a spent quota from a rate
    limit: the status and the structured code or type, never the wording.
    """

    # OpenAI's long-standing spent-quota answer, on a 429, as users post it
    # (https://community.openai.com/t/429-insufficient-quota-when-enough-quota-and-credits-are-left/567740)
    OPENAI_INSUFFICIENT_QUOTA_BODY: ClassVar[dict[str, Any]] = {
        "error": {
            "message": (
                "You exceeded your current quota, please check your plan and billing details. For more information on "
                "this error, read the docs: https://platform.openai.com/docs/guides/error-codes/api-errors."
            ),
            "type": "insufficient_quota",
            "param": None,
            "code": "insufficient_quota",
        }
    }
    # OpenAI's billing 429s carry the cause in `error.code`, and the broad `insufficient_quota` can still be the type
    # (https://developers.openai.com/api/docs/guides/error-codes). The guide gives the codes and their descriptions, no
    # verbatim body, so these are built from them.
    OPENAI_CREDIT_BALANCE_EXHAUSTED_BODY: ClassVar[dict[str, Any]] = {
        "error": {
            "message": "Your organization has no prepaid credits remaining.",
            "type": "insufficient_quota",
            "param": None,
            "code": "credit_balance_exhausted",
        }
    }
    OPENAI_PROJECT_SPEND_LIMIT_NO_TYPE_BODY: ClassVar[dict[str, Any]] = {
        "error": {
            "message": "Your project reached its enforced spend limit.",
            "param": None,
            "code": "project_spend_limit_exceeded",
        }
    }
    # OpenAI's per-minute token limit, in the shape users post it, the organization's id replaced; the guide lists the
    # rate limit with no code, and this type and code are not in it
    OPENAI_RATE_LIMIT_BODY: ClassVar[dict[str, Any]] = {
        "error": {
            "message": (
                "Rate limit reached for gpt-4o in organization org-abc123 on tokens per min (TPM): Limit 30000, Used "
                "29000, Requested 2000. Please try again in 2s. Visit https://platform.openai.com/account/rate-limits "
                "to learn more."
            ),
            "type": "tokens",
            "param": None,
            "code": "rate_limit_exceeded",
        }
    }
    # Built from Gemini's per-minute throttle, whose words say "quota" and "billing", in Google's error shape, for an
    # OpenAI-dialect backend pointed at a Google endpoint: its `code` is the status, a number, and it carries no type
    OPENAI_DIALECT_GEMINI_THROTTLE_BODY: ClassVar[dict[str, Any]] = {
        "error": {
            "code": 429,
            "message": (
                "You exceeded your current quota, please check your plan and billing details. For more information on "
                "this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits."
            ),
            "status": "RESOURCE_EXHAUSTED",
        }
    }
    # OpenRouter's 402 for a request its in-flight spending budget cannot hold until the running requests settle, its
    # documented example with the remedy hint left out (https://openrouter.ai/docs/api_reference/limits.md)
    OPENROUTER_IN_FLIGHT_BUDGET_BODY: ClassVar[dict[str, Any]] = {
        "error": {
            "code": 402,
            "message": (
                "This request would exceed your available credits given your current in-flight requests. Retry after "
                "in-flight requests settle, or add credits."
            ),
            "metadata": {"reason": "in_flight_budget_exhausted", "limit_source": "openrouter_in_flight_budget"},
        }
    }
    # The wait OpenRouter sends with it in the `retry-after` header, as its documentation describes
    OPENROUTER_RETRY_AFTER: ClassVar[str] = "2"
    # OpenRouter's 402 for a balance that cannot cover the request, with its documented message and limit source
    # (https://openrouter.ai/docs/api-reference/errors)
    OPENROUTER_INSUFFICIENT_CREDITS_BODY: ClassVar[dict[str, Any]] = {
        "error": {
            "code": 402,
            "message": "Your account or API key has insufficient credits. Add more credits and retry the request.",
            "metadata": {"limit_source": "openrouter_credits"},
        }
    }

    # Anthropic's 429 for its tier's monthly spend cap, verbatim from its rate-limits page
    # (https://platform.claude.com/docs/en/api/rate-limits#reaching-your-spend-cap)
    ANTHROPIC_SPEND_CAP_BODY: ClassVar[dict[str, Any]] = {
        "type": "error",
        "error": {
            "type": "rate_limit_error",
            "message": (
                "You have reached your API usage limits: your organization has crossed its monthly API usage threshold, "
                "set based on your organization's API tier. You will regain access on 2026-09-01 at 00:00 UTC."
            ),
            "details": {"error_code": "enforced_spend_limit_reached"},
        },
        "request_id": "req_018EeWyXxfu5pfWkrYcMdjWG",
    }
    # Anthropic's 400 for a spent credit balance, verbatim from the SDK issue that confirms its status and type
    # (https://github.com/anthropics/anthropic-sdk-typescript/issues/618)
    ANTHROPIC_CREDIT_BALANCE_BODY: ClassVar[dict[str, Any]] = {
        "type": "error",
        "error": {
            "type": "invalid_request_error",
            "message": "Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.",
        },
        "request_id": "req_011Cf75wfCXCbniKKrP6wSut",
    }
    # Anthropic's 400 for a spend limit the organization or a workspace set itself. Its rate-limits page documents the
    # sentence's start and no verbatim body (https://platform.claude.com/docs/en/api/rate-limits#setting-your-own-spend-limit),
    # so these are built on it.
    ANTHROPIC_SELF_SET_LIMIT_BODY: ClassVar[dict[str, Any]] = {
        "type": "error",
        "error": {
            "type": "invalid_request_error",
            "message": "You have reached your specified API usage limits. You will regain access on 2026-11-01 at 00:00 UTC.",
        },
    }
    ANTHROPIC_WORKSPACE_LIMIT_BODY: ClassVar[dict[str, Any]] = {
        "type": "error",
        "error": {
            "type": "invalid_request_error",
            "message": "You have reached your specified workspace API usage limits. You will regain access on 2026-11-01 at 00:00 UTC.",
        },
    }
    # Anthropic's 402, with the description its errors reference gives `billing_error`
    # (https://platform.claude.com/docs/en/api/errors)
    ANTHROPIC_BILLING_ERROR_BODY: ClassVar[dict[str, Any]] = {
        "type": "error",
        "error": {"type": "billing_error", "message": "There's an issue with your billing or payment information."},
    }
    # Anthropic's per-minute token limit, in the shape users post it, the organization's id left out
    ANTHROPIC_RATE_LIMIT_BODY: ClassVar[dict[str, Any]] = {
        "type": "error",
        "error": {
            "type": "rate_limit_error",
            "message": (
                "This request would exceed the rate limit for your organization of 400,000 input tokens per minute. "
                "For details, refer to: https://docs.claude.com/en/api/rate-limits. You can see the response headers "
                "for current usage. Please reduce the prompt length or the maximum tokens requested, or try again later."
            ),
        },
    }
    # A malformed request, on the status and type the two spend refusals share
    ANTHROPIC_INVALID_REQUEST_BODY: ClassVar[dict[str, Any]] = {
        "type": "error",
        "error": {"type": "invalid_request_error", "message": "messages: text content blocks must be non-empty"},
    }

    # Gemini's per-minute throttle on a paid tier, verbatim as a user posted it
    # (https://discuss.ai.google.dev/t/you-exceeded-your-current-quota-please-check-your-plan-and-billing-details/109580):
    # its words say "quota" and "billing", and the wait it asks for is in the body's `google.rpc.RetryInfo`
    GOOGLE_PER_MINUTE_THROTTLE_BODY: ClassVar[dict[str, Any]] = {
        "error": {
            "code": 429,
            "message": (
                "You exceeded your current quota, please check your plan and billing details. For more information on "
                "this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, "
                "head to: https://ai.dev/usage?tab=rate-limit. \n* Quota exceeded for metric: "
                "generativelanguage.googleapis.com/generate_content_paid_tier_input_token_count, limit: 1000000, model: "
                "gemini-2.5-flash\nPlease retry in 33.470052706s."
            ),
            "status": "RESOURCE_EXHAUSTED",
            "details": [
                {
                    "@type": "type.googleapis.com/google.rpc.Help",
                    "links": [{"description": "Learn more about Gemini API quotas", "url": "https://ai.google.dev/gemini-api/docs/rate-limits"}],
                },
                {
                    "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                    "violations": [
                        {
                            "quotaMetric": "generativelanguage.googleapis.com/generate_content_paid_tier_input_token_count",
                            "quotaId": "GenerateContentPaidTierInputTokensPerModelPerMinute",
                            "quotaDimensions": {"location": "global", "model": "gemini-2.5-flash"},
                            "quotaValue": "1000000",
                        }
                    ],
                },
                {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "33s"},
            ],
        }
    }
    # The wait that throttle's `RetryInfo` asks for, in seconds
    GOOGLE_RETRY_DELAY_SECONDS: ClassVar[float] = 33.0
    # Gemini's 402 for a Prepay balance at zero, which its billing page documents with no body, so only the status is
    # Google's (https://ai.google.dev/gemini-api/docs/billing)
    GOOGLE_PREPAY_DEPLETED_BODY: ClassVar[dict[str, Any]] = {"error": {"code": 402, "message": "Payment required."}}

    # Mistral's capacity refusal on a 429, verbatim from a production log
    # (https://github.com/EOSC-Data-Commons/data-commons-search/issues/7)
    MISTRAL_CAPACITY_BODY: ClassVar[str] = (
        '{"object":"error","message":"Service tier capacity exceeded for this model.",'
        '"type":"service_tier_capacity_exceeded","param":null,"code":"3505"}'
    )
    # Built: a 429 whose words name a quota and which carries no type, as Mistral's monthly token cap may read, since no
    # verbatim body of it was found; a rate limit all the same
    MISTRAL_QUOTA_WORDING_BODY: ClassVar[str] = '{"object":"error","message":"Rate limit reached: your monthly token quota has been exceeded."}'
    # Mistral's 402 for a balance at zero, which its billing page documents with no body, so only the status is Mistral's
    # (https://docs.mistral.ai/admin/billing-usage/billing)
    MISTRAL_BALANCE_DEPLETED_BODY: ClassVar[str] = '{"object":"error","message":"Payment required."}'

    # Bedrock's throttle for an account whose daily token quota is spent, verbatim from AWS re:Post
    # (https://repost.aws/questions/QUt6wvrkLHQwq6yq52nVADvA/all-bedrock-model-quotas-stuck-at-0-tokens-day-cannot-make-any-api-calls)
    BEDROCK_DAILY_TOKENS_THROTTLE_MESSAGE: ClassVar[str] = "Too many tokens per day, please wait before trying again."
    # Built: a Bedrock validation refusal whose words name a limit, which the former word list read as a spent quota
    BEDROCK_INPUT_LIMIT_MESSAGE: ClassVar[str] = "Input token limit exceeded for this model."
    # Bedrock's service-quota refusal, with AWS's documented description
    # (https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_InvokeModel.html)
    BEDROCK_SERVICE_QUOTA_MESSAGE: ClassVar[str] = (
        "Your request exceeds the service quota for your account. You can view your quotas at Viewing service quotas. "
        "You can resubmit your request later."
    )
