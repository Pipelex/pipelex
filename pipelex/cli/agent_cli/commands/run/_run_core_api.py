"""Core logic for running a pipeline via the remote MTHDS API in the agent CLI."""

from __future__ import annotations

from typing import Any, cast

from mthds.client.pipeline import MAIN_STUFF_NAME
from mthds.runners.api_runner import ApiRunner

from pipelex.cli.agent_cli.commands.run._output_helpers import build_run_output


async def run_pipeline_core_api(
    pipe_code: str,
    mthds_content: str | None = None,
    inputs: dict[str, Any] | None = None,
    with_memory: bool = False,
) -> dict[str, Any]:
    """Core logic for running a pipeline via the MTHDS API and returning JSON-serializable output.

    Args:
        pipe_code: The pipe code to run.
        mthds_content: MTHDS content string (optional).
        inputs: Input dictionary for the pipeline.
        with_memory: Whether to include full working memory in output (True) or
            return compact concept JSON only (False, default).

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

    compact_result: dict[str, Any] | None = None
    if main_stuff is not None:
        content: Any = main_stuff.content
        compact_result = cast("dict[str, Any]", content) if isinstance(content, dict) else {"result": content}

    return build_run_output(
        with_memory=with_memory,
        main_stuff_json=main_stuff_json,
        working_memory_dump=response.pipe_output.working_memory.model_dump(),
        compact_result=compact_result,
        extra_metadata={
            "pipeline_run_id": response.pipeline_run_id,
            "pipeline_state": response.pipeline_state,
        },
    )
