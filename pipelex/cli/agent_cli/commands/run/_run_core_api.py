"""Core logic for running a pipeline via the remote MTHDS API in the agent CLI."""

from __future__ import annotations

from typing import Any

from mthds.client.pipeline import MAIN_STUFF_NAME
from mthds.runners.api_runner import ApiRunner


async def run_pipeline_core_api(
    pipe_code: str,
    mthds_content: str | None = None,
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Core logic for running a pipeline via the MTHDS API and returning JSON-serializable output.

    Args:
        pipe_code: The pipe code to run.
        mthds_content: MTHDS content string (optional).
        inputs: Input dictionary for the pipeline.

    Returns:
        Dictionary with execution results suitable for JSON serialization.

    Raises:
        ClientAuthenticationError: If API credentials are invalid or missing.
        PipelineRequestError: If the pipeline request is malformed.
    """
    runner = ApiRunner()
    response = await runner.execute_pipeline(
        pipe_code=pipe_code,
        mthds_content=mthds_content,
        inputs=inputs,
    )

    # Extract main stuff content from the working memory
    main_stuff_json: dict[str, Any] = {}
    main_stuff_name = response.main_stuff_name or MAIN_STUFF_NAME
    main_stuff = response.pipe_output.working_memory.root.get(main_stuff_name)
    if main_stuff is not None:
        main_stuff_json = {
            "json": main_stuff.content,
            "markdown": "",
            "html": "",
        }

    result: dict[str, Any] = {
        "success": True,
        "pipe_code": pipe_code,
        "dry_run": False,
        "runner": "api",
        "pipeline_run_id": response.pipeline_run_id,
        "pipeline_state": response.pipeline_state,
        "main_stuff": main_stuff_json,
        "working_memory": response.pipe_output.working_memory.model_dump(),
    }

    return result
