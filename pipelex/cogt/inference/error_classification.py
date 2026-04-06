"""Helpers for classifying SDK errors into InferenceErrorCategory values.

Pure functions that inspect error messages to discriminate between
quota exhaustion vs rate limiting, and detect content policy violations.
"""

OPENAI_BILLING_URL = "https://platform.openai.com/account/billing"
ANTHROPIC_BILLING_URL = "https://console.anthropic.com/settings/billing"
GOOGLE_BILLING_URL = "https://console.cloud.google.com/billing"
MISTRAL_BILLING_URL = "https://console.mistral.ai/billing"
AWS_BILLING_URL = "https://console.aws.amazon.com/billing"
LINKUP_BILLING_URL = "https://app.linkup.so/billing"
FAL_BILLING_URL = "https://fal.ai/dashboard/billing"
HUGGINGFACE_BILLING_URL = "https://huggingface.co/settings/billing"
GATEWAY_BILLING_URL = "https://pipelex.com/billing"

_OPENAI_QUOTA_PATTERNS: tuple[str, ...] = (
    "insufficient_quota",
    "exceeded your current quota",
)

_ANTHROPIC_QUOTA_PATTERNS: tuple[str, ...] = (
    "quota",
    "billing limit",
    "billing issue",
)

_CONTENT_POLICY_PATTERNS: tuple[str, ...] = (
    "content_policy",
    "content_filter",
    "safety system",
    "safety filter",
    "blocked by safety",
)

_GOOGLE_QUOTA_PATTERNS: tuple[str, ...] = (
    "billing",
    "quota exceeded",
    "resource has been exhausted",
)

_MISTRAL_QUOTA_PATTERNS: tuple[str, ...] = (
    "quota",
    "billing",
    "credits",
)

_AWS_QUOTA_PATTERNS: tuple[str, ...] = (
    "quota",
    "limit exceeded",
    "service quota",
)

_GATEWAY_QUOTA_PATTERNS: tuple[str, ...] = (
    "quota",
    "billing",
    "insufficient",
    "credits exhausted",
)


def is_quota_exhaustion_openai(error_message: str) -> bool:
    """Check if an OpenAI error message indicates quota/credits exhaustion rather than rate limiting."""
    lower_message = error_message.lower()
    return any(pattern in lower_message for pattern in _OPENAI_QUOTA_PATTERNS)


def is_quota_exhaustion_anthropic(error_message: str) -> bool:
    """Check if an Anthropic error message indicates quota/credits exhaustion rather than rate limiting."""
    lower_message = error_message.lower()
    return any(pattern in lower_message for pattern in _ANTHROPIC_QUOTA_PATTERNS)


def is_quota_exhaustion_google(error_message: str) -> bool:
    """Check if a Google error message indicates quota/credits exhaustion rather than rate limiting."""
    lower_message = error_message.lower()
    return any(pattern in lower_message for pattern in _GOOGLE_QUOTA_PATTERNS)


def is_quota_exhaustion_mistral(error_message: str, status_code: int) -> bool:
    """Check if a Mistral error indicates quota/credits exhaustion.

    HTTP 402 (Payment Required) is a definitive quota signal.
    HTTP 429 requires message inspection to distinguish quota from rate limiting.
    """
    if status_code == 402:
        return True
    lower_message = error_message.lower()
    return status_code == 429 and any(pattern in lower_message for pattern in _MISTRAL_QUOTA_PATTERNS)


def is_quota_exhaustion_aws(error_message: str) -> bool:
    """Check if an AWS error message indicates quota/credits exhaustion rather than rate limiting."""
    lower_message = error_message.lower()
    return any(pattern in lower_message for pattern in _AWS_QUOTA_PATTERNS)


def is_quota_exhaustion_gateway(error_message: str, status_code: int) -> bool:
    """Check if a Portkey/Gateway error indicates quota/credits exhaustion.

    HTTP 402 (Payment Required) is a definitive quota signal.
    HTTP 429 requires message inspection to distinguish quota from rate limiting.
    """
    if status_code == 402:
        return True
    lower_message = error_message.lower()
    return status_code == 429 and any(pattern in lower_message for pattern in _GATEWAY_QUOTA_PATTERNS)


def is_content_policy_violation(error_message: str) -> bool:
    """Check if an error message indicates a content policy or safety filter violation."""
    lower_message = error_message.lower()
    return any(pattern in lower_message for pattern in _CONTENT_POLICY_PATTERNS)
