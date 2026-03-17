"""Shared graph rendering utilities for CLI commands.

Builds a render-specific GraphConfig, generates graph outputs, and saves them to disk.
Used by both the regular CLI and the agent CLI.
"""

from pathlib import Path
from typing import Any

from pipelex.config import get_config
from pipelex.graph.graph_config import GraphConfig
from pipelex.graph.graph_factory import GraphOutputs, generate_graph_outputs, save_graph_outputs_to_dir
from pipelex.graph.graphspec import GraphSpec
from pipelex.pipe_run.dry_run_pipeline import dry_run_pipeline
from pipelex.tools.misc.chart_utils import FlowchartDirection
from pipelex.types import StrEnum


def _sanitize_graph_name(graph_name: str) -> str:
    """Sanitize graph_name to prevent path traversal.

    Args:
        graph_name: The requested filename for the graph output.

    Returns:
        A safe filename with no directory components.
    """
    sanitized = Path(graph_name).name
    return sanitized or "graph.html"


class GraphFormat(StrEnum):
    """Selectable graph output formats."""

    MERMAIDFLOW = "mermaidflow"
    REACTFLOW = "reactflow"
    BOTH = "both"


async def render_graph_from_spec(
    graph_spec: GraphSpec,
    graph_config: GraphConfig,
    include_mermaidflow: bool,
    include_reactflow: bool,
    output_dir: Path,
    *,
    pipe_code: str = "",
    title: str | None = None,
    direction: FlowchartDirection | None = None,
    include_subgraphs: bool = True,
) -> dict[str, Path]:
    """Render graph outputs from a graph spec and save to output_dir.

    Builds a render config from the provided graph config with format selection,
    generates graph outputs, and saves them to the output directory.

    Args:
        graph_spec: The graph spec produced by pipeline execution.
        graph_config: The base graph configuration.
        include_mermaidflow: Whether to generate Mermaid HTML output.
        include_reactflow: Whether to generate ReactFlow HTML output.
        output_dir: Directory where graph files will be saved.
        pipe_code: The pipe code, used to derive the HTML page title.
        title: Explicit title for the graph page (takes precedence over pipe_code).
        direction: Flowchart direction override.
        include_subgraphs: Whether to include controller subgraphs in Mermaid output.

    Returns:
        Dict mapping output format keys to saved file paths.
    """
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
                    "mermaidflow_mmd": False,
                    "mermaidflow_html": include_mermaidflow,
                    "reactflow_html": include_reactflow,
                }
            ),
        }
    )

    graph_outputs: GraphOutputs = await generate_graph_outputs(
        graph_spec=graph_spec,
        graph_config=render_graph_config,
        pipe_code=pipe_code,
        title=title,
        direction=direction,
        include_subgraphs=include_subgraphs,
    )

    return save_graph_outputs_to_dir(graph_outputs=graph_outputs, output_dir=output_dir)


async def _dry_run_bundle(
    bundle_path: Path,
    library_dirs: list[str] | None = None,
) -> tuple[GraphSpec, str]:
    """Dry-run a bundle file to produce a GraphSpec.

    Reads the file, ensures its parent directory is in library_dirs,
    then delegates to ``dry_run_pipeline``.

    Args:
        bundle_path: Path to the .mthds bundle file.
        library_dirs: Optional library directories for pipe resolution.

    Returns:
        Tuple of (GraphSpec, pipe_code).
    """
    mthds_content = bundle_path.read_text(encoding="utf-8")

    # Ensure the bundle's parent directory is included in library_dirs
    # so PipelexRunner can resolve sibling dependencies
    bundle_parent_dir = str(bundle_path.parent.resolve())
    effective_library_dirs: list[str]
    if library_dirs:
        effective_library_dirs = list(library_dirs)
        if bundle_parent_dir not in effective_library_dirs:
            effective_library_dirs.append(bundle_parent_dir)
    else:
        effective_library_dirs = [bundle_parent_dir]

    return await dry_run_pipeline(
        mthds_content=mthds_content,
        bundle_uri=str(bundle_path),
        library_dirs=effective_library_dirs,
    )


