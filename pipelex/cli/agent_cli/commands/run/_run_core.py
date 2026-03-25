"""Core logic for running a pipeline in the agent CLI."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from pipelex.cli.agent_cli.commands.run._output_helpers import build_run_output
from pipelex.config import get_config
from pipelex.graph.graph_factory import generate_graph_outputs, save_graph_outputs_to_dir
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.runner import PipelexRunner
from pipelex.tools.misc.json_utils import clean_json_dumps


async def run_pipeline_core(
    pipe_code: str,
    mthds_contents: list[str] | None = None,
    bundle_uris: list[str] | None = None,
    inputs: dict[str, Any] | None = None,
    dry_run: bool = False,
    mock_inputs: bool = False,
    library_dirs: list[str] | None = None,
    graph: bool = False,
    with_memory: bool = False,
) -> dict[str, Any]:
    """Core logic for running a pipeline and returning JSON-serializable output.

    Args:
        pipe_code: The pipe code to run.
        mthds_contents: List of MTHDS content strings (optional).
        bundle_uris: List of bundle file paths (optional).
        inputs: Input dictionary for the pipeline.
        dry_run: Whether to run in dry mode (no actual inference calls).
        mock_inputs: Whether to generate mock data for missing inputs.
        library_dirs: List of library directories to search for pipe definitions.
        graph: Whether to generate execution graph visualizations.
        with_memory: Whether to include full working memory in output (True) or
            return compact concept JSON only (False, default).

    Returns:
        Dictionary with execution results suitable for JSON serialization.

    Raises:
        PipelineExecutionError: If the pipeline execution fails.
    """
    pipe_run_mode = PipeRunMode.DRY if dry_run else None

    execution_config = get_config().pipelex.pipeline_execution_config.with_graph_config_overrides(
        generate_graph=graph,
        mock_inputs=mock_inputs or None,
    )

    runner = PipelexRunner(
        bundle_uris=bundle_uris,
        pipe_run_mode=pipe_run_mode,
        execution_config=execution_config,
        library_dirs=library_dirs,
    )
    response = await runner.execute_pipeline(
        pipe_code=pipe_code,
        mthds_contents=mthds_contents,
        inputs=inputs,
    )
    pipe_output = response.pipe_output

    main_stuff = pipe_output.working_memory.get_optional_main_stuff()
    main_stuff_json: dict[str, Any] = {}
    if main_stuff:
        main_stuff_json = {
            "json": await main_stuff.content.rendered_json_async(),
            "markdown": await main_stuff.content.rendered_markdown_async(),
            "html": await main_stuff.content.rendered_html_async(),
        }

    compact_result: dict[str, Any] | None = None
    if main_stuff:
        compact_result = json.loads(main_stuff_json["json"])

    result = build_run_output(
        with_memory=with_memory,
        main_stuff_json=main_stuff_json,
        working_memory_dump=pipe_output.working_memory.smart_dump(),
        compact_result=compact_result,
    )

    # Determine output directory: next to the bundle, or mthds-wip/ fallback
    output_dir: Path
    if bundle_uris and not bundle_uris[0].startswith(("http://", "https://")):
        output_dir = Path(bundle_uris[0]).parent
    else:
        output_dir = Path("mthds-wip")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Side-effect metadata (file paths) is tracked separately so it never
    # leaks into the compact stdout output.  It is written to the on-disk
    # JSON file and, when with_memory is True, included in the returned dict.
    side_effects: dict[str, Any] = {}

    # Generate and save graph visualizations if requested
    if graph and pipe_output.graph_spec:
        graph_config = execution_config.graph_config
        # Enable ReactFlow HTML output and data inclusion for the render
        render_graph_config = graph_config.model_copy(
            update={
                "data_inclusion": graph_config.data_inclusion.model_copy(
                    update={
                        "stuff_json_content": True,
                        "stuff_text_content": True,
                        "stuff_html_content": True,
                    }
                ),
                "graphs_inclusion": graph_config.graphs_inclusion.model_copy(
                    update={
                        "graphspec_json": False,
                        "mermaidflow_html": False,
                        "reactflow_html": True,
                    }
                ),
            }
        )

        graph_outputs = await generate_graph_outputs(
            graph_spec=pipe_output.graph_spec,
            graph_config=render_graph_config,
            pipe_code=pipe_code,
        )

        saved_files = save_graph_outputs_to_dir(graph_outputs=graph_outputs, output_dir=output_dir)

        # Rename reactflow.html to mode-aware filename
        graph_filename = "dry_run.html" if dry_run else "live_run.html"
        reactflow_path = saved_files.get("reactflow_html")
        if reactflow_path:
            final_path = reactflow_path.parent / graph_filename
            shutil.move(str(reactflow_path), str(final_path))
            side_effects["graph_files"] = {"graph_html": str(final_path)}

    # Save output JSON (includes side-effect paths for on-disk reference)
    output_filename = "dry_run.json" if dry_run else "live_run.json"
    output_path = output_dir / output_filename
    disk_output = {**result, **side_effects}
    output_path.write_text(clean_json_dumps(disk_output, indent=2), encoding="utf-8")
    side_effects["output_file"] = str(output_path)

    # In full mode, include side-effect metadata in the returned output;
    # in compact mode, keep stdout clean (concept JSON only).
    if with_memory:
        result.update(side_effects)

    return result
