"""Pipelex telemetry constants for span attributes."""

from pipelex.types import StrEnum


class PipelexSpanAttr(StrEnum):
    """Pipelex-specific span attribute keys for workflow tracing."""

    PIPE_CODE = "pipelex.pipe.code"
    PIPE_TYPE = "pipelex.pipe.type"
    PIPE_CATEGORY = "pipelex.pipe.category"
    PIPELINE_RUN_ID = "pipelex.pipeline.run_id"
    SPAN_KIND = "pipelex.span.kind"  # "pipe" or "inference"
