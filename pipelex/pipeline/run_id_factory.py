"""Factory for generating run IDs used in pipeline and pipe execution tracking."""

import shortuuid


def make_pipeline_run_id(pipe_code: str | None) -> str:
    """Generate a unique pipeline run ID.

    Args:
        pipe_code: The pipe code to include in the ID. If None, only the short ID is used.

    Returns:
        A unique identifier like "my_pipe_RTMPCEnVbwSRYT5uvscjAa" or just the short ID.
    """
    short_id = shortuuid.uuid()[:5]
    return f"{pipe_code}_{short_id}" if pipe_code else short_id


def make_pipe_run_id(pipe_code: str) -> str:
    """Generate a unique pipe run ID.

    Args:
        pipe_code: The pipe code to include in the ID.

    Returns:
        A unique identifier like "my_pipe_RTMPCEnVbwSRYT5uvscjAa".
    """
    short_id = shortuuid.uuid()[:5]
    return f"{pipe_code}_{short_id}"
