"""Unit tests for ``ErrorReport.to_dict(disclosure_mode=...)`` — strict vs verbose projection.

``DisclosureMode.VERBOSE`` is the exact inverse of ``from_dict`` (round-trip preserved).
``DisclosureMode.STRICT`` is a lossy projection for untrusted external surfaces:
``provider`` / ``model`` / ``provider_metadata`` are always dropped, and the
``message`` is kept only when the report is flagged ``caller_facing_message`` —
the flag set by error classes (``PipelexInterpreterError`` / ``ValidateBundleError``)
whose message describes the caller's own input. Every other report has its
``message`` replaced with a generic placeholder and ``user_action`` dropped,
keeping the stable identifiers (``error_type`` / ``error_domain`` /
``error_category`` / ``retryable`` / ``title`` / ``type_uri``).

The flag is keyed on message *provenance*, not ``error_domain``: ``error_domain``
is inherited up the ``__cause__`` chain, so a domain-less wrapper raised ``from``
an INPUT cause is classified INPUT — but its own internal ``message`` must still
be redacted. ``caller_facing_message`` is not inherited, so STRICT redacts it.
"""

from typing import Any

import pytest

from pipelex.base_exceptions import (
    INTERNAL_ERROR_PLACEHOLDER,
    DisclosureMode,
    ErrorDomain,
    ErrorReport,
    PipelexUnexpectedError,
)
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserAction, UserActionKind
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.core.interpreter.exceptions import PipelexInterpreterError


def _runtime_report(message: str = "rate limited on the worker") -> ErrorReport:
    return ErrorReport(
        error_type="CogtError",
        message=message,
        title="AI inference failed",
        type_uri="https://docs.pipelex.com/latest/errors/cogt-error/",
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
        type_uri="https://docs.pipelex.com/latest/errors/env-var-not-found-error/",
        error_domain=ErrorDomain.CONFIG,
    )


def _caller_facing_report(message: str = "pipe 'summarize' references unknown concept 'Reportt' at line 14") -> ErrorReport:
    """A report whose message was authored as caller-facing copy (interpreter / bundle-validation)."""
    return ErrorReport(
        error_type="PipelexInterpreterError",
        message=message,
        title="Pipelex interpreter error",
        type_uri="https://docs.pipelex.com/latest/errors/pipelex-interpreter-error/",
        error_domain=ErrorDomain.INPUT,
        user_action=UserAction(kind=UserActionKind.CHANGE_INPUT, detail="fix the concept name in your .mthds"),
        caller_facing_message=True,
    )


def _input_domain_wrapper_report(message: str = "internal invariant violated: cache slot is None") -> ErrorReport:
    """An INPUT-classified report whose message is NOT caller-facing.

    Models a domain-less wrapper that inherited ``error_domain=INPUT`` up the
    ``__cause__`` chain while keeping its own internal ``message``.
    """
    return ErrorReport(
        error_type="PipelexUnexpectedError",
        message=message,
        title="Unexpected internal error",
        type_uri="https://docs.pipelex.com/latest/errors/pipelex-unexpected-error/",
        error_domain=ErrorDomain.INPUT,
    )


