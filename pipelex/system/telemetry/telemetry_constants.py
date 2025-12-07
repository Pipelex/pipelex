"""Pipelex telemetry constants for span attributes."""

from pipelex.types import StrEnum

UNKNOWN_PIPE = "unknown-pipe"
REDACTED = "[REDACTED]"
UNKNOWN_JOB = "unknown-job"


class OutputDesc(StrEnum):
    """Output description values for span names."""

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
