"""Unit tests for `PostHogSpanExporter`, which had none.

The exporter is where a run's identity becomes a PostHog capture, and the whole
point of the change these tests pin is that it resolves the identity PER SPAN
rather than binding one for the life of the process. Each test drives the real
exporter with a real OTel span and a stubbed PostHog client, and asserts on the
capture call: the `distinct_id`, the `groups`, and — in every case — that the
user id did not also leak into the properties, where it would be a second copy
nobody keeps in step and a value no group-level count can use.
"""

import uuid
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.sdk.trace import Span as SdkSpan
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import NonRecordingSpan, SpanContext, Status, StatusCode, TraceFlags
from posthog import Posthog
from pytest_mock import MockerFixture

from pipelex.system.telemetry.otel_constants import (
    GenAISpanAttr,
    InferenceKind,
    OTelConstants,
    PipelexSpanAttr,
    PostHogAttr,
    PostHogEvent,
    SpanCategory,
)
from pipelex.system.telemetry.posthog_span_exporter import EVENT_UUID_NAMESPACE, PostHogSpanExporter, make_trace_root_span_id
from pipelex.system.telemetry.telemetry_config import TelemetryRedactionConfig
from pipelex.system.telemetry.telemetry_identity import RunIdentityPolicy
from pipelex.tools.misc.package_utils import get_package_version

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


def _generation_span(*, name: str, attributes: dict[str, Any]) -> SdkSpan:
    """An ended generation span as an inference call leaves it, with `attributes` over its model and usage keys."""
    tracer = TracerProvider().get_tracer("test")
    span_attributes: dict[str, Any] = {
        PipelexSpanAttr.SPAN_CATEGORY: SpanCategory.INFERENCE.value,
        PipelexSpanAttr.PIPELINE_RUN_ID: "run-1",
        PipelexSpanAttr.PIPE_CODE: "some_pipe",
        PipelexSpanAttr.UNIT_JOB_ID: "llm_gen_text",
        PipelexSpanAttr.MODEL_HANDLE: "claude-4.5-sonnet",
        PipelexSpanAttr.INFERENCE_BACKEND: "pipelex_gateway",
        PipelexSpanAttr.INFERENCE_KIND: InferenceKind.LLM.value,
        GenAISpanAttr.OPERATION_NAME: "chat",
        GenAISpanAttr.PROVIDER_NAME: "pipelex_gateway",
        GenAISpanAttr.REQUEST_MODEL: "claude-sonnet-4-5",
        GenAISpanAttr.RESPONSE_MODEL: "claude-sonnet-4-5",
    }
    span_attributes.update(attributes)
    span = tracer.start_span(name=name, attributes=span_attributes)
    span.end()
    assert isinstance(span, SdkSpan)
    return span


_TRACE_ID = 0x0123456789ABCDEF0123456789ABCDEF
_STARTED_AT_NS = 1_700_000_000_000_000_000


def _parent_context(*, parent_span_id: int) -> Context:
    """The context a span starts under when its parent is the span `parent_span_id` of the trace `_TRACE_ID`."""
    return trace.set_span_in_context(
        NonRecordingSpan(SpanContext(trace_id=_TRACE_ID, span_id=parent_span_id, is_remote=True, trace_flags=TraceFlags(TraceFlags.SAMPLED)))
    )


def _virtual_root_context() -> Context:
    """The context a run's own root pipe span starts under: the virtual root parent that sets the run's trace id."""
    return _parent_context(parent_span_id=OTelConstants.OTEL_VIRTUAL_ROOT_PARENT_SPAN_ID)


def _pipe_attributes(*, pipe_type: str) -> dict[str, Any]:
    """A pipe span's attributes as `PipeAbstract` writes them, for a run whose full trace name is `root_abc12345`."""
    return {
        PipelexSpanAttr.SPAN_CATEGORY: SpanCategory.PIPE.value,
        PipelexSpanAttr.PIPELINE_RUN_ID: "run-1",
        PipelexSpanAttr.PIPE_CODE: "root",
        PipelexSpanAttr.PIPE_TYPE: pipe_type,
        PipelexSpanAttr.PIPE_CATEGORY: "PipeController",
        PipelexSpanAttr.OUTCOME: "success",
        PipelexSpanAttr.TRACE_NAME: "root_abc12345",
        PipelexSpanAttr.TRACE_NAME_REDACTED: "abc12345",
    }