class TestErrorReportDisclosureMode:
    @pytest.mark.parametrize(
        "report",
        [
            pytest.param(_runtime_report(), id="runtime"),
            pytest.param(_config_report(), id="config"),
            pytest.param(_caller_facing_report(), id="caller-facing"),
            pytest.param(_input_domain_wrapper_report(), id="input-domain-wrapper"),
        ],
    )
    def test_verbose_preserves_every_populated_field(self, report: ErrorReport) -> None:
        """VERBOSE is a pure passthrough — ``message`` and every populated field survive."""
        payload = report.to_dict(disclosure_mode=DisclosureMode.VERBOSE)
        assert payload["message"] == report.message
        assert payload["error_type"] == report.error_type
        if report.user_action is not None:
            assert "user_action" in payload
        if report.model is not None:
            assert payload["model"] == report.model
        if report.provider is not None:
            assert payload["provider"] == report.provider

    @pytest.mark.parametrize(
        "report",
        [
            pytest.param(_runtime_report(), id="runtime"),
            pytest.param(_config_report(), id="config"),
            pytest.param(_input_domain_wrapper_report(), id="input-domain-wrapper"),
        ],
    )
    def test_strict_redacts_non_caller_facing_reports(self, report: ErrorReport) -> None:
        """STRICT replaces ``message`` and drops disclosure-leaking fields for any non-caller-facing report.

        The ``input-domain-wrapper`` case is the regression pin: ``error_domain``
        alone (here INPUT, inherited up a ``__cause__`` chain) does NOT earn a
        message passthrough — only the ``caller_facing_message`` flag does.
        """
        payload = report.to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert payload["message"] == INTERNAL_ERROR_PLACEHOLDER
        assert "user_action" not in payload
        assert "model" not in payload
        assert "provider" not in payload
        assert "provider_metadata" not in payload
        # Stable identifiers survive.
        assert payload["error_type"] == report.error_type
        assert payload["title"] == report.title
        assert payload["type_uri"] == report.type_uri
        if report.error_domain is not None:
            assert payload["error_domain"] == report.error_domain

    def test_strict_passes_through_caller_facing_message(self) -> None:
        """A report flagged ``caller_facing_message`` keeps its ``message`` and ``user_action`` in STRICT."""
        report = _caller_facing_report()
        payload = report.to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert payload["message"] == report.message
        assert "user_action" in payload
        assert payload["caller_facing_message"] is True

    def test_strict_strips_provider_fields_even_from_caller_facing_passthrough(self) -> None:
        """Gap 2: provider/model attribution is stripped from the caller-facing passthrough branch.

        An INPUT-classification error can pick up ``provider`` / ``model`` /
        ``provider_metadata`` from an inference-layer ``__cause__`` during
        enrichment. STRICT must never reflect that onto an external surface,
        even when the ``message`` itself is allowed through.
        """
        report = _caller_facing_report().model_copy(
            update={
                "model": "gpt-5",
                "provider": "openai",
                "provider_metadata": ProviderErrorMetadata(provider=ProviderName.OPENAI, sdk_exception_type="RateLimitError"),
            }
        )
        payload = report.to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert payload["message"] == report.message
        assert "model" not in payload
        assert "provider" not in payload
        assert "provider_metadata" not in payload

    def test_strict_redacts_domain_less_wrapper_raised_from_input_cause(self) -> None:
        """A domain-less wrapper raised ``from`` an INPUT cause must not leak its own message in STRICT.

        ``PipelexUnexpectedError`` (no domain, internal message) wrapping a
        ``PipelexInterpreterError`` (INPUT) produces a report classified
        ``error_domain=INPUT`` via ``__cause__``-chain inheritance — yet the
        report's ``message`` is the wrapper's internal text. ``caller_facing_message``
        is NOT inherited, so STRICT redacts the message.
        """
        cause = PipelexInterpreterError("parse failed at /srv/secret/internal/bundle.mthds")
        wrapper_message = "internal invariant violated: cache slot is None"
        try:
            raise PipelexUnexpectedError(wrapper_message) from cause
        except PipelexUnexpectedError as exc:
            report = exc.to_error_report()
        # error_domain IS inherited from the INPUT cause ...
        assert report.error_domain == ErrorDomain.INPUT
        # ... but caller_facing_message is NOT — the wrapper authored the message.
        assert report.caller_facing_message is False
        payload = report.to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert payload["message"] == INTERNAL_ERROR_PLACEHOLDER
        assert "invariant" not in payload["message"]

    def test_strict_passes_through_real_interpreter_error_message(self) -> None:
        """A genuine ``PipelexInterpreterError`` reflects its caller-facing message through STRICT."""
        report = PipelexInterpreterError("pipe 'foo' references unknown concept at line 5").to_error_report()
        assert report.caller_facing_message is True
        payload = report.to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert payload["message"] == "pipe 'foo' references unknown concept at line 5"

    def test_strict_does_not_sanitize_paths_inside_a_caller_facing_message(self) -> None:
        """STRICT is a provenance projection, NOT a path-leak shield.

        A genuinely caller-facing message is reflected verbatim — even if it
        contains a path. If such a message could surface a secret, the fix is to
        repair the upstream message, not to widen STRICT's scope.
        """
        report = _caller_facing_report("syntax error in /workspace/caller/bundle.mthds at line 8")
        payload = report.to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert payload["message"] == "syntax error in /workspace/caller/bundle.mthds at line 8"

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
            type_uri="https://docs.pipelex.com/latest/errors/cogt-error/",
            error_domain=ErrorDomain.RUNTIME,
            retryable=retryable,
        )
        payload = report.to_dict(disclosure_mode=mode)
        if retryable is None:
            assert "retryable" not in payload
        else:
            assert payload["retryable"] is retryable

    def test_caller_facing_message_serialized_only_when_set(self) -> None:
        """``caller_facing_message`` rides in ``to_dict`` only when True — a non-caller-facing report omits it.

        Keeps the common-case payload identical to a report without the field,
        while ``from_dict`` defaults the flag back to False so the round-trip holds.
        """
        assert "caller_facing_message" not in _runtime_report().to_dict()
        assert _caller_facing_report().to_dict()["caller_facing_message"] is True

    @pytest.mark.parametrize(
        "report",
        [
            pytest.param(_runtime_report(), id="runtime"),
            pytest.param(_caller_facing_report(), id="caller-facing"),
        ],
    )
    def test_verbose_round_trip_preserves_report(self, report: ErrorReport) -> None:
        """``from_dict(to_dict(VERBOSE))`` reconstructs the original report exactly, ``caller_facing_message`` included."""
        recovered = ErrorReport.from_dict(report.to_dict(disclosure_mode=DisclosureMode.VERBOSE))
        assert recovered == report
        assert recovered.caller_facing_message == report.caller_facing_message

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
