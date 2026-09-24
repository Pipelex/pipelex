"""Unit tests for `PostHogSpanExporter`, which had none.

The exporter is where a run's identity becomes a PostHog capture, and the whole
point of the change these tests pin is that it resolves the identity PER SPAN
rather than binding one for the life of the process. Each test drives the real
exporter with a real OTel span and a stubbed PostHog client, and asserts on the
capture call: the `distinct_id`, the `groups`, and — in every case — that the
user id did not also leak into the properties, where it would be a second copy
nobody keeps in step and a value no group-level count can use.
"""

from typing import Any

from opentelemetry.sdk.trace import Span as SdkSpan
from opentelemetry.sdk.trace import TracerProvider
from posthog import Posthog
from pytest_mock import MockerFixture

from pipelex.system.telemetry.otel_constants import PipelexSpanAttr, PostHogAttr, PostHogEvent, SpanCategory
from pipelex.system.telemetry.posthog_span_exporter import PostHogSpanExporter
from pipelex.system.telemetry.telemetry_config import TelemetryRedactionConfig
from pipelex.system.telemetry.telemetry_identity import RunIdentityPolicy

_FULL_CAPTURE = TelemetryRedactionConfig(
    redact_content=False,
    redact_pipe_codes=False,
    redact_output_class_names=False,
    content_max_length=None,
)


def _make_span(*, span_category: SpanCategory, attributes: dict[str, Any] | None = None) -> SdkSpan:
    """Produce a real, ended `ReadableSpan` the exporter can be handed."""
    tracer = TracerProvider().get_tracer("test")
    span_attributes: dict[str, Any] = {
        PipelexSpanAttr.SPAN_CATEGORY: span_category.value,
        PipelexSpanAttr.PIPELINE_RUN_ID: "run-1",
        PipelexSpanAttr.PIPE_CODE: "some_pipe",
        PipelexSpanAttr.PIPE_TYPE: "PipeLLM",
    }
    span_attributes.update(attributes or {})
    span = tracer.start_span(name="PipeLLM: some_pipe", attributes=span_attributes)
    span.end()
    assert isinstance(span, SdkSpan)
    return span


def _make_exporter(
    *,
    client: Posthog,
    fallback_distinct_id: str | None,
    run_identity_policy: RunIdentityPolicy,
) -> PostHogSpanExporter:
    return PostHogSpanExporter(
        posthog_client=client,
        fallback_distinct_id=fallback_distinct_id,
        run_identity_policy=run_identity_policy,
        redaction_config=_FULL_CAPTURE,
    )


