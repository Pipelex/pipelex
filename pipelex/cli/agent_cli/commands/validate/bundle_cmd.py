"""Agent CLI validate bundle command - validate a bundle file or directory with JSON output."""

import asyncio
from pathlib import Path
from typing import Annotated, Any, NamedTuple

import typer

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import (
    CliOutputFormat,
    agent_error,
    agent_error_validate_bundle,
    agent_file_error,
    agent_success_formatted,
    agent_unreadable_file_error,
    use_agent_cli_error_format,
)
from pipelex.cli.agent_cli.commands.bundle_path_resolver import resolve_bundle_target
from pipelex.cli.agent_cli.commands.validate._validate_core import (
    validate_bundle_core,
    validate_method_folder_core,
    validate_pipe_in_bundle_core,
)
from pipelex.cli.bundle_target_resolution import locate_folder_pipe
from pipelex.cli.commands.run._run_output_folder import bundle_run_outputs_dir, make_run_output_folder, run_output_label
from pipelex.cli.judged_target import JudgedBundleTarget
from pipelex.graph.graph_rendering import GraphFormat
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.mthds_parsing.exceptions import MthdsParserError
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import Pipelex
from pipelex.pipeline.bundle_graph_rendering import GraphOutputFolderMaker, generate_graph_for_bundle, generate_view_for_bundle
from pipelex.pipeline.exceptions import MethodEntryError, PipelineExecutionError, ValidateBundleError
from pipelex.pipeline.validation_render import format_validate_markdown
from pipelex.tools.misc.chart_utils import FlowchartDirection

_GRAPH_UNAVAILABLE_KEY = "graph_unavailable"


class _GraphTarget(NamedTuple):
    """The bundle file a graph is drawn from, the pipe drawn (the one named, else the bundle's or method's entry), and where."""

    bundle_path: Path
    pipe_code: str | None
    #: The directory a `run bundle` of the same target makes its output folders under, where `--graph` makes its own.
    outputs_dir: Path


def _graph_target(*, target: JudgedBundleTarget, pipe: str | None) -> _GraphTarget | str:
    """Where `--graph` and `--view` draw from, or why no graph is drawn.

    A bundle file draws its pipe named, else its own `main_pipe`. A method's folder, judged whole, draws the pipe named,
    in the bundle defining it, else the pipe the method starts at by the MTHDS protocol's rule; when no single bundle
    defines the pipe named, or the method has no single pipe to start at, nothing is drawn and the reason is returned,
    the validation standing as it is.
    """
    if target.bundle_path is not None:
        outputs_dir = bundle_run_outputs_dir(target_path=target.bundle_path, pipe_override=pipe, entry_bundle_file=None)
        return _GraphTarget(bundle_path=target.bundle_path, pipe_code=pipe, outputs_dir=outputs_dir)
    if target.method_tree is None or target.method_dir is None:
        msg = "A method's folder was resolved without its method tree."
        raise PipelexUnexpectedError(msg)
    try:
        entry = locate_folder_pipe(tree=target.method_tree, pipe_override=pipe)
    except MethodEntryError as exc:
        return f"No graph was drawn, since a graph is drawn from one pipe: {exc.message}"
    bundle_path = target.method_tree.file_location(entry.tree_path)
    # A run of the folder writes beside the bundle defining its entry pipe, or in the folder itself when a pipe is named.
    outputs_dir = bundle_run_outputs_dir(target_path=target.method_dir, pipe_override=pipe, entry_bundle_file=bundle_path)
    return _GraphTarget(bundle_path=bundle_path, pipe_code=entry.pipe_ref, outputs_dir=outputs_dir)


def _graph_output_folder_maker(*, outputs_dir: Path) -> GraphOutputFolderMaker:
    """Where `--graph` writes its files: a new numbered folder, `<pipe_code>_output_<NN>/`, under `outputs_dir`.

    `outputs_dir` is where a `run bundle` of the same target makes its output folders, and the folder is made the same
    way, holding a `.gitignore` that ignores everything in it, so the viewer and its graph files never join the method
    tree they were drawn from: validating a method leaves its tree, and its digest, as they were. The envelope names
    each file's path.
    """

    def make_output_folder(*, pipe_code: str) -> Path:
        return make_run_output_folder(output_dir=outputs_dir, label=run_output_label(pipe_ref=pipe_code))

    return make_output_folder


