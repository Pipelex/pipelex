"""Unit tests for ``ErrorReport.to_dict(disclosure_mode=...)`` — strict vs verbose projection.

``DisclosureMode.VERBOSE`` is the exact inverse of ``from_dict`` (round-trip preserved).
``DisclosureMode.STRICT`` is a lossy projection for untrusted external surfaces:
``provider`` / ``model`` are always dropped, ``provider_metadata`` is projected
through the curated subset (just ``status_code`` and ``retry_after_seconds`` —
actionable HTTP client hints), and the ``message`` is kept only when the report
is flagged ``caller_facing_message`` — the flag set by error classes
(``MthdsParserError`` / ``ValidateBundleError``) whose message describes
the caller's own input. Every other report has its ``message`` replaced with a
generic placeholder and ``user_action`` dropped, keeping the stable identifiers
(``error_type`` / ``error_domain`` / ``error_category`` / ``retryable`` /
``title`` / ``type_uri``) plus the curated ``provider_metadata`` slice.

The flag is keyed on message *provenance*, not ``error_domain``: ``error_domain``
is inherited up the ``__cause__`` chain, so a domain-less wrapper raised ``from``
an INPUT cause is classified INPUT — but its own internal ``message`` must still
be redacted. ``caller_facing_message`` is not inherited, so STRICT redacts it.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.base_exceptions import (
    INTERNAL_ERROR_PLACEHOLDER,
    DisclosureMode,
    ErrorDomain,
    ErrorReport,
    PipelexUnexpectedError,
    ValidationErrorCategory,
    ValidationErrorItem,
)
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserAction, UserActionKind
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.mthds_parsing.exceptions import MthdsParserError


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
        error_type="MthdsParserError",
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

        ``provider_metadata`` is the one classification field allowed through
        STRICT as a curated subset: ``status_code`` and ``retry_after_seconds``
        (HTTP client hints) survive — see ``test_strict_preserves_curated_provider_metadata``.
        """
        payload = report.to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert payload["message"] == INTERNAL_ERROR_PLACEHOLDER
        assert "user_action" not in payload
        assert "model" not in payload
        assert "provider" not in payload
        # Stable identifiers survive.
        assert payload["error_type"] == report.error_type
        assert payload["title"] == report.title
        assert payload["type_uri"] == report.type_uri
        if report.error_domain is not None:
            assert payload["error_domain"] == report.error_domain
        if report.error_category is not None:
            assert payload["error_category"] == report.error_category

    def test_strict_passes_through_caller_facing_message(self) -> None:
        """A report flagged ``caller_facing_message`` keeps its ``message`` and ``user_action`` in STRICT.

        The ``caller_facing_message`` flag itself is internal redaction plumbing —
        it rides only the VERBOSE round-trip format, never the STRICT projection.
        """
        report = _caller_facing_report()
        payload = report.to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert payload["message"] == report.message
        assert "user_action" in payload
        assert "caller_facing_message" not in payload

    def test_strict_strips_provider_fields_even_from_caller_facing_passthrough(self) -> None:
        """Gap 2: provider/model attribution is stripped from the caller-facing passthrough branch.

        An INPUT-classification error can pick up ``provider`` / ``model`` /
        ``provider_metadata`` from an inference-layer ``__cause__`` during
        enrichment. STRICT must never reflect that onto an external surface,
        even when the ``message`` itself is allowed through. A
        ``provider_metadata`` with no curated fields (no ``status_code`` /
        ``retry_after_seconds``) is omitted entirely.
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

    def test_strict_preserves_curated_provider_metadata(self) -> None:
        """STRICT preserves ``status_code`` and ``retry_after_seconds`` — actionable HTTP client hints.

        Provider 429s carry a ``Retry-After`` hint the HTTP adapter needs to emit
        a useful response header. Provider identity / SDK type / free-form
        message / request_id are still stripped — only the curated subset rides.

        Holds for BOTH the redacted (non-caller-facing) and caller-facing
        passthrough branches.
        """
        non_caller_facing_report = _runtime_report()
        payload = non_caller_facing_report.to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert "provider_metadata" in payload
        assert payload["provider_metadata"] == {"status_code": 429, "retry_after_seconds": 12.0}
        # The other ProviderErrorMetadata fields (provider, sdk_exception_type) must not leak.
        assert "provider" not in payload["provider_metadata"]
        assert "sdk_exception_type" not in payload["provider_metadata"]

        caller_facing_report = _caller_facing_report().model_copy(
            update={
                "provider_metadata": ProviderErrorMetadata(
                    provider=ProviderName.OPENAI,
                    sdk_exception_type="RateLimitError",
                    status_code=429,
                    retry_after_seconds=12.0,
                ),
            }
        )
        caller_facing_payload = caller_facing_report.to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert caller_facing_payload["provider_metadata"] == {"status_code": 429, "retry_after_seconds": 12.0}

    def test_strict_omits_provider_metadata_when_only_curated_subset_is_empty(self) -> None:
        """A ``provider_metadata`` with no curated fields is omitted entirely rather than emitted as an empty dict."""
        report = _runtime_report().model_copy(
            update={
                "provider_metadata": ProviderErrorMetadata(
                    provider=ProviderName.OPENAI,
                    sdk_exception_type="RateLimitError",
                    status_code=None,
                    retry_after_seconds=None,
                ),
            }
        )
        payload = report.to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert "provider_metadata" not in payload

    def test_strict_provider_metadata_dict_carries_http_status_for_adapter(self) -> None:
        """A STRICT-projected dict carries ``status_code=429`` and ``retry_after_seconds`` for the HTTP adapter.

        STRICT is not meant to round-trip through :meth:`ErrorReport.from_dict`
        (see ``test_strict_does_not_round_trip``) — consumers read the dict
        directly. This pins the contract the HTTP adapter relies on: it can
        read ``payload["provider_metadata"]["status_code"]`` to emit the right
        status and ``payload["provider_metadata"]["retry_after_seconds"]`` to
        emit a useful ``Retry-After`` header, without rehydrating.
        """
        report = _runtime_report()
        strict_payload = report.to_dict(disclosure_mode=DisclosureMode.STRICT)
        provider_metadata = strict_payload["provider_metadata"]
        assert provider_metadata["status_code"] == 429
        assert provider_metadata["retry_after_seconds"] == 12.0

    def test_strict_redacts_domain_less_wrapper_raised_from_input_cause(self) -> None:
        """A domain-less wrapper raised ``from`` an INPUT cause must not leak its own message in STRICT.

        ``PipelexUnexpectedError`` (no domain, internal message) wrapping a
        ``MthdsParserError`` (INPUT) produces a report classified
        ``error_domain=INPUT`` via ``__cause__``-chain inheritance — yet the
        report's ``message`` is the wrapper's internal text. ``caller_facing_message``
        is NOT inherited, so STRICT redacts the message.
        """
        cause = MthdsParserError("parse failed at /srv/secret/internal/bundle.mthds")
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
        """A genuine ``MthdsParserError`` reflects its caller-facing message through STRICT."""
        report = MthdsParserError("pipe 'foo' references unknown concept at line 5").to_error_report()
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
        """STRICT is not the inverse of :meth:`ErrorReport.from_dict` — consumers must read the dict directly.

        STRICT carries a redacted ``message``, drops provider/model identity,
        drops ``user_action``, and projects ``provider_metadata`` through a
        curated subset. Read the dict's fields directly (``payload[<key>]``);
        ``from_dict`` is meant only as the VERBOSE round-trip inverse.
        """
        report = _runtime_report()
        strict_payload = report.to_dict(disclosure_mode=DisclosureMode.STRICT)
        # Direct dict reads — the HTTP adapter / API surface doesn't rehydrate.
        assert strict_payload["message"] == INTERNAL_ERROR_PLACEHOLDER
        assert "provider" not in strict_payload
        assert "model" not in strict_payload
        assert "user_action" not in strict_payload
        # The curated ``provider_metadata`` slice rides for the HTTP adapter to
        # emit Retry-After / the right status — see
        # ``test_strict_provider_metadata_dict_carries_http_status_for_adapter``.

    def test_strict_payload_with_provider_metadata_fails_from_dict_rehydration(self) -> None:
        """A STRICT payload that carries ``provider_metadata`` is not rehydratable via :meth:`from_dict`.

        Pins the sharp failure mode external consumers should expect: the
        curated subset (``status_code`` / ``retry_after_seconds``) lacks the
        ``provider`` and ``sdk_exception_type`` fields required by
        :class:`ProviderErrorMetadata`, so :meth:`ErrorReport.from_dict` raises
        :class:`pydantic.ValidationError`. Consumers must read the STRICT dict
        directly (e.g. via :meth:`ErrorReport.to_problem_document`) rather than
        rebuilding through ``from_dict``; any code path that relied on the
        pre-curated-subset behavior — where STRICT dropped ``provider_metadata``
        entirely and was therefore still rehydratable — must migrate.
        """
        report = _runtime_report()
        strict_payload = report.to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert "provider_metadata" in strict_payload
        with pytest.raises(ValidationError):
            ErrorReport.from_dict(strict_payload)

    def test_to_dict_defaults_to_verbose(self) -> None:
        """No argument == VERBOSE — the safe default for in-process / round-trip callers."""
        report = _runtime_report()
        assert report.to_dict() == report.to_dict(disclosure_mode=DisclosureMode.VERBOSE)

    def test_strict_branch_kept_field_parity(self) -> None:
        """STRICT projection: both branches emit the same key set modulo the deliberately divergent keys.

        Pins the single-allowlist contract introduced when the two STRICT
        branches were unified: caller-facing and redacted branches share
        ``_STRICT_KEPT_FIELDS`` as the base, and the caller-facing branch
        adds ``message`` and ``user_action`` on top while the redacted branch
        only emits a placeholder ``message``. Both branches reattach the
        same curated ``provider_metadata`` slice. The remaining key set must
        match — without this pin, a new ``ErrorReport`` field added in the
        future could silently appear on one branch and silently disappear
        from the other.
        """
        # A report with every populatable field set, so both branches see the
        # same payload going in. We then flip ``caller_facing_message`` to
        # exercise each branch — using ``model_copy`` so pyright sees the
        # concrete field types instead of the union we'd get from ``**kwargs``.
        caller_facing_report = ErrorReport(
            error_type="MthdsParserError",
            message="pipe references unknown concept",
            title="Pipelex interpreter error",
            type_uri="https://docs.pipelex.com/latest/errors/pipelex-interpreter-error/",
            error_category="capacity",
            error_domain=ErrorDomain.INPUT,
            retryable=False,
            user_action=UserAction(kind=UserActionKind.CHANGE_INPUT, detail="fix the concept name"),
            model="gpt-5",
            provider="openai",
            provider_metadata=ProviderErrorMetadata(
                provider=ProviderName.OPENAI,
                sdk_exception_type="RateLimitError",
                status_code=429,
                retry_after_seconds=12.0,
            ),
            caller_facing_message=True,
        )
        redacted_report = caller_facing_report.model_copy(update={"caller_facing_message": False})

        caller_facing_payload = caller_facing_report.to_dict(disclosure_mode=DisclosureMode.STRICT)
        redacted_payload = redacted_report.to_dict(disclosure_mode=DisclosureMode.STRICT)

        # ``message`` is on both (different values), ``user_action`` only on caller-facing —
        # those are the legitimate divergences. After removing them, the key sets must match.
        assert set(caller_facing_payload) - {"message", "user_action"} == set(redacted_payload) - {"message"}

    @pytest.mark.parametrize(
        "caller_facing",
        [
            pytest.param(True, id="caller-facing-branch"),
            pytest.param(False, id="redacted-branch"),
        ],
    )
    def test_strict_retains_validation_errors_on_both_branches(self, caller_facing: bool) -> None:
        """``validation_errors`` survives STRICT on BOTH the caller-facing and redacted branches.

        The structured per-error list describes the caller's own submitted bundle,
        not server internals — so it is kept on the external surface via
        ``_STRICT_KEPT_FIELDS`` rather than by the caller-facing branch's bespoke
        message logic. A real ``ValidateBundleError`` only ever rides the
        caller-facing branch, but the field must be branch-independent so a future
        non-caller-facing report carrying it is not silently redacted.
        """
        report = ErrorReport(
            error_type="ValidateBundleError",
            message="bundle failed validation",
            title="Validate bundle error",
            type_uri="https://docs.pipelex.com/latest/errors/validate-bundle-error/",
            error_domain=ErrorDomain.INPUT,
            caller_facing_message=caller_facing,
            validation_errors=[
                ValidationErrorItem(
                    category=ValidationErrorCategory.PIPE_VALIDATION,
                    source="main.mthds",
                    pipe_code="summarize",
                    message="Missing input variable(s): doc.",
                ),
            ],
        )
        payload = report.to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert "validation_errors" in payload
        assert payload["validation_errors"][0]["source"] == "main.mthds"

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
