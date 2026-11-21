from typing import Any

import pytest
from opentelemetry.sdk.trace import Span as SdkSpan
from opentelemetry.sdk.trace import TracerProvider
from posthog import Posthog
from pytest_mock import MockerFixture

from pipelex.system.telemetry.otel_constants import OTelConstants, PipelexSpanAttr, PostHogAttr, SpanCategory
from pipelex.system.telemetry.posthog_span_exporter import PostHogSpanExporter
from pipelex.system.telemetry.telemetry_config import TelemetryRedactionConfig
from pipelex.system.telemetry.telemetry_identity import RunIdentityPolicy


def _redaction(*, redact: bool) -> TelemetryRedactionConfig:
    return TelemetryRedactionConfig(redact_content=True, redact_pipe_codes=redact, redact_output_class_names=redact, content_max_length=None)


def _make_span(*, span_category: SpanCategory, attributes: dict[str, Any] | None = None) -> SdkSpan:
    tracer = TracerProvider().get_tracer("test")
    span_attributes: dict[str, Any] = {
        PipelexSpanAttr.SPAN_CATEGORY: span_category.value,
        PipelexSpanAttr.PIPELINE_RUN_ID: "run-1",
        PipelexSpanAttr.PIPE_CODE: "extract_invoice",
        PipelexSpanAttr.PIPE_TYPE: "PipeLLM",
        PipelexSpanAttr.TRACE_NAME: "extract_invoice_abc",
        PipelexSpanAttr.TRACE_NAME_REDACTED: "abc",
        PipelexSpanAttr.OUTPUT_CLASS_NAME: "Invoice",
    }
    span_attributes.update(attributes or {})
    span = tracer.start_span(name="PipeLLM: extract_invoice", attributes=span_attributes)
    span.end()
    assert isinstance(span, SdkSpan)
    return span


def _export_properties(*, mocker: MockerFixture, redact: bool, span: SdkSpan) -> dict[str, Any]:
    client = mocker.MagicMock(spec=Posthog)
    exporter = PostHogSpanExporter(
        posthog_client=client,
        fallback_distinct_id="deployment",
        run_identity_policy=RunIdentityPolicy.DIRECT,
        redaction_config=_redaction(redact=redact),
    )
    exporter.export([span])
    client.capture.assert_called_once()
    properties: dict[str, Any] = client.capture.call_args.kwargs["properties"]
    return properties


class TestPostHogSpanExporterPipeIdentity:
    @pytest.mark.parametrize("span_category", [SpanCategory.PIPE, SpanCategory.INFERENCE])
    def test_the_method_id_and_the_pipe_id_ride_the_capture(self, mocker: MockerFixture, span_category: SpanCategory) -> None:
        span = _make_span(span_category=span_category, attributes={PipelexSpanAttr.RUN_METHOD_ID: "mt_abc", PipelexSpanAttr.PIPE_ID: "f" * 32})

        properties = _export_properties(mocker=mocker, redact=True, span=span)

        assert properties["method_id"] == "mt_abc"
        assert properties["pipe_id"] == "f" * 32

    @pytest.mark.parametrize("span_category", [SpanCategory.PIPE, SpanCategory.INFERENCE])
    def test_a_run_with_no_method_sends_a_null_method_id_and_no_pipe_id(self, mocker: MockerFixture, span_category: SpanCategory) -> None:
        properties = _export_properties(mocker=mocker, redact=True, span=_make_span(span_category=span_category))

        assert properties["method_id"] is None
        assert "pipe_id" not in properties

    @pytest.mark.parametrize("deployment_redacts", [True, False])
    def test_a_pipe_span_without_a_run_setting_follows_the_deployment(self, mocker: MockerFixture, deployment_redacts: bool) -> None:
        properties = _export_properties(mocker=mocker, redact=deployment_redacts, span=_make_span(span_category=SpanCategory.PIPE))

        assert properties["pipe_code"] == (OTelConstants.PIPE_CODE_REDACTED if deployment_redacts else "extract_invoice")

    @pytest.mark.parametrize("deployment_redacts", [True, False])
    def test_a_run_that_allows_pipe_codes_sends_them_on_its_pipe_span(self, mocker: MockerFixture, deployment_redacts: bool) -> None:
        span = _make_span(span_category=SpanCategory.PIPE, attributes={PipelexSpanAttr.RUN_CAPTURE_PIPE_CODES: True})

        properties = _export_properties(mocker=mocker, redact=deployment_redacts, span=span)

        assert properties["pipe_code"] == "extract_invoice"
        assert properties[PostHogAttr.SPAN_NAME] == "PipeLLM: extract_invoice"
        assert properties[PostHogAttr.TRACE_NAME] == "extract_invoice_abc"

    @pytest.mark.parametrize("deployment_redacts", [True, False])
    def test_a_run_that_forbids_pipe_codes_hides_them_on_its_pipe_span(self, mocker: MockerFixture, deployment_redacts: bool) -> None:
        span = _make_span(span_category=SpanCategory.PIPE, attributes={PipelexSpanAttr.RUN_CAPTURE_PIPE_CODES: False})

        properties = _export_properties(mocker=mocker, redact=deployment_redacts, span=span)

        assert properties["pipe_code"] == OTelConstants.PIPE_CODE_REDACTED
        assert properties[PostHogAttr.SPAN_NAME] == "PipeLLM"
        assert properties[PostHogAttr.TRACE_NAME] == "abc"
        assert "extract_invoice" not in str(properties)

    def test_a_run_that_allows_pipe_codes_sends_them_and_its_class_names_on_its_generations(self, mocker: MockerFixture) -> None:
        span = _make_span(span_category=SpanCategory.INFERENCE, attributes={PipelexSpanAttr.RUN_CAPTURE_PIPE_CODES: True})

        properties = _export_properties(mocker=mocker, redact=True, span=span)

        assert properties["pipe_code"] == "extract_invoice"
        assert properties["output_class_name"] == "Invoice"
        assert properties[PostHogAttr.TRACE_NAME] == "extract_invoice_abc"

    def test_a_run_that_forbids_pipe_codes_hides_them_and_its_class_names_on_its_generations(self, mocker: MockerFixture) -> None:
        span = _make_span(span_category=SpanCategory.INFERENCE, attributes={PipelexSpanAttr.RUN_CAPTURE_PIPE_CODES: False})

        properties = _export_properties(mocker=mocker, redact=False, span=span)

        assert properties["pipe_code"] == OTelConstants.PIPE_CODE_REDACTED
        assert properties["output_class_name"] == OTelConstants.PIPE_CODE_REDACTED
        assert "extract_invoice" not in str(properties)
        assert "Invoice" not in str(properties)
