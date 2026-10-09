"""OpenTelemetry constants for GenAI-compliant tracing.

This module defines attribute keys used for instrumenting LLM operations
with OpenTelemetry, following the GenAI semantic conventions. The keys and values are written out
rather than imported: `opentelemetry-semantic-conventions` deprecated its whole GenAI namespace when
those conventions moved to their own repository, which publishes no Python package.
"""

from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import TypeAlias

from pipelex.cogt.inference.inference_constants import InferenceOutputType

# OpenTelemetry's own `AttributeValue` is a chained assignment (`AnyValue = AttributeValue = ...`),
# which mypy refuses as a type; this alias spells out the same recursive union.
OTelAttributeValue: TypeAlias = str | bool | int | float | bytes | Sequence["OTelAttributeValue"] | Mapping[str, "OTelAttributeValue"] | None


class OTelConstants:
    """OpenTelemetry constants."""

    DEFAULT_USER_ID = "anonymous"
    SERVICE_NAME = "pipelex"
    SERVICE_NAMESPACE_KEY = "service.namespace"
    SERVICE_NAMESPACE = "ai.orchestration"
    INSTRUMENTING_MODULE_NAME = "pipelex"

    DO_NOT_TRACK_ENV_VAR_KEY = "DO_NOT_TRACK"
    PIPE_CODE_REDACTED = "[REDACTED]"
    OUTPUT_CLASS_REDACTED = "Object"
    TRUNCATION_SUFFIX = "... [truncated]"

    # Virtual parent span ID for root spans.
    # INVALID_SPAN_ID (0) makes SpanContext invalid, causing OTel to ignore our trace_id.
    # Using 1 as virtual parent ensures OTel uses our deterministic trace_id while
    # still treating the span as a root (we filter this out in the exporter).
    OTEL_VIRTUAL_ROOT_PARENT_SPAN_ID = 1

    LANGFUSE_CLOUD_URL = "https://cloud.langfuse.com"


class GenAISpanAttr(StrEnum):
    """OpenTelemetry GenAI semantic convention attribute keys."""

    OPERATION_NAME = "gen_ai.operation.name"
    PROVIDER_NAME = "gen_ai.provider.name"

    REQUEST_MODEL = "gen_ai.request.model"
    REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
    REQUEST_TEMPERATURE = "gen_ai.request.temperature"
    REQUEST_SEED = "gen_ai.request.seed"

    RESPONSE_MODEL = "gen_ai.response.model"
    OUTPUT_TYPE = "gen_ai.output.type"
    USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
    USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"

    # Content attributes for PostHog compatibility (not in standard semconv)
    # PostHog UI expects these as span attributes, not events
    PROMPT_CONTENT = "gen_ai.prompt.0.content"
    COMPLETION_CONTENT = "gen_ai.completion.0.content"


class OTelLogAttr(StrEnum):
    """OpenTelemetry semantic-convention attribute keys that name a log line's fields, written verbatim so an OTLP sink emits them untranslated.

    Only the keys more than one call site uses are here; a key used once is spelled at its call. The handled
    exception's `error.type` and `error.message` are `pipelex.tools.log.error_fields`'s, and the `gen_ai.*` keys
    are `GenAISpanAttr`'s.
    """

    FILE_PATH = "file.path"
    URL_FULL = "url.full"
    USER_ID = "user.id"
    HTTP_RESPONSE_STATUS_CODE = "http.response.status_code"


class PostHogAttr(StrEnum):
    """PostHog AI analytics attribute keys."""

    MODEL = "$ai_model"
    PROVIDER = "$ai_provider"
    INPUT_TOKENS = "$ai_input_tokens"
    OUTPUT_TOKENS = "$ai_output_tokens"
    HTTP_STATUS = "$ai_http_status"
    LATENCY = "$ai_latency"
    TRACE_ID = "$ai_trace_id"
    SPAN_ID = "$ai_span_id"
    TRACE_NAME = "$ai_trace_name"
    PARENT_ID = "$ai_parent_id"
    INPUT = "$ai_input"
    OUTPUT_CHOICES = "$ai_output_choices"
    SPAN_NAME = "$ai_span_name"

    # Additional attributes with $ai prefix
    MODEL_ID = "$ai_model_id"
    OUTPUT_TYPE = "$ai_output_type"
    TEMPERATURE = "$ai_temperature"
    MAX_TOKENS = "$ai_max_tokens"
    SEED = "$ai_seed"

    # Standard PostHog attribute for anonymous tracking
    PROCESS_PERSON_PROFILE = "$process_person_profile"


class PostHogEvent(StrEnum):
    """PostHog AI analytics event names."""

    SPAN = "$ai_span"
    GENERATION = "$ai_generation"


