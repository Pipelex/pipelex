"""Unit tests for the RFC 7807 type-URI and title helpers."""

import pytest

from api.error_uri import error_type_title, error_type_uri


class TestErrorUri:
    @pytest.mark.parametrize(
        ("error_type", "expected"),
        [
            ("EnvVarNotFoundError", "https://docs.pipelex.com/latest/errors/env-var-not-found-error/"),
            ("ValidationError", "https://docs.pipelex.com/latest/errors/validation-error/"),
            ("PayloadTooLarge", "https://docs.pipelex.com/latest/errors/payload-too-large/"),
            ("InvalidJSON", "https://docs.pipelex.com/latest/errors/invalid-json/"),
            ("LLMCompletionError", "https://docs.pipelex.com/latest/errors/llm-completion-error/"),
        ],
    )
    def test_error_type_uri(self, error_type: str, expected: str):
        assert error_type_uri(error_type) == expected

    @pytest.mark.parametrize(
        ("error_type", "expected"),
        [
            ("EnvVarNotFoundError", "Env var not found error"),
            ("ValidationError", "Validation error"),
            ("PayloadTooLarge", "Payload too large"),
            ("BadRequest", "Bad request"),
            # A trailing acronym is preserved by pipelex's pascal_case_to_sentence
            # (`InvalidJSON` → `Invalid JSON`); pinned so the behavior is visible.
            ("InvalidJSON", "Invalid JSON"),
        ],
    )
    def test_error_type_title(self, error_type: str, expected: str):
        assert error_type_title(error_type) == expected