class TestPostHogSpanExporter:
    def test_a_span_naming_a_user_is_captured_under_that_user(self, mocker: MockerFixture) -> None:
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id="deployment-hash", run_identity_policy=RunIdentityPolicy.DIRECT)

        exporter.export([_make_span(span_category=SpanCategory.PIPE, attributes={PipelexSpanAttr.RUN_USER_ID: "user-42"})])

        client.capture.assert_called_once()
        assert client.capture.call_args.kwargs["distinct_id"] == "user-42"

    def test_two_spans_of_two_runs_are_captured_under_two_users(self, mocker: MockerFixture) -> None:
        """The defect this whole change exists to fix: one process, one identity, every tenant."""
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id="deployment-hash", run_identity_policy=RunIdentityPolicy.DIRECT)

        exporter.export(
            [
                _make_span(span_category=SpanCategory.PIPE, attributes={PipelexSpanAttr.RUN_USER_ID: "user-42"}),
                _make_span(span_category=SpanCategory.PIPE, attributes={PipelexSpanAttr.RUN_USER_ID: "user-99"}),
            ]
        )

        captured_ids = [call.kwargs["distinct_id"] for call in client.capture.call_args_list]
        assert captured_ids == ["user-42", "user-99"]

    def test_a_generation_span_resolves_the_same_way(self, mocker: MockerFixture) -> None:
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id="deployment-hash", run_identity_policy=RunIdentityPolicy.DIRECT)

        exporter.export([_make_span(span_category=SpanCategory.INFERENCE, attributes={PipelexSpanAttr.RUN_USER_ID: "user-42"})])

        client.capture.assert_called_once()
        assert client.capture.call_args.kwargs["event"] == PostHogEvent.GENERATION
        assert client.capture.call_args.kwargs["distinct_id"] == "user-42"

    def test_a_span_naming_no_user_falls_back_to_the_configured_id(self, mocker: MockerFixture) -> None:
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id="deployment-hash", run_identity_policy=RunIdentityPolicy.DIRECT)

        exporter.export([_make_span(span_category=SpanCategory.PIPE)])

        assert client.capture.call_args.kwargs["distinct_id"] == "deployment-hash"

    def test_no_user_and_no_fallback_is_an_anonymous_capture(self, mocker: MockerFixture) -> None:
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id=None, run_identity_policy=RunIdentityPolicy.DIRECT)

        exporter.export([_make_span(span_category=SpanCategory.PIPE)])

        capture_kwargs = client.capture.call_args.kwargs
        assert "distinct_id" not in capture_kwargs
        assert capture_kwargs["properties"][PostHogAttr.PROCESS_PERSON_PROFILE] is False

    def test_the_runs_groups_ride_the_capture(self, mocker: MockerFixture) -> None:
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id=None, run_identity_policy=RunIdentityPolicy.DIRECT)

        exporter.export(
            [
                _make_span(
                    span_category=SpanCategory.PIPE,
                    attributes={
                        PipelexSpanAttr.RUN_USER_ID: "user-42",
                        PipelexSpanAttr.RUN_ANALYTICS_GROUPS: '{"organization": "org_acme"}',
                    },
                )
            ]
        )

        assert client.capture.call_args.kwargs["groups"] == {"organization": "org_acme"}

    def test_a_run_without_groups_sends_none_rather_than_an_empty_mapping(self, mocker: MockerFixture) -> None:
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id=None, run_identity_policy=RunIdentityPolicy.DIRECT)

        exporter.export([_make_span(span_category=SpanCategory.PIPE, attributes={PipelexSpanAttr.RUN_USER_ID: "user-42"})])

        assert client.capture.call_args.kwargs["groups"] is None

    def test_an_anonymous_stream_sends_no_identity_at_all(self, mocker: MockerFixture) -> None:
        """`NONE` is the operator's `posthog.mode = "anonymous"`, and it covers the operator too.

        The exporter is built with the configured `user_id` as its fallback —
        `anonymous` mode does not forbid one, so an operator may set one, switch
        modes and leave it behind. Sending it would put a person profile on every
        span of a stream whose mode promises the runtime identifies nobody.
        """
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id="configured-id", run_identity_policy=RunIdentityPolicy.NONE)

        exporter.export(
            [
                _make_span(
                    span_category=SpanCategory.PIPE,
                    attributes={
                        PipelexSpanAttr.RUN_USER_ID: "user-42",
                        PipelexSpanAttr.RUN_ANALYTICS_GROUPS: '{"organization": "org_acme"}',
                    },
                )
            ]
        )

        capture_kwargs = client.capture.call_args.kwargs
        assert "distinct_id" not in capture_kwargs
        assert "groups" not in capture_kwargs
        assert capture_kwargs["properties"][PostHogAttr.PROCESS_PERSON_PROFILE] is False

    def test_neither_the_user_nor_the_groups_appear_in_the_properties(self, mocker: MockerFixture) -> None:
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id=None, run_identity_policy=RunIdentityPolicy.DIRECT)

        exporter.export(
            [
                _make_span(
                    span_category=SpanCategory.INFERENCE,
                    attributes={
                        PipelexSpanAttr.RUN_USER_ID: "user-42",
                        PipelexSpanAttr.RUN_ANALYTICS_GROUPS: '{"organization": "org_acme"}',
                    },
                )
            ]
        )

        properties = client.capture.call_args.kwargs["properties"]
        rendered = repr(properties)
        assert "user-42" not in rendered
        assert "org_acme" not in rendered

    def test_the_fallback_identity_is_not_a_property_either(self, mocker: MockerFixture) -> None:
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id="deployment-hash", run_identity_policy=RunIdentityPolicy.DIRECT)

        exporter.export([_make_span(span_category=SpanCategory.PIPE)])

        assert "deployment-hash" not in repr(client.capture.call_args.kwargs["properties"])