class GenAIOutputType(StrEnum):
    """OpenTelemetry GenAI semantic convention values of `gen_ai.output.type`."""

    TEXT = "text"
    JSON = "json"
    IMAGE = "image"


def make_otel_gen_ai_output_type(output_type: str) -> GenAIOutputType:
    try:
        llm_output_type = InferenceOutputType(output_type)
        match llm_output_type:
            case InferenceOutputType.TEXT:
                return GenAIOutputType.TEXT
            case InferenceOutputType.OBJECT:
                return GenAIOutputType.JSON
            case InferenceOutputType.IMAGE:
                return GenAIOutputType.IMAGE
            case InferenceOutputType.PAGES:
                return GenAIOutputType.JSON
    except ValueError as exc:
        msg = f"Invalid LLM output type: {output_type}, and we only support LLM output types for now in OpenTelemetry"
        raise ValueError(msg) from exc


class PipelexSpanAttr(StrEnum):
    """Pipelex-specific span attribute keys for method tracing."""

    TRACE_NAME = "pipelex.trace.name"
    TRACE_NAME_REDACTED = "pipelex.trace.name.redacted"
    SPAN_CATEGORY = "pipelex.span.category"  # "pipe" or "inference"
    PIPE_CATEGORY = "pipelex.pipe.category"
    PIPE_TYPE = "pipelex.pipe.type"
    PIPE_CODE = "pipelex.pipe.code"
    PIPELINE_RUN_ID = "pipelex.pipeline.run_id"
    OUTCOME = "pipelex.outcome"  # "success" or "failure"
    OUTPUT_CLASS_NAME = "pipelex.output.class_name"

    # The run's identity, set at every span site from `RunMetadata` so the identity
    # rides the span object to every exporter instead of being correlated back to a
    # run through shared state. RUN_USER_ID is who started the run; RUN_EXTRAS is
    # the host's opaque labels, serialized as a JSON string because an OTel attribute
    # is a scalar or a homogeneous list, never a mapping. The extras attribute is
    # omitted entirely when a run carries none.
    RUN_USER_ID = "pipelex.run.user_id"
    RUN_EXTRAS = "pipelex.run.extras"


class LangfuseSpanAttr(StrEnum):
    """Langfuse-specific span attribute keys for enhanced observability.

    These are trace-level attributes that Langfuse uses for grouping and filtering.
    Note: Langfuse auto-detects "generation" type when gen_ai.request.model is present,
    so we don't need to set langfuse.observation.type explicitly.

    See: https://langfuse.com/integrations/native/opentelemetry
    """

    # Trace-level attributes (applied to trace record in Langfuse)
    TRACE_NAME = "langfuse.trace.name"
    USER_ID = "langfuse.user.id"
    SESSION_ID = "langfuse.session.id"
    RELEASE = "langfuse.release"
    TRACE_INPUT = "langfuse.trace.input"
    TRACE_OUTPUT = "langfuse.trace.output"

    # Trace-level metadata (filterable in Langfuse UI)
    TRACE_DESCRIPTION = "langfuse.trace.metadata.description"
    TRACE_PIPE_CODE = "langfuse.trace.metadata.pipe_code"
    TRACE_PIPE_TYPE = "langfuse.trace.metadata.pipe_type"
    TRACE_PIPE_CATEGORY = "langfuse.trace.metadata.pipe_category"
    TRACE_PIPELINE_RUN_ID = "langfuse.trace.metadata.pipeline_run_id"
    TRACE_OUTCOME = "langfuse.trace.metadata.outcome"

    # Environment (standard OTel attribute recognized by Langfuse)
    DEPLOYMENT_ENVIRONMENT = "deployment.environment"

    # Observation-level metadata (filterable in Langfuse UI)
    OBSERVATION_DESCRIPTION = "langfuse.observation.metadata.description"
    OBSERVATION_TYPE = "langfuse.observation.metadata.observation_type"
    OBSERVATION_PIPE_CATEGORY = "langfuse.observation.metadata.pipe_category"
    OBSERVATION_PIPE_TYPE = "langfuse.observation.metadata.pipe_type"
    OBSERVATION_PIPE_CODE = "langfuse.observation.metadata.pipe_code"
    OBSERVATION_PIPELINE_RUN_ID = "langfuse.observation.metadata.pipeline_run_id"
    OBSERVATION_OUTCOME = "langfuse.observation.metadata.outcome"
    OBSERVATION_INPUT = "langfuse.observation.input"
    OBSERVATION_OUTPUT = "langfuse.observation.output"


class SpanCategory(StrEnum):
    PIPE = "pipe"
    INFERENCE = "inference"


class SpanOutcome(StrEnum):
    """Outcome values for span completion."""

    SUCCESS = "success"
    FAILURE = "failure"
