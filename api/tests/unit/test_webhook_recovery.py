"""Cross-path consistency regression for the API's two error surfaces.

The API surfaces a pipelex `ErrorReport` to clients along two paths:

1. The **synchronous HTTP path** — `POST /execute` (and every other
   route that propagates a `PipelexError`) renders the report via
   `build_problem_document(...)` → RFC 7807 `application/problem+json`.
2. The **asynchronous webhook path** — `POST /start` schedules a
   Temporal workflow; on completion (success or `FAILED`), pipelex's
   `DeliveryExecutor._notify_webhook(...)` posts a JSON payload to the
   caller's callback URL. On `FAILED`, the payload carries
   `error: <ErrorReport.to_dict(disclosure_mode=VERBOSE)>` — a flat dict, not
   an RFC 7807 envelope (the receiver chooses how to render it).

This module pins the **T6 cross-path consistency** invariant: given the same
source `ErrorReport`, both renderings must surface the same classification
fields. A client that branches on `error_type` / `error_domain` /
`retryable` / `user_action` must not get one classification synchronously
and a different one over the webhook.

The webhook payload itself is composed entirely upstream in
`pipelex.pipe_run.delivery_executor`; the API never touches the bytes that
go over the wire. So this test exercises the two rendering helpers directly
and asserts the classification overlap is exact. Drift here would imply
either pipelex's `to_dict` / `to_problem_document` diverged in their field
selection, or the API's `build_problem_document` wrapper started shaping
the document.
"""

from typing import Any

import pytest
from pipelex.base_exceptions import DisclosureMode, ErrorDomain, ErrorReport
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserAction, UserActionKind
from pipelex.cogt.inference.provider_name import ProviderName

from api.problem_document import build_problem_document

# Classification fields that, when populated on the source `ErrorReport`,
# must appear with identical values in both renderings. Excluded from this
# list are: (a) `message` — present in both but under different keys
# (`message` in `to_dict`, `detail` in `to_problem_document`); checked
# separately. (b) the RFC 7807 standard slots `type`/`title`/`status` and
# the request-scoped extension members `instance`/`request_id` — those are
# rightfully envelope-only.
_CLASSIFICATION_FIELDS_PRESERVED = (
    "error_type",
    "error_domain",
    "error_category",
    "retryable",
    "user_action",
    "model",
    "provider",
    "provider_metadata",
)


def _fully_populated_llm_report() -> ErrorReport:
    """A provider-429 report exercising every classification field at once.

    Provider/model/provider_metadata ride on `RUNTIME`-domain inference
    failures, so an `LLMCompletionError` stand-in is the broadest single
    fixture: it pins the parity contract on the maximum field set the API
    ever surfaces.
    """
    return ErrorReport(
        error_type="LLMCompletionError",
        message="OpenAI returned 429 (rate_limit_exceeded)",
        title="LLM completion error",
        type_uri="https://docs.pipelex.com/latest/errors/llm-completion-error/",
        error_domain=ErrorDomain.RUNTIME,
        error_category="rate_limit",
        retryable=True,
        user_action=UserAction(
            kind=UserActionKind.WAIT_AND_RETRY,
            detail="The provider is rate-limiting your account. Retry after the indicated delay.",
        ),
        model="gpt-4o-mini",
        provider="openai",
        provider_metadata=ProviderErrorMetadata(
            provider=ProviderName.OPENAI,
            sdk_exception_type="RateLimitError",
            status_code=429,
            retry_after_seconds=12.0,
            request_id="req_provider_abc",
        ),
    )


def _caller_facing_input_report() -> ErrorReport:
    """A caller-facing INPUT-domain report (the other half of the STRICT contract).

    Complements the LLM fixture: minimal classification but
    `caller_facing_message=True`, which is the trigger STRICT projection
    keys its `message` passthrough on. Used here to verify that the parity
    contract holds across both message-disclosure provenances.
    """
    return ErrorReport(
        error_type="MthdsParserError",
        message="Your .mthds file has a syntax error on line 4",
        title="Pipelex interpreter error",
        type_uri="https://docs.pipelex.com/latest/errors/pipelex-interpreter-error/",
        error_domain=ErrorDomain.INPUT,
        retryable=False,
        caller_facing_message=True,
    )


