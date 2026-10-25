"""Core logic for running a pipeline in the agent CLI."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pipelex import log
from pipelex.base_exceptions import PipelexError
from pipelex.cli.agent_cli.commands.run._output_helpers import build_run_output
from pipelex.cli.commands.run._run_output_folder import RUN_RESULTS_DIR_NAME, make_run_output_folder, run_output_label
from pipelex.cogt.usage.cost_registry import CostRegistry
from pipelex.config import get_config
from pipelex.core.memory.absence import AbsenceRecord
from pipelex.core.memory.absence_render import build_absence_html, build_absence_json, build_absence_markdown, build_absence_payload
from pipelex.graph.graph_factory import generate_graph_outputs, save_graph_outputs_to_dir
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.usage_stats.usage_stats_contract import UsageStatsMethodSource
from pipelex.system.usage_stats.usage_stats_runs import method_source_scope
from pipelex.tools.log.error_fields import error_fields
from pipelex.tools.misc.json_utils import clean_json_dumps

if TYPE_CHECKING:
    from mthds.method_tree.models import MethodTree

    from pipelex.libraries.method_tree_listing import MethodTreeListing
    from pipelex.system.configuration.configs import PipelineExecutionConfig


def _with_agent_graphs_inclusion(*, execution_config: PipelineExecutionConfig) -> PipelineExecutionConfig:
    """The agent CLI's graph outputs: the graphspec and the ReactFlow viewer, never the Mermaid page."""
    graphs_inclusion = execution_config.graph.graphs_inclusion.model_copy(
        update={
            "graphspec_json": True,
            "mermaidflow_html": False,
            "reactflow_html": True,
        }
    )
    return execution_config.model_copy(update={"graph": execution_config.graph.model_copy(update={"graphs_inclusion": graphs_inclusion})})


