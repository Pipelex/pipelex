from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from pipelex.base_exceptions import PipelexConfigError, PipelexUnexpectedError
from pipelex.cli.bundle_target_resolution import list_bundle_file_tree, resolve_method_folder_run
from pipelex.cli.commands.run._hosted_sources import collect_mthds_files, hosted_library_dirs
from pipelex.cli.commands.run._inputs_file_loader import DetectedInputsFile, read_default_inputs_file
from pipelex.cli.commands.run._run_core import COMMAND, execute_run, validate_run_flag_combination
from pipelex.cli.commands.run._run_hosted import bundle_main_pipe_code, execute_hosted_run, refuse_local_only_flags, resolve_cli_run_execution
from pipelex.cli.commands.run._run_output_folder import run_output_label
from pipelex.cli.commands.run.exceptions import AmbiguousInputsFilesError, AutoDetectedInputsFileError
from pipelex.cli.error_handlers import handle_pre_boot_config_error, handle_validate_bundle_error
from pipelex.hosted.exceptions import HostedRunSourceError
from pipelex.libraries.method_tree_listing import MethodTreeListing
from pipelex.mthds_parsing.helpers import is_pipelex_file
from pipelex.pipeline.exceptions import MethodEntryError, ValidateBundleError

if TYPE_CHECKING:
    from mthds.method_tree.models import MethodTree


