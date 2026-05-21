"""Unit tests for ``ErrorReport.to_dict(disclosure_mode=...)`` — strict vs verbose projection.

``DisclosureMode.VERBOSE`` is the exact inverse of ``from_dict`` (round-trip preserved).
``DisclosureMode.STRICT`` is a *classification-projection for server-side errors*:
INPUT-domain reports pass through unchanged (caller-influenced); CONFIG / RUNTIME
reports drop ``user_action`` / ``model`` / ``provider`` / ``provider_metadata`` and
replace ``message`` with a generic placeholder while keeping the stable identifiers
(``error_type`` / ``error_domain`` / ``error_category`` / ``retryable`` /
``title`` / ``type_uri``).
"""

from typing import Any

import pytest

from pipelex.base_exceptions import INTERNAL_ERROR_PLACEHOLDER, DisclosureMode, ErrorDomain, ErrorReport
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserAction, UserActionKind
from pipelex.cogt.inference.provider_name import ProviderName


def _runtime_report(message: str = "rate limited on the worker") -> ErrorReport:
    return ErrorReport(
        error_type="CogtError",
        message=message,
        title="AI inference failed",
        type_uri="https://pipelex.dev/errors/cogt-error",
        error_category="capacity",
        error_domain=ErrorDomain.RUNTIME,
        retryable=False,
        user_action=UserAction(kind=UserActionKind.CHECK_BILLING, detail="check your billing page"),
        model="gpt-5",
        provider="openai",
        provider_metadata=ProviderErrorMetadata(
            provider=ProviderName.OPENAI,
            sdk_exception_type="RateLimitError",
            status_code=429,
            retry_after_seconds=12.0,
        ),
    )


def _config_report(message: str = "OPENAI_API_KEY is not set") -> ErrorReport:
    return ErrorReport(
        error_type="EnvVarNotFoundError",
        message=message,
        title="Environment variable not set",
        type_uri="https://pipelex.dev/errors/env-var-not-found-error",
        error_domain=ErrorDomain.CONFIG,
    )


def _input_report(message: str = "JSON payload at /Users/alice/secret.mthds is malformed") -> ErrorReport:
    return ErrorReport(
        error_type="PipelexConfigError",
        message=message,
        title="Pipelex error",
        type_uri="https://pipelex.dev/errors/pipelex-config-error",
        error_domain=ErrorDomain.INPUT,
    )