class TestWebhookRecoveryCrossPath:
    @pytest.mark.parametrize(
        ("label", "report_factory"),
        [
            ("llm_provider_429", _fully_populated_llm_report),
            ("caller_facing_input", _caller_facing_input_report),
        ],
    )
    def test_classification_fields_match_between_sync_and_webhook(self, label: str, report_factory: Any) -> None:
        """T6 regression: webhook `error` and sync RFC 7807 body must agree.

        For every classification field that pipelex populates on the source
        report, the value in `ErrorReport.to_dict(VERBOSE)` (what the webhook
        carries under `error`) must be byte-identical to the value rendered
        in the RFC 7807 problem document (what the sync handler returns).
        """
        report = report_factory()
        webhook_payload = report.to_dict(disclosure_mode=DisclosureMode.VERBOSE)
        problem_doc = build_problem_document(
            report,
            instance="/v1/execute",
            request_id="REQ_T6",
            disclosure_mode=DisclosureMode.VERBOSE,
        )

        for field in _CLASSIFICATION_FIELDS_PRESERVED:
            in_webhook = field in webhook_payload
            in_problem = field in problem_doc
            assert in_webhook == in_problem, f"{label}: field `{field}` presence mismatch (webhook={in_webhook}, problem={in_problem})"
            if in_webhook:
                assert webhook_payload[field] == problem_doc[field], f"{label}: field `{field}` value drift between paths"

        # `message` rides under different keys by design — pin the bridge.
        assert problem_doc["detail"] == webhook_payload["message"], (
            f"{label}: sync `detail` and webhook `message` must carry identical text under VERBOSE"
        )

    def test_sync_only_envelope_members_are_isolated_to_problem_document(self) -> None:
        """The RFC 7807 envelope is the sync path's contract, not the webhook's.

        `type` / `status` / `detail` / `instance` / `request_id` are the
        envelope-only members: pipelex's `to_problem_document` maps them from
        report fields (`type_uri` → `type`, `http_status` → `status`,
        `message` → `detail`) or sources them from the caller (`instance`,
        `request_id`). They never appear on the raw `to_dict` output the
        webhook carries — the webhook is the structured-data layer (per
        Phase 4b decision); receivers that want an envelope render one
        themselves. Pin the asymmetry so a refactor of either path doesn't
        quietly leak envelope members into the webhook payload or strip them
        from the sync body. (`title` and `type_uri` ARE direct fields on
        `ErrorReport`, so they appear in both — not envelope-only.)
        """
        report = _fully_populated_llm_report()
        webhook_payload = report.to_dict(disclosure_mode=DisclosureMode.VERBOSE)
        problem_doc = build_problem_document(
            report,
            instance="/v1/execute",
            request_id="REQ_T6",
            disclosure_mode=DisclosureMode.VERBOSE,
        )

        for envelope_member in ("type", "status", "detail", "instance", "request_id"):
            assert envelope_member in problem_doc, f"sync path must carry RFC 7807 envelope member `{envelope_member}`"
            assert envelope_member not in webhook_payload, (
                f"webhook payload must NOT carry RFC 7807 envelope member `{envelope_member}` (use `to_problem_document` if you need an envelope)"
            )

    def test_webhook_carries_raw_report_regardless_of_disclosure_mode(self) -> None:
        """The webhook always renders the report VERBOSE, even when sync is STRICT.

        The receiver decides what to re-expose downstream — pipelex hardcodes
        `DisclosureMode.VERBOSE` in `_notify_webhook` for exactly this reason.
        Pin it here so a future refactor that introduces a `disclosure_mode`
        knob on the webhook path is caught by this test.
        """
        report = _fully_populated_llm_report()
        verbose_payload = report.to_dict(disclosure_mode=DisclosureMode.VERBOSE)
        strict_payload = report.to_dict(disclosure_mode=DisclosureMode.STRICT)

        # The provider-identifying fields are the cheapest signal that the
        # projection actually fired: VERBOSE keeps them, STRICT drops them.
        assert verbose_payload.get("provider") == "openai"
        assert verbose_payload.get("model") == "gpt-4o-mini"
        assert "provider" not in strict_payload
        assert "model" not in strict_payload
