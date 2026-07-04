"""Core logic for running a pipeline via the remote MTHDS API in the agent CLI."""

# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false

from __future__ import annotations

from typing import Any, cast

from mthds.runners.api.client import MthdsAPIClient
from mthds.runners.api.models import MAIN_STUFF_NAME

from pipelex.cli.agent_cli.commands.run._output_helpers import build_run_output
from pipelex.pipeline.exceptions import PipeExecutionError


async def run_pipeline_core_api(
    pipe_code: str,
    *,
    mthds_contents: list[str] | None = None,
    inputs: dict[str, Any] | None = None,
    with_memory: bool = False,
) -> dict[str, Any]:
    """Core logic for running a pipeline via the MTHDS API and returning JSON-serializable output.

    Args:
        pipe_code: The pipe code to run.
        mthds_contents: List of MTHDS content strings (optional).
        inputs: Input dictionary for the pipeline.
        with_memory: Whether to include full working memory in output (True) or
            return compact concept JSON only (False, default).

    Returns:
        Dictionary with execution results suitable for JSON serialization.

    Raises:
        ClientAuthenticationError: If API credentials are invalid or missing.
        PipelineRequestError: If the pipeline request is malformed.
    """
    async with MthdsAPIClient() as runner:
        response = await runner.execute(
            pipe_code=pipe_code,
            mthds_contents=mthds_contents,
            inputs=inputs,
        )

    pipe_output = response.pipe_output

    # `main_stuff_name` and `state` are pipelex extension fields on the protocol's
    # extension-open RunResult — they ride model_extra, never named by the SDK.
    extensions: dict[str, Any] = response.model_extra or {}

    # Extract the main stuff content from the working memory. A completed run always delivers
    # a main stuff — a response without one under the announced key is a runner contract violation.
    raw_main_stuff_name = extensions.get("main_stuff_name")
    main_stuff_name = raw_main_stuff_name if isinstance(raw_main_stuff_name, str) else MAIN_STUFF_NAME
    main_stuff = pipe_output.working_memory.root.get(main_stuff_name)
    if main_stuff is None:
        msg = (
            f"Completed run '{response.pipeline_run_id}' response has no main stuff under key '{main_stuff_name}' — "
            "a completed run always delivers a main stuff."
        )
        raise PipeExecutionError(msg)

    main_stuff_json: dict[str, Any] = {
        "json": main_stuff.content,
        "markdown": "",
        "html": "",
    }
    content: Any = main_stuff.content
    compact_result: dict[str, Any] = cast("dict[str, Any]", content) if isinstance(content, dict) else {"result": content}

    return build_run_output(
        with_memory=with_memory,
        main_stuff_json=main_stuff_json,
        working_memory_dump=pipe_output.working_memory.model_dump(),
        compact_result=compact_result,
        extra_metadata={
            "pipeline_run_id": response.pipeline_run_id,
            "pipeline_state": extensions.get("state"),
        },
    )
