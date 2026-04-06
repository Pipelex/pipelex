"""Helpers for classifying SDK errors into InferenceErrorCategory values.

Pure functions that inspect error messages to discriminate between
quota exhaustion vs rate limiting, and detect content policy violations.
"""

OPENAI_BILLING_URL = "https://platform.openai.com/account/billing"
ANTHROPIC_BILLING_URL = "https://console.anthropic.com/settings/billing"

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


def is_quota_exhaustion_openai(error_message: str) -> bool:
    """Check if an OpenAI error message indicates quota/credits exhaustion rather than rate limiting."""
    lower_message = error_message.lower()
    return any(pattern in lower_message for pattern in _OPENAI_QUOTA_PATTERNS)


def is_quota_exhaustion_anthropic(error_message: str) -> bool:
    """Check if an Anthropic error message indicates quota/credits exhaustion rather than rate limiting."""
    lower_message = error_message.lower()
    return any(pattern in lower_message for pattern in _ANTHROPIC_QUOTA_PATTERNS)


def is_content_policy_violation(error_message: str) -> bool:
    """Check if an error message indicates a content policy or safety filter violation."""
    lower_message = error_message.lower()
    return any(pattern in lower_message for pattern in _CONTENT_POLICY_PATTERNS)
