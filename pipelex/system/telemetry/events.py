from pipelex.types import StrEnum


class TelemetryEventName(StrEnum):
    PIPELINE_EXECUTE = "pipeline_execute"
    PIPE_RUN = "pipe_run"
    PIPE_COMPLETE = "pipe_complete"
