"""Example: resolve a method from a GitHub URL, validate it, and print the mermaid graph.

Usage:
    .venv/bin/python -m pipelex.examples

Requires:
    - A valid .pipelex/ config
    - git installed on PATH (for cloning remote methods)
"""

import asyncio
from pathlib import Path

from pipelex import log
from pipelex.cli.method_resolver import resolve_method_target
from pipelex.config import get_config
from pipelex.graph.graph_factory import generate_graph_outputs
from pipelex.hub import get_library_manager, get_required_pipe, set_current_library
from pipelex.pipe_run.dry_run_with_graph import dry_run_pipe_with_graph
from pipelex.pipelex import Pipelex
from pipelex.tools.misc.chart_utils import FlowchartDirection


async def validate_method_and_print_graph(
    method_target: str,
    pipe_override: str | None = None,
) -> None:
    """Resolve a method, dry-run it, and print the mermaid graph.

    The *method_target* can be either a local method name (e.g. ``"cv-analyzer"``)
    or a GitHub URL pointing to a method package (e.g.
    ``"https://github.com/Pipelex/methods/methods/cv-analyzer"``).

    No LLM calls are made — the pipeline is executed in dry-run mode which
    validates all bundles and captures the execution graph.

    Args:
        method_target: Installed method name or GitHub URL to resolve.
        pipe_override: Optional pipe code override (takes precedence over main_pipe).
    """
    # 1. Initialize pipelex (no inference needed for dry runs)
    Pipelex.make(needs_inference=False)

    # 2. Resolve the method target (local name or GitHub URL)
    pipe_code, library_dirs, method = resolve_method_target(
        method_name=method_target,
        pipe_override=pipe_override,
    )
    log.info(f"Resolved method '{method.name}' → pipe '{pipe_code}'")

    # 3. Load the method's libraries
    library_manager = get_library_manager()
    library_id, _ = library_manager.open_library()
    set_current_library(library_id=library_id)
    library_manager.load_libraries(
        library_id=library_id,
        library_dirs=[Path(lib_dir) for lib_dir in library_dirs],
    )

    # 4. Get the pipe and dry-run it with graph tracing
    pipe = get_required_pipe(pipe_code=pipe_code)
    log.info(f"Dry-running pipe '{pipe_code}' with graph tracing...")
    graph_spec = await dry_run_pipe_with_graph(pipe)

    log.info(f"Graph generated: {len(graph_spec.nodes)} nodes, {len(graph_spec.edges)} edges")

    # 5. Generate mermaid graph output
    graph_config = get_config().pipelex.pipeline_execution_config.graph_config
    graph_outputs = await generate_graph_outputs(
        graph_spec=graph_spec,
        graph_config=graph_config,
        pipe_code=pipe_code,
        title=f"Pipeline: {method.name}",
        direction=FlowchartDirection.TOP_DOWN,
        include_subgraphs=True,
    )

    # 6. Print the mermaid code
    if graph_outputs.mermaidflow_mmd:
        print(graph_outputs.mermaidflow_mmd)
    else:
        log.warning("No mermaid graph was generated.")


if __name__ == "__main__":
    asyncio.run(
        validate_method_and_print_graph(
            method_target="https://github.com/Pipelex/methods/tree/main/methods/doc-summarizer",
        )
    )
