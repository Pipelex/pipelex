"""Unit tests for ``ErrorReport.to_problem_document`` — RFC 7807 envelope.

The runner stays HTTP-agnostic (no FastAPI/Starlette import); ``to_problem_document``
returns a plain dict that downstream HTTP adapters serialize as JSON. The
standard 7807 slots (``type``, ``title``, ``status``, ``detail``, ``instance``)
are populated from the report; pipelex-native classification fields ride as
extension members. ``type_uri`` and ``title`` are mapped, not duplicated — there
is exactly one ``title`` key and ``type == type_uri``.
"""

import pytest

from pipelex.base_exceptions import INTERNAL_ERROR_PLACEHOLDER, DisclosureMode, ErrorDomain, ErrorReport
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserAction, UserActionKind
from pipelex.cogt.inference.provider_name import ProviderName


def _runtime_report() -> ErrorReport:
    return ErrorReport(
        error_type="CogtError",
        message="rate limited on the worker",
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


class TestErrorReportProblemDocument:
    def test_standard_slots_populated_from_report(self) -> None:
        """``type`` / ``title`` / ``status`` / ``detail`` / ``instance`` come straight off the report or args."""
        report = _runtime_report()
        document = report.to_problem_document(instance="urn:pipelex:run:123", request_id="r-abc")
        assert document["type"] == report.type_uri
        assert document["title"] == report.title
        assert document["status"] == report.http_status
        assert document["detail"] == report.message
        assert document["instance"] == "urn:pipelex:run:123"
        assert document["request_id"] == "r-abc"

    def test_rfc_7807_mapping_does_not_duplicate_title_or_type(self) -> None:
        """``type_uri`` / ``title`` are mapped into the standard slots — not echoed in extensions."""
        report = _runtime_report()
        document = report.to_problem_document()
        # Single ``title`` key — no extension would otherwise collide with the standard slot.
        assert sum(1 for key in document if key == "title") == 1
        # ``type`` standard slot holds the URI value; no separate ``type_uri`` extension survives.
        assert document["type"] == report.type_uri
        assert "type_uri" not in document

    def test_extension_members_carry_pipelex_classification(self) -> None:
        """Pipelex-native fields ride as extensions; the standard slots do not duplicate them."""
        report = _runtime_report()
        document = report.to_problem_document()
        assert document["error_type"] == "CogtError"
        assert document["error_domain"] == ErrorDomain.RUNTIME
        assert document["error_category"] == "capacity"
        assert document["retryable"] is False
        assert document["model"] == "gpt-5"
        assert document["provider"] == "openai"
        assert document["user_action"]["kind"] == UserActionKind.CHECK_BILLING

    def test_request_id_extension_absent_when_not_provided(self) -> None:
        """``request_id`` is an optional extension — omitted when the caller does not pass it."""
        document = _runtime_report().to_problem_document()
        assert "request_id" not in document

    def test_instance_extension_absent_when_not_provided(self) -> None:
        """``instance`` is optional — omitted when the caller does not pass it."""
        document = _runtime_report().to_problem_document()
        assert "instance" not in document

    @pytest.mark.parametrize(
        ("error_domain", "expected_status"),
        [
            pytest.param(ErrorDomain.INPUT, 422, id="input-422"),
            pytest.param(ErrorDomain.CONFIG, 500, id="config-500"),
            pytest.param(ErrorDomain.RUNTIME, 500, id="runtime-500"),
        ],
    )
    def test_status_follows_http_status_property(self, error_domain: ErrorDomain, expected_status: int) -> None:
        """``status`` follows ``ErrorReport.http_status`` so the domain → HTTP mapping is honored."""
        report = ErrorReport(
            error_type="X",
            message="m",
            title="X",
            type_uri="https://docs.pipelex.com/latest/errors/x/",
            error_domain=error_domain,
        )
        document = report.to_problem_document()
        assert document["status"] == expected_status

    def test_strict_mode_redacts_detail_and_drops_disclosure_fields(self) -> None:
        """Strict ``to_problem_document`` redacts ``detail`` and drops disclosure-leaking extensions.

        ``provider`` / ``model`` identity is stripped. ``provider_metadata`` is
        projected through the curated subset — ``status_code`` and
        ``retry_after_seconds`` ride as an extension member so HTTP adapters can
        derive ``Retry-After`` headers from the problem document.
        """
        report = _runtime_report()
        document = report.to_problem_document(disclosure_mode=DisclosureMode.STRICT)
        assert document["detail"] == INTERNAL_ERROR_PLACEHOLDER
        assert "model" not in document
        assert "provider" not in document
        assert "user_action" not in document
        # Stable identifiers are kept.
        assert document["error_type"] == "CogtError"
        assert document["error_category"] == "capacity"
        assert document["retryable"] is False
        # Curated provider_metadata slice rides as an extension member.
        assert document["provider_metadata"] == {"status_code": 429, "retry_after_seconds": 12.0}

    def test_strict_mode_passes_through_detail_for_caller_facing_report(self) -> None:
        """A caller-facing-message report reflects ``detail`` back unchanged in STRICT mode."""
        report = ErrorReport(
            error_type="MthdsParserError",
            message="pipe 'summarize' references unknown concept at line 14",
            title="MTHDS parser",
            type_uri="https://docs.pipelex.com/latest/errors/mthds-parser-error/",
            error_domain=ErrorDomain.INPUT,
            caller_facing_message=True,
        )
        document = report.to_problem_document(disclosure_mode=DisclosureMode.STRICT)
        assert document["detail"] == "pipe 'summarize' references unknown concept at line 14"

    def test_strict_mode_redacts_detail_for_input_domain_without_caller_facing_flag(self) -> None:
        """An INPUT-classified report whose message is NOT caller-facing is still redacted in STRICT.

        Regression pin: ``error_domain == INPUT`` alone (here inherited up a
        ``__cause__`` chain by a domain-less wrapper) must not earn a ``detail``
        passthrough — only ``caller_facing_message`` does.
        """
        report = ErrorReport(
            error_type="PipelexUnexpectedError",
            message="internal invariant violated at /srv/secret/handler.py",
            title="Unexpected internal error",
            type_uri="https://docs.pipelex.com/latest/errors/pipelex-unexpected-error/",
            error_domain=ErrorDomain.INPUT,
        )
        document = report.to_problem_document(disclosure_mode=DisclosureMode.STRICT)
        assert document["detail"] == INTERNAL_ERROR_PLACEHOLDER

    def test_strict_mode_never_emits_provider_fields_regardless_of_error_domain(self) -> None:
        """STRICT ``to_problem_document`` never echoes ``provider`` / ``model`` / ``provider_metadata``.

        Gap 2: even a caller-facing INPUT report whose cause-enrichment pulled
        provider metadata from an inference ``__cause__`` must not surface it on
        the RFC 7807 envelope.
        """
        report = ErrorReport(
            error_type="MthdsParserError",
            message="pipe 'summarize' references unknown concept at line 14",
            title="MTHDS parser",
            type_uri="https://docs.pipelex.com/latest/errors/mthds-parser-error/",
            error_domain=ErrorDomain.INPUT,
            caller_facing_message=True,
            model="gpt-5",
            provider="openai",
            provider_metadata=ProviderErrorMetadata(provider=ProviderName.OPENAI, sdk_exception_type="RateLimitError"),
        )
        document = report.to_problem_document(disclosure_mode=DisclosureMode.STRICT)
        assert document["detail"] == report.message
        assert "model" not in document
        assert "provider" not in document
        assert "provider_metadata" not in document

    def test_caller_facing_message_flag_never_rides_as_extension_member(self) -> None:
        """``caller_facing_message`` is internal redaction plumbing — never an RFC 7807 extension member."""
        report = ErrorReport(
            error_type="MthdsParserError",
            message="pipe 'summarize' references unknown concept at line 14",
            title="MTHDS parser",
            type_uri="https://docs.pipelex.com/latest/errors/mthds-parser-error/",
            error_domain=ErrorDomain.INPUT,
            caller_facing_message=True,
        )
        verbose_document = report.to_problem_document(disclosure_mode=DisclosureMode.VERBOSE)
        strict_document = report.to_problem_document(disclosure_mode=DisclosureMode.STRICT)
        assert "caller_facing_message" not in verbose_document
        assert "caller_facing_message" not in strict_document
