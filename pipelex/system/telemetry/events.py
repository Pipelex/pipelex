from pipelex.types import StrEnum


class EventName(StrEnum):
    # Pipeline
    PIPELINE_EXECUTE = "pipeline_execute"
    PIPELINE_COMPLETE = "pipeline_complete"

    # Pipe
    PIPE_RUN = "pipe_run"
    PIPE_COMPLETE = "pipe_complete"


class EventProperty(StrEnum):
    # Pipeline
    PIPELINE_RUN_ID = "pipeline_run_id"
    PIPELINE_EXECUTE_OUTCOME = "pipeline_execute_outcome"

    # Pipe
    PIPE_RUN_OUTCOME = "pipe_run_outcome"


class Outcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
