"""Factory for generating run IDs used in pipeline and pipe execution tracking."""

import shortuuid

from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract


def make_pipeline_run_id(pipe_code: str | None) -> str:
    """Generate a unique pipeline run ID.

    When capture_pipe_codes_enabled is False, the pipe_code is omitted for privacy.

    Args:
        pipe_code: The pipe code to include in the ID. If None or if pipe code capture
                   is disabled, only the short ID is used.

    Returns:
        A unique identifier like "my_pipe_abc12" or just "abc12" when redacted.
    """
    if pipe_code and TelemetryManagerAbstract.is_capture_pipe_codes_enabled():
        short_id = shortuuid.uuid()[:5]
        return f"{pipe_code}_{short_id}"
    else:
        return shortuuid.uuid()


def make_pipe_run_id(pipe_code: str) -> str:
    """Generate a unique pipe run ID.

    When capture_pipe_codes_enabled is False, the pipe_code is omitted for privacy.

    Args:
        pipe_code: The pipe code to include in the ID.

    Returns:
        A unique identifier like "my_pipe_abc12" or just "abc12" when redacted.
    """
    if TelemetryManagerAbstract.is_capture_pipe_codes_enabled():
        short_id = shortuuid.uuid()[:5]
        return f"{pipe_code}_{short_id}"
    else:
        return shortuuid.uuid()
