"""PostHog span exporter for OpenTelemetry.

This module provides a SpanExporter that sends OTel spans to PostHog
as $ai_generation or $ai_span events, plus one root `$ai_span` per run's trace.

A run's trace on this stream is one tree. Its root is the trace's own `$ai_span`, which no OpenTelemetry span
backs: the exporter sends it when it exports the run's root pipe span, the span marked `pipelex.run_root`, with that
pipe's latency, timestamped at that pipe's start so it is the trace's earliest event, and under a span id derived from
the trace and the run (`make_trace_root_span_id`). The run's root pipe span names that root as its parent, and every other span
names the Pipelex span it ran under, so the tracking plan's "exactly one root per run's trace" holds whichever
process exports the root pipe span: the one that ran the run in process, or an orchestrator's worker that ran it in
workflow code, where only the live execution exports it (`pipelex.system.telemetry.replay_safe_spans`).
"""

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any, Final, Mapping, Sequence, cast

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import StatusCode
from posthog import Posthog
from typing_extensions import override

from pipelex import log
from pipelex.system.telemetry.otel_constants import (
    GenAISpanAttr,
    OTelAttributeValue,
    OTelConstants,
    PipelexSpanAttr,
    PostHogAttr,
    PostHogEvent,
    SpanCategory,
)
from pipelex.system.telemetry.telemetry_config import TelemetryRedactionConfig
from pipelex.system.telemetry.telemetry_identity import RunIdentityPolicy, TelemetryIdentity
from pipelex.tools.log.error_fields import error_fields
from pipelex.tools.misc.package_utils import get_package_version

# The namespace of the deterministic event uuids PostHog deduplicates on, the same fixed, arbitrary UUID the hosted
# plane's own emitters derive theirs from. NEVER change it: a new namespace re-enables the double counts it stops.
EVENT_UUID_NAMESPACE: Final[uuid.UUID] = uuid.UUID("6f5c1f3a-3a2e-4f1b-9c0d-8a7b6e5d4c3b")


def make_trace_root_span_id(*, trace_id: int, pipeline_run_id: str) -> str:
    """The span id of a run's trace root `$ai_span`, derived from the trace and the run, so every copy of one root carries the same one.

    The root is no OpenTelemetry span, so it has no span id of its own: this one is the first 16 hexadecimal digits of
    the MD5 digest of the trace id and the run id, the width of a span id. The run id is in it because several runs can
    share one trace, those that joined one host's trace, and each keeps a root of its own. The run's root pipe span names
    it as its parent.
    """
    return hashlib.md5(f"trace-root:{trace_id:032x}:{pipeline_run_id}".encode(), usedforsecurity=False).hexdigest()[:16]


def make_span_event_uuid(*, span_id: str) -> str:
    """The uuid of a pipe's ``$ai_span`` event, a UUIDv5 of ``"$ai_span:<$ai_span_id>"``.

    A pipe's span is exported once, by the execution that ran it to its end, even across a replay of workflow code
    (see ``pipelex.system.telemetry.replay_safe_spans``); the uuid is the tracking plan's backstop against the PostHog
    client delivering the same capture twice, and never the guarantee.
    """
    return str(uuid.uuid5(EVENT_UUID_NAMESPACE, f"{PostHogEvent.SPAN}:{span_id}"))