def validate_bundle_cmd(
    path: Annotated[
        str,
        typer.Argument(help="Path to a .mthds bundle file, or a method's folder, whose every bundle is judged"),
    ],
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code to validate (overrides bundle's main_pipe)"),
    ] = None,
    graph: Annotated[
        bool,
        typer.Option(
            "--graph",
            "-g",
            help="On successful bundle validation, save graph HTML files in a new <pipe_code>_output_<NN>/ folder under the results/ "
            "directory a run of the same target writes to, kept out of the method tree, and include their paths in the output",
        ),
    ] = False,
    graph_format: Annotated[
        GraphFormat,
        typer.Option("--graph-format", "-f", help="Graph format to generate: mermaidflow, reactflow, or both"),
    ] = GraphFormat.REACTFLOW,
    direction: Annotated[
        FlowchartDirection | None,
        typer.Option("--direction", help="Flowchart direction"),
    ] = None,
    view: Annotated[
        bool,
        typer.Option("--view", help="On successful bundle validation, include a GraphSpec (structured JSON for graph rendering) in the output"),
    ] = False,
    library_dir: Annotated[
        list[str] | None,
        typer.Option("--library-dir", "-L", help="Directory to search for pipe definitions (.mthds files)"),
    ] = None,
    allow_signatures: Annotated[
        bool,
        typer.Option(
            "--allow-signatures",
            help="Accept PipeSignature placeholders in the dependency graph (lenient mode).",
        ),
    ] = False,
    output_format: Annotated[
        CliOutputFormat,
        typer.Option("--format", help="Success output format: markdown (default) or json (structured)"),
    ] = CliOutputFormat.MARKDOWN,
    error_format: Annotated[
        CliOutputFormat | None,
        typer.Option("--error-format", help="Error output format: markdown or json (defaults to the program's --error-format, then to --format)"),
    ] = None,
) -> None:
    """Validate a bundle file (.mthds) or a method's folder and output the results.

    A folder is judged whole: every bundle of its method tree, with no pipe to start at needed. --pipe narrows the dry
    run to one pipe. --graph and --view draw the pipe named, else the method's main pipe, and say so when it has none.

    Default output is markdown; use --format json for structured JSON.
    Results go to stdout on success, errors to stderr with exit code 1.

    Examples:
        pipelex-agent validate bundle my_bundle.mthds
        pipelex-agent validate bundle my_bundle.mthds --pipe my_pipe
        pipelex-agent validate bundle my_bundle.mthds --graph
        pipelex-agent validate bundle my_method/
        pipelex-agent validate bundle my_method/ --pipe my_domain.my_pipe
        pipelex-agent validate bundle my_method/ --graph
        pipelex-agent validate bundle draft_pipeline.mthds --allow-signatures
    """
    use_agent_cli_error_format(error_format=error_format, output_format=output_format)

    # A folder is judged whole, as the MTHDS protocol's validation judges a method: every bundle of its tree.
    try:
        target = resolve_bundle_target(path, library_dir=library_dir)
    except ValidateBundleError as exc:
        agent_error_validate_bundle(
            exc,
            bundle_path=Path(path).expanduser(),
            library_dirs=[Path(lib_dir).expanduser() for lib_dir in library_dir] if library_dir else None,
            allow_signatures=allow_signatures,
        )
    # The path judged: the method's folder, or the bundle file.
    judged_path = target.judged_path
    library_dirs = target.library_dirs

    # Convert library_dirs to list[str] for graph helper
    library_dir_strings = [str(lib_dir) for lib_dir in library_dirs] if library_dirs else None

    make_pipelex_for_agent_cli(library_dirs=library_dirs, needs_inference=False)

    try:
        if target.method_dir is not None:
            # The whole method, every pipe of it, or only the pipe named while the whole tree loads
            result = asyncio.run(
                validate_method_folder_core(
                    method_dir=target.method_dir, library_dirs=library_dirs, allow_signatures=allow_signatures, pipe_code=pipe
                )
            )
        elif pipe:
            # Validate a specific pipe within the bundle
            result = asyncio.run(
                validate_pipe_in_bundle_core(bundle_path=judged_path, pipe_code=pipe, library_dirs=library_dirs, allow_signatures=allow_signatures)
            )
        else:
            # Validate the entire bundle
            result = asyncio.run(validate_bundle_core(bundle_path=judged_path, library_dirs=library_dirs, allow_signatures=allow_signatures))

        graph_target: _GraphTarget | str | None = _graph_target(target=target, pipe=pipe) if graph or view else None
        if isinstance(graph_target, str):
            result[_GRAPH_UNAVAILABLE_KEY] = graph_target

        # Generate graph if requested and validation succeeded
        if graph and isinstance(graph_target, _GraphTarget):
            try:
                graph_result = asyncio.run(
                    generate_graph_for_bundle(
                        bundle_path=graph_target.bundle_path,
                        graph_format=graph_format,
                        make_output_folder=_graph_output_folder_maker(outputs_dir=graph_target.outputs_dir),
                        library_dirs=library_dir_strings,
                        pipe_code=graph_target.pipe_code,
                        direction=direction,
                    )
                )
                result.update(graph_result)
            except PipelineExecutionError as exc:
                agent_error(
                    f"Graph generation failed: {exc.message}",
                    cause=exc,
                    exit_code=2,
                )
            except MthdsParserError as exc:
                agent_error(f"Graph generation failed: {exc}", cause=exc, exit_code=2)
            except typer.Exit:
                raise
            except Exception as exc:  # ruff: ignore[blind-except]
                # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into its problem.
                agent_error(f"Graph generation failed: {exc}", cause=exc, exit_code=2)

        # Generate view (GraphSpec JSON) if requested and validation succeeded
        if view and isinstance(graph_target, _GraphTarget):
            try:
                view_result = asyncio.run(
                    generate_view_for_bundle(
                        bundle_path=graph_target.bundle_path,
                        library_dirs=library_dir_strings,
                        pipe_code=graph_target.pipe_code,
                        direction=direction,
                    )
                )
                result.update(view_result)
            except PipelineExecutionError as exc:
                agent_error(
                    f"View generation failed: {exc.message}",
                    cause=exc,
                    exit_code=2,
                )
            except MthdsParserError as exc:
                agent_error(f"View generation failed: {exc}", cause=exc, exit_code=2)
            except typer.Exit:
                raise
            except Exception as exc:  # ruff: ignore[blind-except]
                # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into its problem.
                agent_error(f"View generation failed: {exc}", cause=exc, exit_code=2)

        agent_success_formatted(result, markdown_renderer=format_validate_markdown, output_format=output_format)

        # Gate-from-report (D-B consumer-decides): the bundle is valid, but unsatisfied PipeSignature
        # placeholders make it NOT runnable. The success envelope (carrying pending_signatures +
        # is_runnable) is already emitted above; the exit code — not a fabricated error item — reflects
        # the gate. --allow-signatures tolerates the placeholders (exit 0). Re-raised by the
        # `except typer.Exit` arm below so teardown still runs.
        #
        # Only the whole-bundle path gates: with --pipe, `result` is the slice envelope whose
        # is_runnable derives from LIBRARY-WIDE pending_signatures, so gating there would fail a
        # fully-implemented slice for unrelated placeholders elsewhere in the bundle. The slice makes
        # no library-wide runnability claim (mirroring `validate pipe`), so it is not gated.
        if not pipe and not allow_signatures and not result.get("is_runnable", True):
            raise typer.Exit(1)

    except PipeNotFoundError as exc:
        # The real class, not the caught base — see the same arm in `validate pipe`.
        agent_error(str(exc), cause=exc, exit_code=2)

    except FileNotFoundError as exc:
        agent_file_error(f"Bundle file not found: {judged_path}", path=str(judged_path), reason="not found", cause=exc, exit_code=2)

    except OSError as exc:
        # A method file this machine would not let the command read: the file, never a fault of the method. An error
        # naming no file, a connection or a timeout, is the unexpected failure the boundary reports.
        agent_unreadable_file_error(error=exc, exit_code=2)

    except ValidateBundleError as exc:
        # Invalid verdict: the problem of the method that does not validate, format-aware. Its errors are
        # the shared builder's items, non-empty on every invalid verdict, beside the is_valid:false
        # discriminant; markdown renders those items as prose with a fix-aware footer. Signatures never
        # reach here (they are a runnability fact, gated above).
        agent_error_validate_bundle(exc, bundle_path=judged_path, library_dirs=library_dirs, allow_signatures=allow_signatures)

    except PipeOperatorModelAvailabilityError as exc:
        availability_extra: dict[str, Any] = {
            "pipe_code": exc.pipe_code,
            "model_handle": exc.model_handle,
        }
        if exc.fallback_list:
            availability_extra["fallback_list"] = exc.fallback_list
        if exc.pipe_stack:
            availability_extra["pipe_stack"] = exc.pipe_stack
        agent_error(exc.message, cause=exc, exit_code=2, **availability_extra)

    except typer.Exit:
        raise

    except Exception as exc:  # ruff: ignore[blind-except]
        # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into its problem.
        agent_error(str(exc), cause=exc, exit_code=2)

    finally:
        Pipelex.teardown_if_needed()