async def run_pipeline_core(
    pipe_code: str,
    *,
    mthds_contents: list[str] | None = None,
    bundle_uris: list[str] | None = None,
    inputs: dict[str, Any] | None = None,
    dry_run: bool = False,
    mock_inputs: bool = False,
    library_dirs: list[str] | None = None,
    graph: bool = False,
    costs: bool = True,
    with_memory: bool = False,
    inputs_base_dir: Path | None = None,
    output_dir_override: Path | None = None,
    method_tree: MethodTree | None = None,
    tree_listing: MethodTreeListing | None = None,
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
        costs: Whether to emit usage (cost) tracing events. Default True.
        with_memory: Whether to include full working memory in output (True) or
            return compact concept JSON only (False, default).
        inputs_base_dir: Directory bare relative file paths in ``inputs`` resolve against (Smart
            Inputs D3) — the inputs file's parent when file-loaded, else ``None``.
        output_dir_override: Directory the run's output folder (output JSON, graph files) is created under,
            overriding the default, `results/` beside the bundle. `run bundle` always passes the one
            `bundle_run_outputs_dir` settles for its target, which `validate bundle --graph` shares; `run method`
            passes one when the bundle lives in a directory that will not survive the process, a fetched method's
            ephemeral clone.
        method_tree: The method tree the run reads, when the command listed one: its digest is recorded as
            ``method_tree_digest`` beside the run's other side effects, on disk and under ``with_memory``.
        tree_listing: The listing the command listed ``method_tree`` through, which the run loads its trees from, so
            the digest recorded is the digest of the tree the run loaded. None lists the trees for the run.

    Returns:
        Dictionary with execution results suitable for JSON serialization.

    Raises:
        ValidateBundleError: If the bundle is refused while it loads, before any pipe runs; it carries
            the same located ``validation_errors`` validating the bundle gives.
        PipelineExecutionError: If the pipeline execution fails.
    """
    pipe_run_mode = PipeRunMode.DRY if dry_run else None

    execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(
        generate_graph=graph,
        generate_usage=costs,
        mock_inputs=mock_inputs or None,
    )
    if graph:
        # The agent CLI writes the graphspec and the ReactFlow viewer whatever the configured inclusion
        # says. The override is applied before the run, not at render time: the run setup gates the
        # graphspec's companion artifacts on this same flag, and they are built inside the run's library
        # window, which is gone by the time anything is rendered.
        execution_config = _with_agent_graphs_inclusion(execution_config=execution_config)

    runner = PipelexMTHDSProtocol(
        bundle_uris=bundle_uris,
        pipe_run_mode=pipe_run_mode,
        execution_config=execution_config,
        library_dirs=library_dirs,
        inputs_base_dir=inputs_base_dir,
        # The directories a CLI loads are the caller's own: a refusal there is their invalid bundle.
        library_dirs_are_callers=True,
    )
    # The CLI reads every bundle it runs from the caller's files; a method it resolved declared its own source first.
    with method_source_scope(source=UsageStatsMethodSource.LOCAL_BUNDLE):
        response = await runner.execute(
            pipe_code=pipe_code,
            mthds_contents=mthds_contents,
            inputs=inputs,
            tree_listing=tree_listing,
        )
    pipe_output = response.pipe_output

    # A completed run always resolves its declared output: a value or a recorded absence. An
    # absent main output renders the explicit absence document on every arm of the envelope.
    main_resolved = pipe_output.working_memory.resolve_main_stuff()
    main_stuff_json: dict[str, Any]
    compact_result: dict[str, Any]
    if isinstance(main_resolved, AbsenceRecord):
        main_stuff_json = {
            "json": build_absence_json(main_resolved),
            "markdown": build_absence_markdown(main_resolved),
            "html": build_absence_html(main_resolved),
        }
        compact_result = build_absence_payload(main_resolved)
    else:
        main_stuff = main_resolved
        main_stuff_json = {
            "json": await main_stuff.content.rendered_json_async(),
            "markdown": await main_stuff.content.rendered_markdown_async(),
            "html": await main_stuff.content.rendered_html_async(),
        }
        compact_result = json.loads(main_stuff_json["json"])

    result = build_run_output(
        with_memory=with_memory,
        main_stuff_json=main_stuff_json,
        working_memory_dump=pipe_output.working_memory.smart_dump(),
        compact_result=compact_result,
    )

    # The run writes into a new numbered folder, `<pipe_code>_output_NN/`, under the directory its outputs go to: an
    # explicit override wins (a fetched method's bundle lives in an ephemeral clone deleted at process exit, so the
    # caller re-anchors outputs somewhere durable); otherwise `results/` beside the bundle, or under mthds-wip/. The
    # folder holds a `.gitignore` ignoring everything in it, as `pipelex run`'s does, so a run beside its bundle never
    # adds a file to the method tree it ran, and the next run reads the same tree, with the same digest.
    outputs_dir: Path
    if output_dir_override is not None:
        outputs_dir = output_dir_override
    elif bundle_uris and not bundle_uris[0].startswith(("http://", "https://")):
        outputs_dir = Path(bundle_uris[0]).parent / RUN_RESULTS_DIR_NAME
    else:
        outputs_dir = Path("mthds-wip") / RUN_RESULTS_DIR_NAME
    output_dir = make_run_output_folder(output_dir=outputs_dir, label=run_output_label(pipe_ref=pipe_code))

    # Side-effect metadata (file paths) is tracked separately so it never
    # leaks into the compact stdout output.  It is written to the on-disk
    # JSON file and, when with_memory is True, included in the returned dict.
    side_effects: dict[str, Any] = {}
    # The digest of the method tree the run read names the exact files of the method it ran.
    if method_tree is not None:
        side_effects["method_tree_digest"] = method_tree.digest

    # Cost report: best-effort structured `cost_report` object in the JSON output (machine-first; no Rich
    # table on stderr like the human CLI). build_cost_summary returns None for runs that did no reportable
    # work (dry runs: zero tokens and zero cost), so a free/zero-price real run yields a summary (total_cost
    # 0) while a dry run yields None. When a summary is produced it rides the side-effect envelope: on disk
    # always, and in the stdout result under --with-memory; the markdown renderer ignores the key, so it is
    # JSON-only. It is therefore absent for dry runs, --no-costs (the gate below), or an aggregation failure
    # (the guard below skips it without failing the run) — consumers treat it as optional.
    if costs and pipe_output.tokens_usages:
        # A cost-summary failure must never fail an otherwise-successful run (mirrors the main CLI's
        # render_run_cost_report guard): CostRegistry can raise CostRegistryError (a PipelexError) during
        # aggregation. Catch it, log, and skip the cost_report rather than propagate.
        try:
            cost_summary = CostRegistry.build_cost_summary(tokens_usages=pipe_output.tokens_usages)
        except PipelexError as cost_summary_error:
            log.warning(
                "The cost summary of a successful run could not be built",
                fields=error_fields(exc=cost_summary_error),
            )
        else:
            if cost_summary is not None:
                side_effects["cost_report"] = cost_summary

    # Generate and save graph visualizations if requested
    if graph and pipe_output.graph_spec:
        graph_config = execution_config.graph
        # Full data inclusion for the render (the graphs inclusion was settled before the run)
        render_graph_config = graph_config.model_copy(
            update={
                "data_inclusion": graph_config.data_inclusion.model_copy(
                    update={
                        "stuff_json_content": True,
                    }
                ),
            }
        )

        graph_outputs = await generate_graph_outputs(
            graph_spec=pipe_output.graph_spec,
            graph_config=render_graph_config,
            pipe_code=pipe_code,
            pipe_io_artifacts=pipe_output.pipe_io_artifacts,
        )

        saved_files = save_graph_outputs_to_dir(graph_outputs=graph_outputs, output_dir=output_dir)

        # Rename reactflow.html to mode-aware filename
        graph_filename = "dry_run.html" if dry_run else "live_run.html"
        reactflow_path = saved_files.get("reactflow_html")
        if reactflow_path:
            final_path = reactflow_path.parent / graph_filename
            shutil.move(str(reactflow_path), str(final_path))
            side_effects["graph_files"] = {"graph_html": str(final_path)}

        # On live runs only, rename graphspec.json to live_run_graph.json
        graphspec_path = saved_files.get("graphspec_json")
        if graphspec_path and not dry_run:
            final_graphspec_path = graphspec_path.parent / "live_run_graph.json"
            shutil.move(str(graphspec_path), str(final_graphspec_path))
            side_effects.setdefault("graph_files", {})["graph_spec"] = str(final_graphspec_path)

        # The graphspec's companions keep their canonical names beside it: a reader resolves them
        # from the graphspec's directory, not from its name.
        for output_key in ("pipe_io_contracts_json", "input_form_json", "output_form_json"):
            companion_path = saved_files.get(output_key)
            if companion_path:
                side_effects.setdefault("graph_files", {})[output_key.removesuffix("_json")] = str(companion_path)

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