def _pipe_span_under(
    *,
    parent_span_id: int,
    is_run_root: bool,
    method_id: str | None = None,
    capture_pipe_codes: bool | None = None,
    extra_attributes: dict[str, Any] | None = None,
) -> SdkSpan:
    """An ended `PipeSequence` span under the span `parent_span_id`, marked as its run's root when `is_run_root`."""
    attributes = _pipe_attributes(pipe_type="PipeSequence")
    if is_run_root:
        attributes[PipelexSpanAttr.RUN_ROOT] = True
    if method_id is not None:
        attributes[PipelexSpanAttr.RUN_METHOD_ID] = method_id
    if capture_pipe_codes is not None:
        attributes[PipelexSpanAttr.RUN_CAPTURE_PIPE_CODES] = capture_pipe_codes
    attributes.update(extra_attributes or {})
    span = (
        TracerProvider()
        .get_tracer("test")
        .start_span(name="PipeSequence: root", context=_parent_context(parent_span_id=parent_span_id), attributes=attributes)
    )
    span.end()
    assert isinstance(span, SdkSpan)
    return span


def _trace_root_capture(client: Any) -> Any:
    """The one capture of the trace's root, the `$ai_span` without a parent."""
    (root_capture,) = [call for call in client.capture.call_args_list if PostHogAttr.PARENT_ID not in call.kwargs["properties"]]
    return root_capture


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
                        PipelexSpanAttr.RUN_EXTRAS: '{"organization": "org_acme"}',
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
                        PipelexSpanAttr.RUN_EXTRAS: '{"organization": "org_acme"}',
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
                        PipelexSpanAttr.RUN_EXTRAS: '{"organization": "org_acme"}',
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

    @pytest.mark.parametrize(
        ("parent_span_id", "is_run_root", "expected_parent_id"),
        [
            # A run's root pipe span under the host's span, in a run that joined the host's trace: a parent this stream
            # never receives, so it hangs from the trace's root instead.
            (0x00000000000000CD, True, make_trace_root_span_id(trace_id=_TRACE_ID, pipeline_run_id="run-1")),
            # A run's own root pipe span, under the virtual root parent: it hangs from the trace's root too.
            (OTelConstants.OTEL_VIRTUAL_ROOT_PARENT_SPAN_ID, True, make_trace_root_span_id(trace_id=_TRACE_ID, pipeline_run_id="run-1")),
            # A nested pipe or an LLM call, under a Pipelex span this stream receives.
            (0x00000000000000AB, False, "00000000000000ab"),
        ],
    )
    def test_a_pipe_span_names_the_parent_this_stream_receives(
        self, mocker: MockerFixture, parent_span_id: int, is_run_root: bool, expected_parent_id: str
    ) -> None:
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id=None, run_identity_policy=RunIdentityPolicy.DIRECT)

        exporter.export([_pipe_span_under(parent_span_id=parent_span_id, is_run_root=is_run_root)])

        (pipe_capture,) = [call for call in client.capture.call_args_list if call.kwargs["properties"].get("pipe_type") == "PipeSequence"]
        assert pipe_capture.kwargs["properties"].get(PostHogAttr.PARENT_ID) == expected_parent_id

    def test_a_runs_trace_has_one_root_and_every_other_span_hangs_from_a_span_of_the_trace(self, mocker: MockerFixture) -> None:
        """The tracking plan's "exactly one root per run's trace": the root pipe, a nested pipe and its call make one tree."""
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id=None, run_identity_policy=RunIdentityPolicy.DIRECT)
        tracer = TracerProvider().get_tracer("test")
        root_pipe = tracer.start_span(
            name="PipeSequence: root",
            context=_virtual_root_context(),
            attributes={**_pipe_attributes(pipe_type="PipeSequence"), PipelexSpanAttr.RUN_ROOT: True},
        )
        nested_pipe = tracer.start_span(
            name="PipeLLM: nested", context=trace.set_span_in_context(root_pipe), attributes=_pipe_attributes(pipe_type="PipeLLM")
        )
        generation = tracer.start_span(
            name="nested: llm_gen_text (claude-4.5-sonnet) -> Text",
            context=trace.set_span_in_context(nested_pipe),
            attributes={PipelexSpanAttr.SPAN_CATEGORY: SpanCategory.INFERENCE.value, PipelexSpanAttr.PIPELINE_RUN_ID: "run-1"},
        )
        generation.end()
        nested_pipe.end()
        root_pipe.end()

        exporter.export([cast("SdkSpan", generation), cast("SdkSpan", nested_pipe), cast("SdkSpan", root_pipe)])

        captures = [call.kwargs["properties"] for call in client.capture.call_args_list]
        assert len(captures) == 4
        roots = [properties for properties in captures if PostHogAttr.PARENT_ID not in properties]
        assert len(roots) == 1
        assert roots[0][PostHogAttr.SPAN_ID] == make_trace_root_span_id(trace_id=_TRACE_ID, pipeline_run_id="run-1")
        span_ids = {properties[PostHogAttr.SPAN_ID] for properties in captures}
        assert all(properties[PostHogAttr.PARENT_ID] in span_ids for properties in captures if properties is not roots[0])
        assert {properties[PostHogAttr.TRACE_ID] for properties in captures} == {f"{_TRACE_ID:032x}"}

    def test_every_span_carries_a_non_negative_latency(self, mocker: MockerFixture) -> None:
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id=None, run_identity_policy=RunIdentityPolicy.DIRECT)

        exporter.export(
            [
                _pipe_span_under(parent_span_id=OTelConstants.OTEL_VIRTUAL_ROOT_PARENT_SPAN_ID, is_run_root=True),
                _make_span(span_category=SpanCategory.PIPE),
                _generation_span(name="some_pipe: llm_gen_text (claude-4.5-sonnet) -> Text", attributes={}),
            ]
        )

        assert len(client.capture.call_args_list) == 4
        for call in client.capture.call_args_list:
            latency = call.kwargs["properties"][PostHogAttr.LATENCY]
            assert isinstance(latency, float)
            assert latency >= 0

    def test_the_trace_root_lasts_as_long_as_the_runs_root_pipe_and_is_dated_at_its_start(self, mocker: MockerFixture) -> None:
        """PostHog names a trace after its earliest event and times it by its root, so the root carries both."""
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id=None, run_identity_policy=RunIdentityPolicy.DIRECT)
        root_pipe = (
            TracerProvider()
            .get_tracer("test")
            .start_span(
                name="PipeSequence: root",
                context=_virtual_root_context(),
                attributes={**_pipe_attributes(pipe_type="PipeSequence"), PipelexSpanAttr.RUN_ROOT: True},
                start_time=_STARTED_AT_NS,
            )
        )
        root_pipe.end(end_time=_STARTED_AT_NS + 2_500_000_000)

        exporter.export([cast("SdkSpan", root_pipe)])

        root_capture = _trace_root_capture(client)
        assert root_capture.kwargs["properties"][PostHogAttr.LATENCY] == 2.5
        assert root_capture.kwargs["timestamp"] == datetime.fromtimestamp(_STARTED_AT_NS / 1e9, tz=UTC)
        pipe_capture = next(call for call in client.capture.call_args_list if call is not root_capture)
        assert pipe_capture.kwargs["properties"][PostHogAttr.LATENCY] == 2.5
        assert pipe_capture.kwargs["timestamp"] is None

    def test_the_trace_root_is_the_trace_and_no_pipe(self, mocker: MockerFixture) -> None:
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id=None, run_identity_policy=RunIdentityPolicy.DIRECT)

        exporter.export([_pipe_span_under(parent_span_id=OTelConstants.OTEL_VIRTUAL_ROOT_PARENT_SPAN_ID, is_run_root=True, method_id="mt_invoices")])

        root_capture = _trace_root_capture(client)
        properties = root_capture.kwargs["properties"]
        assert root_capture.kwargs["event"] == PostHogEvent.SPAN
        assert properties[PostHogAttr.SPAN_NAME] == properties[PostHogAttr.TRACE_NAME] == "root_abc12345"
        assert properties[PostHogAttr.PIPELINE_RUN_ID] == "run-1"
        assert properties["method_id"] == "mt_invoices"
        assert properties[PostHogAttr.PIPELEX_VERSION] == get_package_version()
        assert not {"pipe_type", "pipe_category", "pipe_code", "pipe_id", "outcome"} & set(properties)
        # Deduplicated on its span id, as every `$ai_span` is.
        assert root_capture.kwargs["uuid"] == str(uuid.uuid5(EVENT_UUID_NAMESPACE, f"$ai_span:{properties[PostHogAttr.SPAN_ID]}"))

    def test_the_trace_root_of_a_run_with_no_method_names_it_as_null(self, mocker: MockerFixture) -> None:
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id=None, run_identity_policy=RunIdentityPolicy.DIRECT)

        exporter.export([_pipe_span_under(parent_span_id=OTelConstants.OTEL_VIRTUAL_ROOT_PARENT_SPAN_ID, is_run_root=True)])

        properties = _trace_root_capture(client).kwargs["properties"]
        assert "method_id" in properties
        assert properties["method_id"] is None

    @pytest.mark.parametrize(
        ("redact_pipe_codes", "capture_pipe_codes", "expected_trace_name"),
        [
            (True, None, "abc12345"),
            (False, None, "root_abc12345"),
            (True, True, "root_abc12345"),
            (False, False, "abc12345"),
        ],
    )
    def test_the_trace_root_names_the_trace_as_the_run_allows(
        self, mocker: MockerFixture, redact_pipe_codes: bool, capture_pipe_codes: bool | None, expected_trace_name: str
    ) -> None:
        client = mocker.MagicMock(spec=Posthog)
        exporter = PostHogSpanExporter(
            posthog_client=client,
            fallback_distinct_id=None,
            run_identity_policy=RunIdentityPolicy.DIRECT,
            redaction_config=_FULL_CAPTURE.model_copy(update={"redact_pipe_codes": redact_pipe_codes}),
        )

        exporter.export(
            [_pipe_span_under(parent_span_id=OTelConstants.OTEL_VIRTUAL_ROOT_PARENT_SPAN_ID, is_run_root=True, capture_pipe_codes=capture_pipe_codes)]
        )

        properties = _trace_root_capture(client).kwargs["properties"]
        assert properties[PostHogAttr.SPAN_NAME] == properties[PostHogAttr.TRACE_NAME] == expected_trace_name

    def test_the_trace_root_lands_on_the_runs_person_and_groups(self, mocker: MockerFixture) -> None:
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id="deployment-hash", run_identity_policy=RunIdentityPolicy.DIRECT)

        exporter.export(
            [
                _pipe_span_under(
                    parent_span_id=OTelConstants.OTEL_VIRTUAL_ROOT_PARENT_SPAN_ID,
                    is_run_root=True,
                    extra_attributes={
                        PipelexSpanAttr.RUN_USER_ID: "user-42",
                        PipelexSpanAttr.RUN_EXTRAS: '{"organization": "org_acme"}',
                    },
                )
            ]
        )

        for call in client.capture.call_args_list:
            assert call.kwargs["distinct_id"] == "user-42"
            assert call.kwargs["groups"] == {"organization": "org_acme"}
            assert "user-42" not in repr(call.kwargs["properties"])

    def test_an_anonymous_stream_sends_the_trace_root_without_a_person(self, mocker: MockerFixture) -> None:
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id="left-behind-id", run_identity_policy=RunIdentityPolicy.NONE)

        exporter.export([_pipe_span_under(parent_span_id=OTelConstants.OTEL_VIRTUAL_ROOT_PARENT_SPAN_ID, is_run_root=True)])

        root_capture = _trace_root_capture(client)
        assert "distinct_id" not in root_capture.kwargs
        assert root_capture.kwargs["properties"][PostHogAttr.PROCESS_PERSON_PROFILE] is False

    def test_two_runs_sharing_a_host_trace_keep_a_root_each(self, mocker: MockerFixture) -> None:
        """Runs that joined one host's trace share its trace id, so each run's root is told apart by its run."""
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id=None, run_identity_policy=RunIdentityPolicy.DIRECT)

        exporter.export(
            [
                _pipe_span_under(parent_span_id=0x00000000000000CD, is_run_root=True),
                _pipe_span_under(parent_span_id=0x00000000000000CD, is_run_root=True, extra_attributes={PipelexSpanAttr.PIPELINE_RUN_ID: "run-2"}),
            ]
        )

        captures = [call.kwargs["properties"] for call in client.capture.call_args_list]
        roots = {properties[PostHogAttr.PIPELINE_RUN_ID]: properties for properties in captures if PostHogAttr.PARENT_ID not in properties}
        assert set(roots) == {"run-1", "run-2"}
        assert roots["run-1"][PostHogAttr.SPAN_ID] != roots["run-2"][PostHogAttr.SPAN_ID]
        for properties in captures:
            if PostHogAttr.PARENT_ID in properties:
                assert properties[PostHogAttr.PARENT_ID] == roots[properties["pipeline_run_id"]][PostHogAttr.SPAN_ID]

    def test_a_pipe_span_that_is_not_its_runs_root_sends_no_trace_root(self, mocker: MockerFixture) -> None:
        """A nested pipe, or the first pipe of a run started inside a running pipe, which joins that pipe's tree."""
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id=None, run_identity_policy=RunIdentityPolicy.DIRECT)

        exporter.export([_pipe_span_under(parent_span_id=0x00000000000000AB, is_run_root=False)])

        client.capture.assert_called_once()
        assert client.capture.call_args.kwargs["properties"].get("pipe_type") == "PipeSequence"

    def test_the_provider_is_the_serving_provider_alone_and_the_model_its_id(self, mocker: MockerFixture) -> None:
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id=None, run_identity_policy=RunIdentityPolicy.DIRECT)

        exporter.export([_generation_span(name="some_pipe: llm_gen_text (claude-4.5-sonnet) -> Text", attributes={})])

        properties = client.capture.call_args.kwargs["properties"]
        assert properties[PostHogAttr.PROVIDER] == "pipelex_gateway"
        assert properties[PostHogAttr.MODEL] == "claude-sonnet-4-5"
        assert properties[PostHogAttr.MODEL_HANDLE] == "claude-4.5-sonnet"
        assert properties[PostHogAttr.INFERENCE_BACKEND] == "pipelex_gateway"
        assert properties[PostHogAttr.INFERENCE_KIND] == "llm"
        assert properties[PostHogAttr.PIPELEX_VERSION] == get_package_version()
        assert "$ai_model_id" not in properties

    def test_the_usage_cost_and_attempts_ride_the_generation(self, mocker: MockerFixture) -> None:
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id=None, run_identity_policy=RunIdentityPolicy.DIRECT)

        exporter.export(
            [
                _generation_span(
                    name="some_pipe: llm_gen_object (claude-4.5-sonnet) -> Invoice",
                    attributes={
                        GenAISpanAttr.USAGE_INPUT_TOKENS: 3600,
                        GenAISpanAttr.USAGE_OUTPUT_TOKENS: 900,
                        PipelexSpanAttr.INPUT_COST_USD: 0.0108,
                        PipelexSpanAttr.OUTPUT_COST_USD: 0.0135,
                        PipelexSpanAttr.TOTAL_COST_USD: 0.0243,
                        PipelexSpanAttr.ATTEMPT_COUNT: 3,
                    },
                )
            ]
        )

        properties = client.capture.call_args.kwargs["properties"]
        assert (properties[PostHogAttr.INPUT_TOKENS], properties[PostHogAttr.OUTPUT_TOKENS]) == (3600, 900)
        assert (properties[PostHogAttr.INPUT_COST_USD], properties[PostHogAttr.OUTPUT_COST_USD]) == (0.0108, 0.0135)
        assert properties[PostHogAttr.TOTAL_COST_USD] == 0.0243
        assert properties[PostHogAttr.ATTEMPT_COUNT] == 3
        assert (properties[PostHogAttr.IS_ERROR], properties[PostHogAttr.ERROR]) == (False, None)

    def test_a_failed_generation_names_its_category_and_never_its_message(self, mocker: MockerFixture) -> None:
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id=None, run_identity_policy=RunIdentityPolicy.DIRECT)
        tracer = TracerProvider().get_tracer("test")
        span = tracer.start_span(
            name="some_pipe: llm_gen_text (claude-4.5-sonnet) -> Text",
            attributes={PipelexSpanAttr.SPAN_CATEGORY: SpanCategory.INFERENCE.value, GenAISpanAttr.ERROR_TYPE: "capacity"},
        )
        span.set_status(Status(StatusCode.ERROR, "quota exhausted for org_secret"))
        span.end()
        assert isinstance(span, SdkSpan)

        exporter.export([span])

        properties = client.capture.call_args.kwargs["properties"]
        assert (properties[PostHogAttr.IS_ERROR], properties[PostHogAttr.ERROR]) == (True, "capacity")
        assert "org_secret" not in repr(properties)

    def test_a_redacted_name_keeps_the_output_type_of_a_call_with_no_class(self, mocker: MockerFixture) -> None:
        client = mocker.MagicMock(spec=Posthog)
        exporter = PostHogSpanExporter(
            posthog_client=client,
            fallback_distinct_id=None,
            run_identity_policy=RunIdentityPolicy.DIRECT,
            redaction_config=TelemetryRedactionConfig(
                redact_content=True, redact_pipe_codes=True, redact_output_class_names=True, content_max_length=None
            ),
        )

        exporter.export([_generation_span(name="some_pipe: img_gen (flux-pro) -> Image", attributes={PipelexSpanAttr.UNIT_JOB_ID: "img_gen"})])

        assert client.capture.call_args.kwargs["properties"][PostHogAttr.SPAN_NAME] == "img_gen (claude-4.5-sonnet) -> Image"

    def test_a_pipe_span_is_deduplicated_on_its_span_id(self, mocker: MockerFixture) -> None:
        """Rule 7's backstop: `$ai_span`'s uuid is a UUIDv5 of `"$ai_span:<$ai_span_id>"`, the same for every copy of one span."""
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id="deployment-hash", run_identity_policy=RunIdentityPolicy.DIRECT)
        span = _make_span(span_category=SpanCategory.PIPE)

        exporter.export([span])
        exporter.export([span])

        first_call, second_call = client.capture.call_args_list
        span_id = first_call.kwargs["properties"][PostHogAttr.SPAN_ID]
        assert first_call.kwargs["uuid"] == str(uuid.uuid5(EVENT_UUID_NAMESPACE, f"$ai_span:{span_id}"))
        assert second_call.kwargs["uuid"] == first_call.kwargs["uuid"]

    def test_an_anonymous_pipe_span_is_deduplicated_too(self, mocker: MockerFixture) -> None:
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id=None, run_identity_policy=RunIdentityPolicy.DIRECT)

        exporter.export([_make_span(span_category=SpanCategory.PIPE)])

        span_id = client.capture.call_args.kwargs["properties"][PostHogAttr.SPAN_ID]
        assert client.capture.call_args.kwargs["uuid"] == str(uuid.uuid5(EVENT_UUID_NAMESPACE, f"$ai_span:{span_id}"))

    def test_two_pipe_spans_get_two_uuids(self, mocker: MockerFixture) -> None:
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id="deployment-hash", run_identity_policy=RunIdentityPolicy.DIRECT)

        exporter.export([_make_span(span_category=SpanCategory.PIPE), _make_span(span_category=SpanCategory.PIPE)])

        first_call, second_call = client.capture.call_args_list
        assert first_call.kwargs["uuid"] != second_call.kwargs["uuid"]

    def test_a_generation_names_no_uuid_the_tracking_plan_gives_it_no_key(self, mocker: MockerFixture) -> None:
        client = mocker.MagicMock(spec=Posthog)
        exporter = _make_exporter(client=client, fallback_distinct_id="deployment-hash", run_identity_policy=RunIdentityPolicy.DIRECT)

        exporter.export([_make_span(span_category=SpanCategory.INFERENCE)])

        assert client.capture.call_args.kwargs["event"] == PostHogEvent.GENERATION
        assert client.capture.call_args.kwargs["uuid"] is None
