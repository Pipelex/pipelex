from pydantic import BaseModel, ConfigDict, Field


class OtelContext(BaseModel):
    """OpenTelemetry context for tracing, derived from business IDs."""

    model_config = ConfigDict(strict=True, extra="forbid")

    trace_id: int = Field(description="128-bit, derived from pipeline_run_id")
    trace_name: str = Field(description="Trace name derived from pipeline_run_id and its main pipe_code")
    span_id: int = Field(description="64-bit, derived from pipe_run_id")