class TestErrorReportDisclosureMode:
    @pytest.mark.parametrize(
        ("report", "mode"),
        [
            pytest.param(_runtime_report(), DisclosureMode.VERBOSE, id="runtime-verbose"),
            pytest.param(_config_report(), DisclosureMode.VERBOSE, id="config-verbose"),
            pytest.param(_input_report(), DisclosureMode.VERBOSE, id="input-verbose"),
            pytest.param(_input_report(), DisclosureMode.STRICT, id="input-strict-passthrough"),
        ],
    )
    def test_passthrough_modes_preserve_message_and_classification(self, report: ErrorReport, mode: DisclosureMode) -> None:
        """VERBOSE preserves every populated field; STRICT preserves INPUT-domain reports unchanged."""
        payload = report.to_dict(disclosure_mode=mode)
        assert payload["message"] == report.message
        if report.user_action is not None:
            assert "user_action" in payload
        if report.model is not None:
            assert payload["model"] == report.model
        if report.provider is not None:
            assert payload["provider"] == report.provider

    @pytest.mark.parametrize(
        "report",
        [
            pytest.param(_runtime_report(), id="runtime-strict"),
            pytest.param(_config_report(), id="config-strict"),
        ],
    )
    def test_strict_redaction_drops_sensitive_fields(self, report: ErrorReport) -> None:
        """STRICT for CONFIG / RUNTIME replaces ``message`` and drops the disclosure-leaking fields."""
        payload = report.to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert payload["message"] == INTERNAL_ERROR_PLACEHOLDER
        assert "user_action" not in payload
        assert "model" not in payload
        assert "provider" not in payload
        assert "provider_metadata" not in payload
        # Stable identifiers are kept.
        assert payload["error_type"] == report.error_type
        assert payload["title"] == report.title
        assert payload["type_uri"] == report.type_uri
        if report.error_domain is not None:
            assert payload["error_domain"] == report.error_domain
        if report.error_category is not None:
            assert payload["error_category"] == report.error_category

    def test_input_strict_keeps_caller_influenced_path_in_message(self) -> None:
        """INPUT-strict pin: an INPUT message containing a server-side path passes through unchanged.

        STRICT is a classification-projection, NOT a path-leak shield — the contract
        is that INPUT-domain ``message`` text reflects back to the caller as-is. If
        that message could surface a secret, the fix is to repair the upstream
        message, not to expand STRICT mode's scope.
        """
        report = _input_report("JSON payload at /Users/alice/secret.mthds is malformed")
        payload = report.to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert payload["message"] == "JSON payload at /Users/alice/secret.mthds is malformed"

    @pytest.mark.parametrize(
        "retryable",
        [
            pytest.param(True, id="retryable-true"),
            pytest.param(False, id="retryable-false"),
            pytest.param(None, id="retryable-none"),
        ],
    )
    @pytest.mark.parametrize(
        "mode",
        [
            pytest.param(DisclosureMode.VERBOSE, id="verbose"),
            pytest.param(DisclosureMode.STRICT, id="strict"),
        ],
    )
    def test_retryable_survives_disclosure_mode(self, retryable: bool | None, mode: DisclosureMode) -> None:
        """``retryable`` is a stable identifier — kept in both modes for True / False / None."""
        report = ErrorReport(
            error_type="CogtError",
            message="boom",
            title="AI inference failed",
            type_uri="https://pipelex.dev/errors/cogt-error",
            error_domain=ErrorDomain.RUNTIME,
            retryable=retryable,
        )
        payload = report.to_dict(disclosure_mode=mode)
        if retryable is None:
            assert "retryable" not in payload
        else:
            assert payload["retryable"] is retryable

    def test_verbose_round_trip_preserves_report(self) -> None:
        """``from_dict(to_dict(VERBOSE))`` reconstructs the original report exactly."""
        report = _runtime_report()
        recovered = ErrorReport.from_dict(report.to_dict(disclosure_mode=DisclosureMode.VERBOSE))
        assert recovered == report

    def test_strict_does_not_round_trip(self) -> None:
        """``from_dict(to_dict(STRICT))`` for a RUNTIME report loses ``provider`` and rewrites ``message``."""
        report = _runtime_report()
        recovered = ErrorReport.from_dict(report.to_dict(disclosure_mode=DisclosureMode.STRICT))
        assert recovered.message == INTERNAL_ERROR_PLACEHOLDER
        assert recovered.provider is None
        assert recovered.user_action is None

    def test_to_dict_defaults_to_verbose(self) -> None:
        """No argument == VERBOSE — the safe default for in-process / round-trip callers."""
        report = _runtime_report()
        assert report.to_dict() == report.to_dict(disclosure_mode=DisclosureMode.VERBOSE)

    def test_receiver_rehydrates_verbose_payload_for_webhook(self) -> None:
        """An API-side receiver rebuilds the report from a VERBOSE webhook payload.

        Pins the contract pipelex-api consumes on the delivery webhook: the
        runner serializes a report into ``payload["error"]`` using
        ``to_dict(VERBOSE)`` and the receiver round-trips it back through
        ``ErrorReport.from_dict``.
        """
        report = _runtime_report()
        envelope: dict[str, Any] = {"status": "failed", "error": report.to_dict(disclosure_mode=DisclosureMode.VERBOSE)}
        recovered = ErrorReport.from_dict(envelope["error"])
        assert recovered == report
