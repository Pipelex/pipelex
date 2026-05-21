"""Unit tests for ``ErrorReport.from_dict`` — the strict inverse of ``to_dict``.

``from_dict`` rebuilds an ``ErrorReport`` from a serialized payload (e.g. a
Temporal ``ApplicationError.details`` dict) so it re-enters the
``to_error_report()`` world. It must round-trip ``to_dict`` exactly — nested
``UserAction`` / ``ProviderErrorMetadata`` included — and stay strict, raising
``ValidationError`` on a malformed or schema-drifted dict.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.base_exceptions import ErrorDomain, ErrorReport
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserAction, UserActionKind
from pipelex.cogt.inference.provider_name import ProviderName


class TestErrorReportFromDict:
    @pytest.mark.parametrize(
        "report",
        [
            pytest.param(
                ErrorReport(
                    error_type="X",
                    message="m",
                    title="X error",
                    type_uri="https://pipelex.dev/errors/x",
                ),
                id="minimal",
            ),
            pytest.param(
                ErrorReport(
                    error_type="CogtError",
                    message="rate limited",
                    title="AI inference failed",
                    type_uri="https://pipelex.dev/errors/cogt-error",
                    error_category="capacity",
                    error_domain=ErrorDomain.RUNTIME,
                    retryable=False,
                    user_action=UserAction(kind=UserActionKind.CHECK_BILLING, detail="check your billing page"),
                    model="gpt-5",
                    provider="openai",
                ),
                id="full-with-user-action",
            ),
            pytest.param(
                ErrorReport(
                    error_type="LLMCompletionError",
                    message="429 Too Many Requests",
                    title="LLM completion",
                    type_uri="https://pipelex.dev/errors/llm-completion-error",
                    error_category="capacity",
                    retryable=True,
                    provider_metadata=ProviderErrorMetadata(
                        provider=ProviderName.OPENAI,
                        sdk_exception_type="RateLimitError",
                        status_code=429,
                        retry_after_seconds=12.0,
                    ),
                ),
                id="provider-metadata-429",
            ),
        ],
    )
    def test_from_dict_round_trips_to_dict(self, report: ErrorReport) -> None:
        """``from_dict`` is the exact inverse of ``to_dict``, nested models included."""
        recovered = ErrorReport.from_dict(report.to_dict())
        assert recovered == report
        # The 429 passthrough must survive so HTTP adapters keep the right status.
        assert recovered.http_status == report.http_status

    @pytest.mark.parametrize(
        "bad_data",
        [
            pytest.param(
                {"message": "missing error_type", "title": "t", "type_uri": "u"},
                id="missing-required-error-type",
            ),
            pytest.param(
                {"error_type": "X", "title": "t", "type_uri": "u"},
                id="missing-required-message",
            ),
            pytest.param(
                {"error_type": "X", "message": "m", "type_uri": "u"},
                id="missing-required-title",
            ),
            pytest.param(
                {"error_type": "X", "message": "m", "title": "t"},
                id="missing-required-type-uri",
            ),
            pytest.param(
                {
                    "error_type": "X",
                    "message": "m",
                    "title": "t",
                    "type_uri": "u",
                    "surprise": "extra",
                },
                id="extra-forbidden-key",
            ),
            pytest.param(
                {
                    "error_type": "X",
                    "message": "m",
                    "title": "t",
                    "type_uri": "u",
                    "retryable": ["not", "a", "bool"],
                },
                id="wrong-field-type",
            ),
        ],
    )
    def test_g1_from_dict_raises_on_malformed_dict(self, bad_data: dict[str, Any]) -> None:
        """G1 — ``from_dict`` is strict: a malformed / schema-drifted dict raises ``ValidationError``."""
        with pytest.raises(ValidationError):
            ErrorReport.from_dict(bad_data)
