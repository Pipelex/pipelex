"""OpenTelemetry utilities for GenAI-compliant tracing.

This module provides helpers for instrumenting LLM operations with OpenTelemetry.
"""

import hashlib

from opentelemetry.trace import Tracer


def pipeline_run_id_to_trace_id(pipeline_run_id: str) -> int:
    """Convert pipeline_run_id to a 128-bit OTel trace ID (deterministic).

    Uses MD5 hash to generate a consistent trace ID from the pipeline_run_id.
    This ensures all spans within the same pipeline run share the same trace ID.

    Args:
        pipeline_run_id: The pipeline run identifier string.

    Returns:
        A 128-bit integer suitable for use as an OTel trace ID.
    """
    return int(hashlib.md5(pipeline_run_id.encode("utf-8")).hexdigest(), 16)  # noqa: S324


#########################################################
# Global Tracer Accessor (avoids circular imports)
#########################################################

# Module-level tracer reference, set by TelemetryManager during initialization
_global_tracer: Tracer | None = None


def set_global_tracer(tracer: Tracer | None) -> None:
    """Set the global tracer. Called by TelemetryManager during setup."""
    global _global_tracer  # noqa: PLW0603
    _global_tracer = tracer


def get_global_tracer() -> Tracer | None:
    """Get the global tracer for OTel instrumentation.

    This avoids circular imports by not depending on the hub module.
    """
    return _global_tracer
