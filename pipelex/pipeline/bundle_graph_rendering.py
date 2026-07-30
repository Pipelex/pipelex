"""Producing a run graph for a *bundle*, by dry-running it.

Interpreter-layer counterpart of ``pipelex.graph.graph_rendering``: these helpers take a bundle path,
load and dry-run the method to obtain a :class:`GraphSpec`, then hand it to the runtime-layer renderer.
The split is along "do I need a loaded method?", which is the hub layering boundary's own question —
see ``docs/contribute/hub-layering.md``.
"""

from pathlib import Path
from typing import Any

from pipelex.config import get_config
from pipelex.graph.graph_rendering import GraphFormat, render_graph_from_spec
from pipelex.graph.graphspec import GraphSpec
from pipelex.pipeline.dry_run_pipeline import dry_run_pipeline
from pipelex.tools.misc.chart_utils import FlowchartDirection


def _sanitize_graph_name(graph_name: str) -> str:
    """Sanitize graph_name to prevent path traversal.

    Args:
        graph_name: The requested filename for the graph output.

    Returns:
        A safe filename with no directory components.
    """
    sanitized = Path(graph_name).name
    return sanitized or "graph.html"


async def _dry_run_bundle(
    bundle_path: Path,
    *,
    library_dirs: list[str] | None = None,
    pipe_code: str | None = None,
) -> tuple[GraphSpec, str]:
    """Dry-run a bundle file to produce a GraphSpec.

    Reads the file, ensures its parent directory is in library_dirs,
    then delegates to ``dry_run_pipeline``.

    Args:
        bundle_path: Path to the .mthds bundle file.
        library_dirs: Optional library directories for pipe resolution.
        pipe_code: Optional explicit pipe target for graph generation.

    Returns:
        Tuple of (GraphSpec, pipe_code).
    """
    mthds_content = bundle_path.read_text(encoding="utf-8")

    # Ensure the bundle's parent directory is included in library_dirs
    # so PipelexMTHDSProtocol can resolve sibling dependencies
    bundle_parent_dir = str(bundle_path.parent.resolve())
    effective_library_dirs: list[str]
    if library_dirs:
        effective_library_dirs = list(library_dirs)
        if bundle_parent_dir not in effective_library_dirs:
            effective_library_dirs.append(bundle_parent_dir)
    else:
        effective_library_dirs = [bundle_parent_dir]

    return await dry_run_pipeline(
        mthds_contents=[mthds_content],
        bundle_uris=[str(bundle_path)],
        library_dirs=effective_library_dirs,
        pipe_code=pipe_code,
    )


async def generate_graph_for_bundle(
    bundle_path: Path,
    *,
    graph_format: GraphFormat,
    library_dirs: list[str] | None = None,
    pipe_code: str | None = None,
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
        pipe_code: Optional explicit pipe target for graph generation.
        direction: Flowchart layout direction (default: None, uses TB).
        graph_name: Filename for the generated HTML graph (default: "dry_run.html").

    Returns:
        Dictionary with graph_files, graph_output_dir, and direction.

    Raises:
        MthdsParserError: If bundle parsing fails or main_pipe is missing.
        PipelexError: If pipeline execution does not produce a graph spec.
        PipelineExecutionError: If dry-run execution fails.
    """
    graph_spec, resolved_pipe_code = await _dry_run_bundle(bundle_path, library_dirs=library_dirs, pipe_code=pipe_code)

    execution_config = get_config().pipelex.pipeline_execution_config.with_execution_overrides(
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
        pipe_code=resolved_pipe_code,
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
        "pipe_code": resolved_pipe_code,
        "direction": str(direction) if direction else None,
    }


async def generate_view_for_bundle(
    bundle_path: Path,
    *,
    library_dirs: list[str] | None = None,
    pipe_code: str | None = None,
    direction: FlowchartDirection | None = None,
) -> dict[str, Any]:
    """Generate a GraphSpec for a bundle via dry-run pipeline execution.

    Returns structured JSON data (GraphSpec) suitable for client-side rendering,
    without writing any files to disk.

    Args:
        bundle_path: Path to the .mthds bundle file.
        library_dirs: Optional library directories for pipe resolution.
        pipe_code: Optional explicit pipe target for graph generation.
        direction: Flowchart layout direction (default: None, uses config default).

    Returns:
        Dictionary with graphspec (JSON-serializable dict), pipe_code, and direction.

    Raises:
        MthdsParserError: If bundle parsing fails or main_pipe is missing.
        PipelexError: If pipeline execution does not produce a graph spec.
        PipelineExecutionError: If dry-run execution fails.
    """
    graph_spec, resolved_pipe_code = await _dry_run_bundle(bundle_path, library_dirs=library_dirs, pipe_code=pipe_code)

    execution_config = get_config().pipelex.pipeline_execution_config.with_execution_overrides(
        generate_graph=True,
        mock_inputs=True,
    )
    rf_config = execution_config.graph_config.reactflow_config
    effective_direction = direction or rf_config.layout_direction

    return {
        "graphspec": graph_spec.model_dump(mode="json", by_alias=True),
        "pipe_code": resolved_pipe_code,
        "direction": str(effective_direction) if effective_direction else None,
    }