def run_bundle_cmd(
    path: Annotated[
        str,
        typer.Argument(help="Path to a .mthds bundle file, or a method's folder, which starts at its entry pipe unless --pipe names one"),
    ],
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code to run (overrides bundle's main_pipe)"),
    ] = None,
    inputs: Annotated[
        str | None,
        typer.Option("--inputs", "-i", help="Inputs: a JSON or TOML file (by its extension), or inline JSON starting with {"),
    ] = None,
    save_working_memory: Annotated[
        bool,
        typer.Option("--save-working-memory/--no-save-working-memory", help="Save working memory to JSON file"),
    ] = True,
    working_memory_path: Annotated[
        str | None,
        typer.Option("--working-memory-path", help="Custom path to save working memory JSON"),
    ] = None,
    save_main_stuff: Annotated[
        bool,
        typer.Option("--save-main-stuff/--no-save-main-stuff", help="Save main_stuff in JSON and Markdown formats"),
    ] = True,
    no_pretty_print: Annotated[
        bool,
        typer.Option("--no-pretty-print", help="Skip pretty printing the main_stuff"),
    ] = False,
    graph: Annotated[
        bool | None,
        typer.Option(
            "--graph/--no-graph",
            help="Override config: enable or disable execution graph outputs (JSON, Mermaid, HTML)",
        ),
    ] = None,
    graph_full_data: Annotated[
        bool | None,
        typer.Option(
            "--graph-full-data/--graph-no-data",
            help="Override config: include or exclude full serialized data in graph",
        ),
    ] = None,
    output_dir: Annotated[
        str,
        typer.Option("--output-dir", "-o", help="Base directory for all outputs (working memory, main_stuff, graphs)"),
    ] = "results",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Run pipeline in dry mode (no actual inference calls)"),
    ] = False,
    mock_usage: Annotated[
        bool,
        typer.Option(
            "--mock-usage",
            hidden=True,
            help="Internal test trigger: dry run whose LLM leaf mocks report nonzero synthetic usage so the cost report renders. Requires --dry-run.",
        ),
    ] = False,
    mock_inputs: Annotated[
        bool,
        typer.Option("--mock-inputs", help="Generate mock data for missing required inputs (requires --dry-run)"),
    ] = False,
    library_dir: Annotated[
        list[str] | None,
        typer.Option("--library-dir", "-L", help="Directory to search for pipe definitions (.mthds files). Can be specified multiple times."),
    ] = None,
    orchestrator: Annotated[
        str | None,
        typer.Option("--orchestrator", help="Boot this process under the named orchestrator plugin (e.g. 'temporal'); omit for in-process execution"),
    ] = None,
    dynamic_output_concept_ref: Annotated[
        str | None,
        typer.Option(
            "--dynamic-output-concept",
            "-O",
            help="Concept ref (e.g. 'document_qa.ReferenceCount') used to resolve a pipe whose output is declared as 'Dynamic'.",
        ),
    ] = None,
    costs: Annotated[
        bool | None,
        typer.Option(
            "--costs/--no-costs",
            help="Override config: emit usage (cost) tracing events and render the end-of-run cost report. Default on.",
        ),
    ] = None,
    save_csv: Annotated[
        str | None,
        typer.Option(
            "--save-csv",
            help="Write the main stuff to this literal CSV path (not under --output-dir; absolute/~/relative ok). Requires a flat list output.",
        ),
    ] = None,
    hosted: Annotated[
        bool | None,
        typer.Option(
            "--hosted/--local",
            # Typer renders help as Rich markup, which drops an unescaped [run]: \[ prints the bracket.
            help=r"Run on the hosted Pipelex API (key in PIPELEX_API_KEY) or on this machine. Default: \[run] execution, else local.",
        ),
    ] = None,
    base_url: Annotated[
        str | None,
        typer.Option(
            "--base-url",
            help="Origin of the hosted API a hosted run calls, scheme://host[:port]. Overrides PIPELEX_BASE_URL; default https://api.pipelex.com.",
        ),
    ] = None,
) -> None:
    """Run a pipeline from a bundle file (.mthds) or pipeline directory.

    Examples:
        pipelex run bundle pipeline_01/
        pipelex run bundle pipeline_01/ --pipe my_pipe
        pipelex run bundle my_bundle.mthds
        pipelex run bundle my_bundle.mthds --pipe my_pipe --inputs data.json
        pipelex run bundle pipeline_01/ --dry-run
        pipelex run bundle pipeline_01/ --hosted
    """
    validate_run_flag_combination(dry_run=dry_run, mock_usage=mock_usage, mock_inputs=mock_inputs)

    pipe_code: str | None = pipe
    bundle_path: str | None = None
    # `--inputs` as given, or the inputs file auto-detection read from the method's folder.
    run_inputs: str | DetectedInputsFile | None = inputs
    target_path = Path(path)

    # The method tree the run reads, whose digest the run records: the folder's, or the bundle file's own. It is listed
    # once, through the listing the run's load takes it from.
    method_tree: MethodTree
    tree_listing = MethodTreeListing()
    # The pipe a hosted run names: `--pipe`, else the main pipe the local run starts at, qualified by its domain, so the
    # hosted API starts at the same pipe when two domains of the files it is sent define the same code.
    hosted_pipe_code: str | None = pipe
    if target_path.is_dir():
        # Directory mode: the method rooted at or above the folder, started where the protocol's rule says
        try:
            folder_run = resolve_method_folder_run(directory=target_path, pipe_override=pipe, tree_listing=tree_listing)
        except ValidateBundleError as exc:
            handle_validate_bundle_error(exc, library_dirs=[Path(one_dir) for one_dir in library_dir] if library_dir else None)
        except MethodEntryError as entry_exc:
            # No pipe to start at is no verdict on the method, which may be valid: the run names none, and the message
            # names the folder's bundles by their tree paths and what each declares.
            typer.secho(f"Failed to run: {entry_exc.message}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from entry_exc
        except PipelexConfigError as exc:
            # Listing the tree reads its limits from the configuration, before the boot would.
            handle_pre_boot_config_error(exc=exc, command=COMMAND, exit_code=1)
        method_tree = folder_run.tree
        pipe_code = folder_run.pipe_code
        if folder_run.entry is not None and folder_run.entry_bundle_file is not None:
            bundle_path = str(folder_run.entry_bundle_file)
            hosted_pipe_code = folder_run.entry.pipe_ref
            typer.echo(f"Starting at the method's main pipe {folder_run.entry.pipe_ref}, in {folder_run.entry.tree_path}")

        # Auto-detect inputs (inputs.json or inputs.toml) if --inputs not explicitly provided. The run parses the
        # bytes the probe read without following a link, and never opens the path again.
        if not inputs:
            try:
                detected_inputs = read_default_inputs_file(directory=target_path)
            except (AmbiguousInputsFilesError, AutoDetectedInputsFileError) as inputs_file_exc:
                typer.secho(f"Failed to run: {inputs_file_exc.message}", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from inputs_file_exc
            if detected_inputs is not None:
                run_inputs = detected_inputs
                typer.echo(f"Auto-detected inputs: {detected_inputs.path}")

        # Add directory as library dir
        target_dir_str = str(target_path)
        if library_dir is None:
            library_dir = [target_dir_str]
        elif target_dir_str not in library_dir:
            library_dir = [target_dir_str, *library_dir]

    elif is_pipelex_file(target_path):
        bundle_path = path
        try:
            method_tree = list_bundle_file_tree(bundle_file=target_path, tree_listing=tree_listing)
        except ValidateBundleError as exc:
            handle_validate_bundle_error(
                exc, bundle_path=target_path, library_dirs=[Path(one_dir) for one_dir in library_dir] if library_dir else None
            )
        except PipelexConfigError as exc:
            handle_pre_boot_config_error(exc=exc, command=COMMAND, exit_code=1)
    else:
        typer.secho(
            f"Failed to run: '{path}' is not a .mthds file or directory.\n"
            f"  To run a pipe by code, use: pipelex run pipe <code>\n"
            f"  To run a bundle, pass a .mthds file or directory: pipelex run bundle <path>",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    execution = resolve_cli_run_execution(hosted=hosted, base_url=base_url)
    if execution.is_hosted:
        refuse_local_only_flags(
            dry_run=dry_run,
            mock_usage=mock_usage,
            mock_inputs=mock_inputs,
            orchestrator=orchestrator,
            save_csv=save_csv,
            costs=costs,
            graph_full_data=graph_full_data,
        )
        if hosted_pipe_code is None:
            if bundle_path is None:
                msg = "A hosted run of a method's folder names its pipe, or the bundle defining its main pipe."
                raise PipelexUnexpectedError(msg)
            hosted_pipe_code = bundle_main_pipe_code(bundle_path=bundle_path, library_dirs=library_dir)
        # The entry bundle goes first, then the rest of the library a local run would load with it: the method's folder
        # and -L, else PIPELEXPATH.
        try:
            bundle_files = collect_mthds_files(
                primary=Path(bundle_path) if bundle_path else None, library_dirs=hosted_library_dirs(library_dirs=library_dir)
            )
        except HostedRunSourceError as exc:
            typer.secho(f"Failed to run: {exc.message}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc
        execute_hosted_run(
            mthds_files=bundle_files,
            pipe_code=hosted_pipe_code,
            inputs=run_inputs,
            dynamic_output_concept_ref=dynamic_output_concept_ref,
            base_url=base_url,
            output_label=run_output_label(pipe_ref=hosted_pipe_code),
            output_dir=output_dir,
            save_working_memory=save_working_memory,
            working_memory_path=working_memory_path,
            save_main_stuff=save_main_stuff,
            no_pretty_print=no_pretty_print,
            graph=graph,
        )
        return

    execute_run(
        pipe_code=pipe_code,
        bundle_path=bundle_path,
        inputs=run_inputs,
        save_working_memory=save_working_memory,
        working_memory_path=working_memory_path,
        save_main_stuff=save_main_stuff,
        no_pretty_print=no_pretty_print,
        graph=graph,
        graph_full_data=graph_full_data,
        output_dir=output_dir,
        dry_run=dry_run,
        mock_usage=mock_usage,
        mock_inputs=mock_inputs,
        library_dir=library_dir,
        costs=costs,
        telemetry_command_label=f"{COMMAND} bundle",
        orchestrator=orchestrator,
        dynamic_output_concept_ref=dynamic_output_concept_ref,
        save_csv=save_csv,
        method_tree=method_tree,
        tree_listing=tree_listing,
    )