class PostHogSpanExporter(SpanExporter):
    """Exports OTel spans to PostHog as $ai_generation or $ai_span events.

    Applies redaction rules from TelemetryRedactionConfig before sending events,
    and attributes each span to the run that produced it — see
    :mod:`pipelex.system.telemetry.telemetry_identity`. The exporter is built
    with the operator's configured id as its fallback and the policy their mode
    implies.
    """

    def __init__(
        self,
        *,
        posthog_client: Posthog,
        fallback_distinct_id: str | None,
        run_identity_policy: RunIdentityPolicy,
        redaction_config: TelemetryRedactionConfig,
    ):
        """Build an exporter for one PostHog stream.

        Args:
            posthog_client: The client this exporter captures through.
            fallback_distinct_id: The identity for a span that names no run —
                this used to be the identity for every span on the stream.
            run_identity_policy: What this stream may do with a span's own user.
                `NONE` on an operator's stream in `anonymous` mode, where the
                operator chose not to identify people at all; `DIRECT`
                otherwise.
            redaction_config: What this stream is allowed to see.
        """
        self.posthog_client = posthog_client
        self.fallback_distinct_id = fallback_distinct_id
        self.run_identity_policy = run_identity_policy
        self.redaction_config = redaction_config

    def _resolve_identity(self, *, attributes: Mapping[str, OTelAttributeValue]) -> TelemetryIdentity:
        """Resolve who this span belongs to on this stream."""
        return TelemetryIdentity.make_from_span_attributes(
            attributes=attributes,
            fallback_distinct_id=self.fallback_distinct_id,
            run_identity_policy=self.run_identity_policy,
        )

    def _resolve_redaction(self, *, attributes: Mapping[str, OTelAttributeValue]) -> TelemetryRedactionConfig:
        """What this span may show on this stream: the run's own pipe-code setting, when the span carries one, else the stream's.

        A host may set `capture_pipe_codes` for a run (`RunMetadata.capture_pipe_codes`), and the span site writes it on
        the span as `pipelex.run.capture_pipe_codes`, in whichever process made the span. When present it decides both
        the pipe codes and the output class names, which name the method's concepts as the codes name its pipes; when
        absent, the stream's configured redaction stands.
        """
        run_capture_pipe_codes = attributes.get(PipelexSpanAttr.RUN_CAPTURE_PIPE_CODES)
        if not isinstance(run_capture_pipe_codes, bool):
            return self.redaction_config
        return self.redaction_config.model_copy(
            update={
                "redact_pipe_codes": not run_capture_pipe_codes,
                "redact_output_class_names": not run_capture_pipe_codes,
            }
        )

    def _add_method_properties(self, *, properties: dict[str, Any], attributes: Mapping[str, OTelAttributeValue]) -> None:
        """Add the run's `method_id`, null when it has none, and the pipe's `pipe_id`, left out when the runtime has no key.

        Neither is content: the host's opaque id of the stored method, and a keyed digest of the pipe
        (`pipelex.system.telemetry.pipe_identity`). So neither is redacted.
        """
        properties["method_id"] = attributes.get(PipelexSpanAttr.RUN_METHOD_ID)
        if (pipe_id := attributes.get(PipelexSpanAttr.PIPE_ID)) is not None:
            properties["pipe_id"] = pipe_id

    def _capture_event(
        self,
        event: PostHogEvent,
        *,
        properties: dict[str, Any],
        identity: TelemetryIdentity,
        event_uuid: str | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        """Capture an event to PostHog, handling anonymous vs identified users.

        PostHog requires a valid distinct_id - passing None will cause the event to be rejected.
        For anonymous tracking, we omit distinct_id and set $process_person_profile=False.

        The identity lands in the fields PostHog reserves for it — `distinct_id`
        and `groups` — and in no property: a property cannot produce a group-level
        count after the fact, and a second copy of the user id is a second thing
        to keep in step.

        An ``event_uuid`` is the event's deduplication key, derived from the event's own identity; without one, the
        client generates a random uuid. A ``timestamp`` dates the event when it happened before it is sent; without
        one, the client dates it now.
        """
        if identity.distinct_id:
            # Identified user: pass distinct_id, and the entities the run belongs to
            self.posthog_client.capture(
                distinct_id=identity.distinct_id,
                event=event,
                properties=properties,
                groups=identity.groups or None,
                uuid=event_uuid,
                timestamp=timestamp,
            )
        else:
            # Anonymous user: don't pass distinct_id, mark as anonymous
            properties[PostHogAttr.PROCESS_PERSON_PROFILE] = False
            self.posthog_client.capture(
                event=event,
                properties=properties,
                uuid=event_uuid,
                timestamp=timestamp,
            )

    def _truncate_content(self, content: str) -> str:
        """Truncate content if it exceeds max length.

        Args:
            content: The content string to potentially truncate.

        Returns:
            The original content if no limit is set or within limit,
            otherwise truncated content with suffix.
        """
        max_length = self.redaction_config.content_max_length
        if max_length is None or len(content) <= max_length:
            return content
        truncate_at = max(0, max_length - len(OTelConstants.TRUNCATION_SUFFIX))
        return content[:truncate_at] + OTelConstants.TRUNCATION_SUFFIX

    def _apply_content_redaction(self, properties: dict[str, Any]) -> None:
        """Apply content redaction to properties in place.

        Removes or truncates content fields based on redaction config.

        Args:
            properties: The properties dict to modify in place.
        """
        if self.redaction_config.redact_content:
            # Remove content fields entirely
            properties.pop(PostHogAttr.INPUT, None)
            properties.pop(PostHogAttr.OUTPUT_CHOICES, None)
        else:
            # Apply truncation if content exists
            if properties.get(PostHogAttr.INPUT):
                properties[PostHogAttr.INPUT] = self._truncate_content(str(properties[PostHogAttr.INPUT]))
            if properties.get(PostHogAttr.OUTPUT_CHOICES):
                properties[PostHogAttr.OUTPUT_CHOICES] = self._truncate_content(str(properties[PostHogAttr.OUTPUT_CHOICES]))

    def _build_redacted_pipe_span_name(
        self,
        original_span_name: str,
        *,
        pipe_type: str | None,
        redaction: TelemetryRedactionConfig,
    ) -> str:
        """Build a redacted span name for pipe spans.

        Pipe span names follow the format: "{pipe_type}: {pipe_code}"
        This method rebuilds the name with redacted pipe code if needed.

        Args:
            original_span_name: The original span name from OTel.
            pipe_type: The pipe type from attributes.
            redaction: What this span may show (`_resolve_redaction`).

        Returns:
            The span name with redacted pipe code if redaction is enabled,
            otherwise the original span name.
        """
        if not redaction.redact_pipe_codes:
            return original_span_name

        # Rebuild with redacted pipe code
        if pipe_type:
            return pipe_type
        else:
            return OTelConstants.PIPE_CODE_REDACTED

    def _build_redacted_generation_span_name(
        self,
        original_span_name: str,
        *,
        pipe_code: str | None,
        unit_job_id: str | None,
        model_name: str | None,
        output_class_name: str | None,
        redaction: TelemetryRedactionConfig,
    ) -> str:
        """Build a redacted span name for generation spans.

        Generation span names follow the format:
        "{pipe_code}: {unit_job_id} ({model_handle}) -> {output_desc}"
        where output_desc is the output type or the output class name.

        Args:
            original_span_name: The original span name from OTel.
            pipe_code: The original pipe code from attributes.
            unit_job_id: The unit job ID (e.g., "LLM_GEN_TEXT").
            model_name: The model name.
            output_class_name: The output class name (for object generation).
            redaction: What this span may show (`_resolve_redaction`).

        Returns:
            The span name with redacted parts based on redaction config.
        """
        redact_pipe_codes = redaction.redact_pipe_codes
        redact_class_names = redaction.redact_output_class_names

        if not redact_pipe_codes and not redact_class_names:
            return original_span_name

        # Build output description
        if output_class_name:
            display_output = OTelConstants.OUTPUT_CLASS_REDACTED if redact_class_names else output_class_name
        else:
            # No class: the name ends with the output type, `Text`, `Image`, `Pages`, `Document` or a judgment's `Object`, which names no content
            display_output = original_span_name.rsplit(" -> ", 1)[-1] if " -> " in original_span_name else "text"

        # Build redacted pipe code
        if redact_pipe_codes:
            return f"{unit_job_id or 'unknown'} ({model_name or 'unknown'}) -> {display_output}"
        elif pipe_code:
            return f"{pipe_code}: {unit_job_id or 'unknown'} ({model_name or 'unknown'}) -> {display_output}"
        else:
            return f"{unit_job_id or 'unknown'} ({model_name or 'unknown'}) -> {display_output}"

    def _get_redacted_pipe_code(self, pipe_code: str | None, *, redaction: TelemetryRedactionConfig) -> str | None:
        """Get the pipe code, redacted if config requires it.

        Args:
            pipe_code: The original pipe code.
            redaction: What this span may show (`_resolve_redaction`).

        Returns:
            The original pipe code or redacted value based on config.
        """
        if not redaction.redact_pipe_codes:
            return pipe_code
        return OTelConstants.PIPE_CODE_REDACTED if pipe_code else None

    def _get_redacted_output_class_name(self, output_class_name: str | None, *, redaction: TelemetryRedactionConfig) -> str | None:
        """Get the output class name, redacted if config requires it.

        Args:
            output_class_name: The original output class name.
            redaction: What this span may show (`_resolve_redaction`).

        Returns:
            The original output class name or redacted value based on config.
        """
        if not redaction.redact_output_class_names:
            return output_class_name
        return OTelConstants.PIPE_CODE_REDACTED if output_class_name else None

    def _get_base_properties(
        self, span: ReadableSpan, *, attributes: Mapping[str, OTelAttributeValue], redaction: TelemetryRedactionConfig
    ) -> dict[str, Any]:
        """Get common properties for all span types, the runtime's version and the span's latency among them."""
        properties: dict[str, Any] = {
            PostHogAttr.PIPELEX_VERSION: get_package_version(),
            PostHogAttr.LATENCY: self._get_latency_seconds(span=span),
        }

        # Add trace/span IDs for PostHog trace grouping
        span_context = span.get_span_context()
        if span_context and span_context.is_valid:
            properties[PostHogAttr.TRACE_ID] = f"{span_context.trace_id:032x}"
            properties[PostHogAttr.SPAN_ID] = f"{span_context.span_id:016x}"
            properties[PostHogAttr.TRACE_NAME] = self._get_trace_name(attributes=attributes, redaction=redaction)

        # Add parent span ID for trace hierarchy. A run's root pipe span has a parent this stream never receives,
        # the virtual root parent that sets a run's own trace id, or a host's span the run joined, so it names the
        # trace's root `$ai_span` instead, which this exporter sends beside it (`_export_trace_root`): the run keeps
        # one root here either way. A run started inside a running pipe keeps its parent, that pipe's span, which
        # this stream receives: its first span carries no run-root mark.
        if attributes.get(PipelexSpanAttr.RUN_ROOT) is True:
            if span_context and span_context.is_valid:
                properties[PostHogAttr.PARENT_ID] = self._get_trace_root_span_id(trace_id=span_context.trace_id, attributes=attributes)
        elif span.parent and span.parent.span_id != OTelConstants.OTEL_VIRTUAL_ROOT_PARENT_SPAN_ID:
            properties[PostHogAttr.PARENT_ID] = f"{span.parent.span_id:016x}"

        return properties

    @staticmethod
    def _get_latency_seconds(*, span: ReadableSpan) -> float:
        """The seconds the span took, never negative, and 0 for a span that names no start or no end, which an ended span always names."""
        if span.start_time is None or span.end_time is None:
            return 0.0
        return max(0.0, (span.end_time - span.start_time) / 1e9)

    @staticmethod
    def _get_trace_root_span_id(*, trace_id: int, attributes: Mapping[str, OTelAttributeValue]) -> str:
        """The span id of the trace root of the run this span belongs to (`make_trace_root_span_id`)."""
        return make_trace_root_span_id(trace_id=trace_id, pipeline_run_id=str(attributes.get(PipelexSpanAttr.PIPELINE_RUN_ID, "")))

    @staticmethod
    def _get_trace_name(*, attributes: Mapping[str, OTelAttributeValue], redaction: TelemetryRedactionConfig) -> OTelAttributeValue | None:
        """The trace's name as this span may show it: the full name with the pipe code, or the redacted one without it."""
        if redaction.redact_pipe_codes:
            return attributes.get(PipelexSpanAttr.TRACE_NAME_REDACTED)
        return attributes.get(PipelexSpanAttr.TRACE_NAME)

    def _export_generation_span(self, span: ReadableSpan, *, attributes: Mapping[str, OTelAttributeValue]) -> None:
        """Export a generation span, one inference call of any kind, as `$ai_generation`.

        `$ai_provider` is the span's `gen_ai.provider.name`, the serving provider, and `$ai_model` the model id the call
        asked it for; the Pipelex handle and backend ride `model_handle` and `inference_backend`. The tokens and their
        cost are the ones the span recorded, summed over every attempt of the call. A failed call says so in
        `$ai_is_error`, and names its inference error category, the span's `error.type`, in `$ai_error`, never a message.
        """
        redaction = self._resolve_redaction(attributes=attributes)
        properties = self._get_base_properties(span=span, attributes=attributes, redaction=redaction)

        # Get raw attribute values for redaction
        pipe_code = cast("str | None", attributes.get(PipelexSpanAttr.PIPE_CODE))
        output_class_name = cast("str | None", attributes.get(PipelexSpanAttr.OUTPUT_CLASS_NAME))
        unit_job_id = cast("str | None", attributes.get(PipelexSpanAttr.UNIT_JOB_ID) or attributes.get(GenAISpanAttr.OPERATION_NAME))
        model_handle = cast("str | None", attributes.get(PipelexSpanAttr.MODEL_HANDLE))
        is_error = span.status.status_code == StatusCode.ERROR

        properties.update(
            {
                PostHogAttr.MODEL: attributes.get(GenAISpanAttr.REQUEST_MODEL),
                PostHogAttr.PROVIDER: attributes.get(GenAISpanAttr.PROVIDER_NAME),
                PostHogAttr.TEMPERATURE: attributes.get(GenAISpanAttr.REQUEST_TEMPERATURE),
                PostHogAttr.MAX_TOKENS: attributes.get(GenAISpanAttr.REQUEST_MAX_TOKENS),
                PostHogAttr.SEED: attributes.get(GenAISpanAttr.REQUEST_SEED),
                PostHogAttr.OUTPUT_TYPE: attributes.get(GenAISpanAttr.OUTPUT_TYPE),
                PostHogAttr.INPUT_TOKENS: attributes.get(GenAISpanAttr.USAGE_INPUT_TOKENS),
                PostHogAttr.OUTPUT_TOKENS: attributes.get(GenAISpanAttr.USAGE_OUTPUT_TOKENS),
                PostHogAttr.INPUT_COST_USD: attributes.get(PipelexSpanAttr.INPUT_COST_USD),
                PostHogAttr.OUTPUT_COST_USD: attributes.get(PipelexSpanAttr.OUTPUT_COST_USD),
                PostHogAttr.TOTAL_COST_USD: attributes.get(PipelexSpanAttr.TOTAL_COST_USD),
                PostHogAttr.ATTEMPT_COUNT: attributes.get(PipelexSpanAttr.ATTEMPT_COUNT, 1),
                PostHogAttr.IS_ERROR: is_error,
                PostHogAttr.ERROR: attributes.get(GenAISpanAttr.ERROR_TYPE) if is_error else None,
                PostHogAttr.INFERENCE_KIND: attributes.get(PipelexSpanAttr.INFERENCE_KIND),
                PostHogAttr.INFERENCE_BACKEND: attributes.get(PipelexSpanAttr.INFERENCE_BACKEND),
                PostHogAttr.MODEL_HANDLE: model_handle,
            }
        )

        # Add content if available
        if prompt := attributes.get(GenAISpanAttr.PROMPT_CONTENT):
            properties[PostHogAttr.INPUT] = prompt
        if completion := attributes.get(GenAISpanAttr.COMPLETION_CONTENT):
            properties[PostHogAttr.OUTPUT_CHOICES] = completion

        # Apply content redaction (removes or truncates content)
        self._apply_content_redaction(properties)

        # Build redacted span name for display
        redacted_span_name = self._build_redacted_generation_span_name(
            original_span_name=span.name,
            pipe_code=pipe_code,
            unit_job_id=unit_job_id,
            model_name=model_handle,
            output_class_name=output_class_name,
            redaction=redaction,
        )
        properties[PostHogAttr.SPAN_NAME] = redacted_span_name

        # Apply pipe code and output class name redaction to properties (only add if not None)
        if redacted_pipe_code := self._get_redacted_pipe_code(pipe_code, redaction=redaction):
            properties["pipe_code"] = redacted_pipe_code
        if redacted_output_class_name := self._get_redacted_output_class_name(output_class_name, redaction=redaction):
            properties["output_class_name"] = redacted_output_class_name

        # Add pipeline_run_id (never redacted - useful for debugging and correlation)
        properties[PostHogAttr.PIPELINE_RUN_ID] = attributes.get(PipelexSpanAttr.PIPELINE_RUN_ID)
        self._add_method_properties(properties=properties, attributes=attributes)

        self._capture_event(
            event=PostHogEvent.GENERATION,
            properties=properties,
            identity=self._resolve_identity(attributes=attributes),
        )

    def _export_pipe_span(self, span: ReadableSpan, *, attributes: Mapping[str, OTelAttributeValue]) -> None:
        """Export a pipe execution span."""
        redaction = self._resolve_redaction(attributes=attributes)
        properties = self._get_base_properties(span=span, attributes=attributes, redaction=redaction)

        # Get raw attribute values for redaction
        pipe_code = cast("str | None", attributes.get(PipelexSpanAttr.PIPE_CODE))
        pipe_type = cast("str | None", attributes.get(PipelexSpanAttr.PIPE_TYPE))

        # Build redacted span name
        redacted_span_name = self._build_redacted_pipe_span_name(
            original_span_name=span.name,
            pipe_type=pipe_type,
            redaction=redaction,
        )

        # Add pipeline_run_id (never redacted - useful for debugging and correlation)
        pipeline_run_id = attributes.get(PipelexSpanAttr.PIPELINE_RUN_ID)

        properties[PostHogAttr.SPAN_NAME] = redacted_span_name
        properties["pipe_type"] = pipe_type
        properties["pipe_category"] = attributes.get(PipelexSpanAttr.PIPE_CATEGORY)
        properties["outcome"] = attributes.get(PipelexSpanAttr.OUTCOME)
        properties["pipeline_run_id"] = pipeline_run_id
        self._add_method_properties(properties=properties, attributes=attributes)

        # Apply pipe code redaction (only add if not None, for consistency)
        if redacted_pipe_code := self._get_redacted_pipe_code(pipe_code, redaction=redaction):
            properties["pipe_code"] = redacted_pipe_code

        # Deduplicated on `$ai_span_id`, as the tracking plan's rule 7 backstop.
        span_id = properties.get(PostHogAttr.SPAN_ID)
        identity = self._resolve_identity(attributes=attributes)
        if attributes.get(PipelexSpanAttr.RUN_ROOT) is True:
            self._export_trace_root(span=span, attributes=attributes, redaction=redaction, identity=identity)
        self._capture_event(
            event=PostHogEvent.SPAN,
            properties=properties,
            identity=identity,
            event_uuid=make_span_event_uuid(span_id=span_id) if isinstance(span_id, str) else None,
        )

    def _export_trace_root(
        self,
        *,
        span: ReadableSpan,
        attributes: Mapping[str, OTelAttributeValue],
        redaction: TelemetryRedactionConfig,
        identity: TelemetryIdentity,
    ) -> None:
        """Send the trace's root `$ai_span`, the one span of the run's trace without a parent, beside the run's root pipe span.

        It takes everything from that pipe span, which the run's every process marks the same way: the trace, the
        trace's name as the run allows it to be shown, the run, its method, the person and groups, and the pipe's
        latency, which is the run's. It is named after the trace, as PostHog names a trace after its earliest event, and
        dated at the pipe's start, so it is that earliest event whenever it arrives. It carries no pipe property, since
        it is the trace and no pipe, and it is deduplicated on its span id, derived from the trace and the run
        (`make_trace_root_span_id`), as every `$ai_span` is.
        """
        span_context = span.get_span_context()
        if not span_context or not span_context.is_valid:
            return
        trace_name = self._get_trace_name(attributes=attributes, redaction=redaction)
        root_span_id = self._get_trace_root_span_id(trace_id=span_context.trace_id, attributes=attributes)
        properties: dict[str, Any] = {
            PostHogAttr.PIPELEX_VERSION: get_package_version(),
            PostHogAttr.LATENCY: self._get_latency_seconds(span=span),
            PostHogAttr.TRACE_ID: f"{span_context.trace_id:032x}",
            PostHogAttr.SPAN_ID: root_span_id,
            PostHogAttr.SPAN_NAME: trace_name,
            PostHogAttr.TRACE_NAME: trace_name,
            PostHogAttr.PIPELINE_RUN_ID: attributes.get(PipelexSpanAttr.PIPELINE_RUN_ID),
            "method_id": attributes.get(PipelexSpanAttr.RUN_METHOD_ID),
        }
        start_time = datetime.fromtimestamp(span.start_time / 1e9, tz=UTC) if span.start_time is not None else None
        self._capture_event(
            event=PostHogEvent.SPAN,
            properties=properties,
            identity=identity,
            event_uuid=make_span_event_uuid(span_id=root_span_id),
            timestamp=start_time,
        )

    @override
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            return self._do_export(spans)
        except RuntimeError:
            # Gracefully handle the case where the logging/config system has already
            # been torn down (e.g. OTel background thread firing after Pipelex teardown).
            return SpanExportResult.SUCCESS

    def _do_export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        for span in spans:
            try:
                attributes = span.attributes or {}
                span_category_str = cast("str", attributes.get(PipelexSpanAttr.SPAN_CATEGORY))
                span_category = SpanCategory(span_category_str)

                match span_category:
                    case SpanCategory.INFERENCE:
                        self._export_generation_span(span=span, attributes=attributes)
                    case SpanCategory.PIPE:
                        self._export_pipe_span(span=span, attributes=attributes)

            except Exception as exc:  # ruff: ignore[blind-except]
                # Fail silently to avoid breaking app
                log.debug("A span could not be exported to PostHog", fields=error_fields(exc=exc))

        return SpanExportResult.SUCCESS

    @override
    def shutdown(self) -> None:
        pass