async def generate_graph_for_bundle(
    bundle_path: Path,
    graph_format: GraphFormat,
    library_dirs: list[str] | None = None,
    direction: FlowchartDirection | None = None,
    graph_name: str = "dry_run.html",
) -> dict[str, Any]:
    """Generate graph visualization for a bundle via dry-run pipeline execution.

    Reads the bundle, parses main_pipe, performs a dry-run with graph tracing,
    then renders and saves graph HTML files alongside the bundle.

    Args:
        bundle_path: Path to the .mthds bundle file.
        graph_format: Which graph format(s) to generate.
        library_dirs: Optional library directories for pipe resolution.
        direction: Flowchart layout direction (default: None, uses TB).
        graph_name: Filename for the generated HTML graph (default: "dry_run.html").

    Returns:
        Dictionary with graph_files, graph_output_dir, and direction.

    Raises:
        PipelexInterpreterError: If bundle parsing fails or main_pipe is missing.
        PipelexError: If pipeline execution does not produce a graph spec.
        PipelineExecutionError: If dry-run execution fails.
    """
    graph_spec, pipe_code = await _dry_run_bundle(bundle_path, library_dirs)

    execution_config = get_config().pipelex.pipeline_execution_config.with_graph_config_overrides(
        generate_graph=True,
        mock_inputs=True,
    )

    include_mermaidflow: bool
    include_reactflow: bool
    match graph_format:
        case GraphFormat.MERMAIDFLOW:
            include_mermaidflow = True
            include_reactflow = False
        case GraphFormat.REACTFLOW:
            include_mermaidflow = False
            include_reactflow = True
        case GraphFormat.BOTH:
            include_mermaidflow = True
            include_reactflow = True

    output_dir = bundle_path.parent
    saved_files = await render_graph_from_spec(
        graph_spec=graph_spec,
        graph_config=execution_config.graph_config,
        include_mermaidflow=include_mermaidflow,
        include_reactflow=include_reactflow,
        output_dir=output_dir,
        pipe_code=pipe_code,
        direction=direction,
    )

    # Rename reactflow.html to the requested filename
    reactflow_path = saved_files.get("reactflow_html")
    safe_name = _sanitize_graph_name(graph_name)
    if reactflow_path and safe_name:
        final_path = reactflow_path.parent / safe_name
        reactflow_path.rename(final_path)
        saved_files["reactflow_html"] = final_path

    return {
        "graph_files": {key: str(path) for key, path in saved_files.items()},
        "graph_output_dir": str(output_dir),
        "pipe_code": pipe_code,
        "direction": str(direction) if direction else None,
    }


async def generate_view_for_bundle(
    bundle_path: Path,
    library_dirs: list[str] | None = None,
    direction: FlowchartDirection | None = None,
) -> dict[str, Any]:
    """Generate a GraphSpec for a bundle via dry-run pipeline execution.

    Returns structured JSON data (GraphSpec) suitable for client-side rendering,
    without writing any files to disk.

    Args:
        bundle_path: Path to the .mthds bundle file.
        library_dirs: Optional library directories for pipe resolution.
        direction: Flowchart layout direction (default: None, uses config default).

    Returns:
        Dictionary with graphspec (JSON-serializable dict), pipe_code, and direction.

    Raises:
        PipelexInterpreterError: If bundle parsing fails or main_pipe is missing.
        PipelexError: If pipeline execution does not produce a graph spec.
        PipelineExecutionError: If dry-run execution fails.
    """
    graph_spec, pipe_code = await _dry_run_bundle(bundle_path, library_dirs)

    execution_config = get_config().pipelex.pipeline_execution_config.with_graph_config_overrides(
        generate_graph=True,
        mock_inputs=True,
    )
    rf_config = execution_config.graph_config.reactflow_config
    effective_direction = direction or rf_config.layout_direction

    return {
        "graphspec": graph_spec.model_dump(mode="json", by_alias=True),
        "pipe_code": pipe_code,
        "direction": str(effective_direction) if effective_direction else None,
    }
