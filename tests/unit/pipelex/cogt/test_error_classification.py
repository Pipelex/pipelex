"""Tests for the error classification helpers used by inference workers."""

from typing import ClassVar

import pytest

from pipelex.cogt.inference.error_classification import (
    is_content_policy_violation,
    is_quota_exhaustion_anthropic,
    is_quota_exhaustion_openai,
)


class _TestCases:
    # (topic, error_message, expected_result)
    OPENAI_QUOTA_CASES: ClassVar[list[tuple[str, str, bool]]] = [
        ("insufficient_quota", "Error: insufficient_quota - you have exceeded your billing limit", True),
        ("exceeded_quota", "You exceeded your current quota, please check your plan", True),
        ("generic_rate_limit", "Rate limit exceeded. Please retry after 20s", False),
        ("empty_message", "", False),
        ("unrelated_error", "Invalid API key provided", False),
        ("case_insensitive", "Insufficient_Quota error occurred", True),
    ]

    ANTHROPIC_QUOTA_CASES: ClassVar[list[tuple[str, str, bool]]] = [
        ("quota_in_message", "Your account quota has been exceeded", True),
        ("billing_limit", "You have reached your billing limit", True),
        ("billing_issue", "There is a billing issue with your account", True),
        ("generic_rate_limit", "rate_limit_error: Number of request tokens has exceeded your per-minute limit", False),
        ("empty_message", "", False),
        ("unrelated_error", "Invalid API key", False),
        ("billing_word_alone_not_matched", "Please check your billing dashboard", False),
        ("case_insensitive", "Account Billing Issue detected", True),
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


class TestErrorClassification:
    """Tests for quota detection and content policy classification helpers."""

    @pytest.mark.parametrize(
        ("_topic", "error_message", "expected"),
        _TestCases.OPENAI_QUOTA_CASES,
    )
    def test_is_quota_exhaustion_openai(self, _topic: str, error_message: str, expected: bool) -> None:
        """Discriminate OpenAI quota exhaustion from generic rate limiting."""
        assert is_quota_exhaustion_openai(error_message) == expected

    @pytest.mark.parametrize(
        ("_topic", "error_message", "expected"),
        _TestCases.ANTHROPIC_QUOTA_CASES,
    )
    def test_is_quota_exhaustion_anthropic(self, _topic: str, error_message: str, expected: bool) -> None:
        """Discriminate Anthropic quota exhaustion from generic rate limiting."""
        assert is_quota_exhaustion_anthropic(error_message) == expected

    @pytest.mark.parametrize(
        ("_topic", "error_message", "expected"),
        _TestCases.CONTENT_POLICY_CASES,
    )
    def test_is_content_policy_violation(self, _topic: str, error_message: str, expected: bool) -> None:
        """Detect content policy and safety filter violations."""
        assert is_content_policy_violation(error_message) == expected
