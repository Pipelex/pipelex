from pipelex.types import StrEnum


class EventName(StrEnum):
    # Settings
    TELEMETRY_JUST_ENABLED = "telemetry_just_enabled"

    # Show
    BACKENDS_SHOW = "backends_show"

    # Pipeline
    PIPELINE_EXECUTE = "pipeline_execute"
    PIPELINE_COMPLETE = "pipeline_complete"

    # Pipe
    PIPES_LIST = "pipes_list"
    PIPE_SHOW = "pipe_show"
    PIPE_RUN = "pipe_run"
    PIPE_COMPLETE = "pipe_complete"

    # Validation
    BUNDLE_DRY_RUN = "bundle_dry_run"
    PIPE_DRY_RUN = "pipe_dry_run"


class Setting(StrEnum):
    TELEMETRY_MODE = "telemetry_mode"


class EventProperty(StrEnum):
    # Context
    INTEGRATION = "integration"
    PIPELEX_VERSION = "pipelex_version"
    # Sub-context
    CLI_COMMAND = "cli_command"
    SETTING = "setting"

    # Settings
    TELEMETRY_MODE = "telemetry_mode"

    # Show
    NB_BACKENDS = "nb_backends"

    # Pipeline
    PIPELINE_RUN_ID = "pipeline_run_id"
    PIPELINE_EXECUTE_OUTCOME = "pipeline_execute_outcome"

    # Pipe
    PIPE_TYPE = "pipe_type"
    NB_PIPES = "nb_pipes"
    PIPE_RUN_OUTCOME = "pipe_run_outcome"

    # Bundle
    NB_CONCEPTS = "nb_concepts"


class Outcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
