"""OpenTelemetry constants for GenAI-compliant tracing.

This module defines attribute keys used for instrumenting LLM operations
with OpenTelemetry, following the GenAI semantic conventions.
"""

from opentelemetry.semconv._incubating.attributes import gen_ai_attributes as otel_gen_ai_attributes  # noqa: PLC2701

from pipelex.types import StrEnum

UNKNOWN_PIPE = "unknown-pipe"
REDACTED = "[REDACTED]"
UNKNOWN_JOB = "unknown-job"
TRUNCATION_SUFFIX = "... [truncated]"

# Virtual parent span ID for root spans.
# INVALID_SPAN_ID (0) makes SpanContext invalid, causing OTel to ignore our trace_id.
# Using 1 as virtual parent ensures OTel uses our deterministic trace_id while
# still treating the span as a root (we filter this out in the exporter).
OTEL_VIRTUAL_ROOT_PARENT_SPAN_ID = 1


class GenAISpanAttr(StrEnum):
    """OpenTelemetry GenAI semantic convention attribute keys."""

    OPERATION_NAME = otel_gen_ai_attributes.GEN_AI_OPERATION_NAME
    PROVIDER_NAME = otel_gen_ai_attributes.GEN_AI_PROVIDER_NAME

    REQUEST_MODEL = otel_gen_ai_attributes.GEN_AI_REQUEST_MODEL
    REQUEST_MAX_TOKENS = otel_gen_ai_attributes.GEN_AI_REQUEST_MAX_TOKENS
    REQUEST_TEMPERATURE = otel_gen_ai_attributes.GEN_AI_REQUEST_TEMPERATURE
    REQUEST_SEED = otel_gen_ai_attributes.GEN_AI_REQUEST_SEED

    RESPONSE_MODEL = otel_gen_ai_attributes.GEN_AI_RESPONSE_MODEL
    OUTPUT_TYPE = otel_gen_ai_attributes.GEN_AI_OUTPUT_TYPE
    USAGE_INPUT_TOKENS = otel_gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS
    USAGE_OUTPUT_TOKENS = otel_gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS

    # Content attributes for PostHog compatibility (not in standard semconv)
    # PostHog UI expects these as span attributes, not events
    PROMPT_CONTENT = "gen_ai.prompt.0.content"
    COMPLETION_CONTENT = "gen_ai.completion.0.content"


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


class PostHogEvent(StrEnum):
    """PostHog AI analytics event names."""

    SPAN = "$ai_span"
    GENERATION = "$ai_generation"


class OTelConstants(StrEnum):
    """OpenTelemetry constants."""

    DEFAULT_USER_ID = "anonymous"
    SERVICE_NAME = "pipelex"
    SERVICE_NAMESPACE_KEY = "service.namespace"
    SERVICE_NAMESPACE = "ai.orchestration"
    INSTRUMENTATION_NAME = "pipelex"


class LLMOutputType(StrEnum):
    TEXT = "Text"
    OBJECT = "Object"

    @classmethod
    def is_text(cls, output_desc: str) -> bool:
        try:
            output_desc_enum = cls(output_desc)
        except ValueError:
            return False
        match output_desc_enum:
            case cls.TEXT:
                return True
            case cls.OBJECT:
                return False

    @property
    def as_otel_gen_ai_output_type(self) -> otel_gen_ai_attributes.GenAiOutputTypeValues:
        match self:
            case LLMOutputType.TEXT:
                return otel_gen_ai_attributes.GenAiOutputTypeValues.TEXT
            case LLMOutputType.OBJECT:
                return otel_gen_ai_attributes.GenAiOutputTypeValues.JSON


class PipelexSpanAttr(StrEnum):
    """Pipelex-specific span attribute keys for workflow tracing."""

    SPAN_CATEGORY = "pipelex.span.category"  # "pipe" or "inference"
    PIPE_CATEGORY = "pipelex.pipe.category"
    PIPE_TYPE = "pipelex.pipe.type"
    PIPE_CODE = "pipelex.pipe.code"
    PIPELINE_RUN_ID = "pipelex.pipeline.run_id"
    JOB_NAME = "pipelex.job.name"
    OUTCOME = "pipelex.outcome"  # "success" or "failure"


class SpanCategory(StrEnum):
    PIPE = "pipe"
    INFERENCE = "inference"


class SpanOutcome(StrEnum):
    """Outcome values for span completion."""

    SUCCESS = "success"
    FAILURE = "failure"
