from pydantic import BaseModel, ConfigDict, Field


class OtelContext(BaseModel):
    """OpenTelemetry context for tracing, carried in the job metadata so it crosses a process boundary.

    By default the trace is derived from the run's business ids. A run that joined its host's trace
    (``join_host_trace``) carries the host's trace id, the host span its root pipe span starts under,
    the host's sampling decision and its W3C trace state instead, so a worker in another process
    continues the same trace.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    trace_id: int = Field(description="128-bit: derived from pipeline_run_id, or the host's when the run joined the host's trace")
    trace_name: str = Field(description="Trace name with pipe_code (for custom telemetry)")
    trace_name_redacted: str = Field(description="Trace name without pipe_code (for Pipelex telemetry)")
    span_id: int = Field(description="64-bit: the parent of the next span, the virtual root parent on the run's root context")
    is_sampled: bool = Field(description="The sampled flag of the synthetic parent built from this context: the host's decision on a joined run")
    trace_state: str | None = Field(
        default=None, description="The W3C `tracestate` header of the trace, carried to every synthetic parent; None when it is empty"
    )
    host_span_id: int | None = Field(
        default=None, description="On the root context of a run that joined its host's trace, the host span its root pipe span starts under"
    )
    is_host_span_pipelex: bool = Field(
        default=False,
        description="On the root context of a run started inside a running pipe of this process with join_host_trace on: the span the "
        "run joined is that pipe's Pipelex span, which Pipelex's own streams receive, so the run's root span is not the trace's root",
    )

    @property
    def is_trace_root_announced(self) -> bool:
        """Whether a run starting from this context announces its trace: not when the host sampled it out or an enclosing run already did."""
        return self.is_sampled and not self.is_host_span_pipelex
