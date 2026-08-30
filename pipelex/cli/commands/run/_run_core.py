from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

import typer
from posthog import tag

from pipelex import log
from pipelex.base_exceptions import PipelexError
from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.commands.run._inputs_file_loader import load_inputs_dict_from_path
from pipelex.cli.commands.run._inputs_path_resolver import resolve_inputs_paths
from pipelex.cli.error_handlers import (
    ErrorContext,
    handle_model_availability_error,
    handle_model_choice_error,
    print_traceback_if_requested,
)
from pipelex.config import get_config
from pipelex.core.concepts.exceptions import ConceptValueError
from pipelex.core.memory.absence import AbsenceRecord
from pipelex.core.memory.absence_render import build_absence_json, build_absence_markdown
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_viewer import render_stuff_viewer
from pipelex.graph.graph_factory import generate_graph_outputs, save_graph_outputs_to_dir
from pipelex.interpreter_hub import clear_current_library, get_concept_library, get_library_manager
from pipelex.mthds_parsing.exceptions import MthdsParserError
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import Pipelex
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.execution_seams import acquire_library
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.reporting.cost_report_renderer import render_cost_report_for_output
from pipelex.runtime_hub import get_console, get_telemetry_manager
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventProperty
from pipelex.tools.misc.exceptions import JsonTypeError, TomlError
from pipelex.tools.misc.file_utils import get_incremental_directory_path
from pipelex.tools.misc.json_utils import save_as_json_to_path
from pipelex.tools.misc.package_utils import get_package_version
from pipelex.tools.tabular.csv_codec import assert_supported_table_suffix, csv_from_list_content, flat_field_names
from pipelex.tools.tabular.exceptions import CsvError

if TYPE_CHECKING:
    from pipelex.core.concepts.concept import Concept
    from pipelex.core.stuffs.stuff_content import StuffContent

COMMAND = "run"


def validate_run_flag_combination(*, dry_run: bool, mock_usage: bool, mock_inputs: bool) -> None:
    """Reject illegal ``--dry-run`` / ``--mock-usage`` / ``--mock-inputs`` combinations.

    Single owner of which run-flag combinations are legal, shared by the ``pipe`` / ``method`` / ``bundle``
    run subcommands so they can't drift:

    - ``--mock-inputs`` requires ``--dry-run`` — it synthesizes missing required inputs for a dry
      run; a live run must be fed real inputs.
    - ``--mock-usage`` (hidden test trigger) requires ``--dry-run`` — it is a sub-flag of the dry
      run (non-zero synthetic usage so the cost report renders); on a live run it is a contract
      violation.

    Prints the offending combination to stderr and raises ``typer.Exit(1)``; returns ``None`` when the
    combination is legal.
    """
    if mock_inputs and not dry_run:
        typer.secho("Failed to run: --mock-inputs requires --dry-run", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    if mock_usage and not dry_run:
        typer.secho("Failed to run: --mock-usage requires --dry-run", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)


def _resolve_row_model_for_empty_result(
    *,
    concept: Concept,
    bundle_path: str | None,
    mthds_content: str | None,
    library_dir: list[str] | None,
) -> type[StuffContent]:
    """Resolve the CSV row model for a run that produced no rows, by reloading its bundle.

    A run whose main output is an empty list leaves no instance to read the row class off, and the
    run's own library — which owned the ClassRegistry holding its generated structure classes — is
    torn down by the time ``--save-csv`` runs. Reloading the same bundle into a throwaway library
    regenerates the declared concept's structure class under the same name and fields, which is what
    the header needs. The load inputs are the ones handed to the runner just above, so the two see
    the same bundle. The library is torn down again immediately; only the resolved class survives.
    """
    library_id, _main_pipe = acquire_library(
        library_id="",
        library_dirs=library_dir,
        mthds_contents=[mthds_content] if mthds_content else None,
        bundle_uris=[bundle_path] if bundle_path else None,
    )
    try:
        return get_concept_library().get_structure_class(concept=concept)
    finally:
        clear_current_library()
        get_library_manager().teardown(library_id=library_id)


async def _execute_run(
    *,
    pipe_code: str | None,
    bundle_path: str | None,
    inputs: str | None,
    save_working_memory: bool,
    working_memory_path: str | None,
    save_main_stuff: bool,
    no_pretty_print: bool,
    graph: bool | None,
    graph_full_data: bool | None,
    output_dir: str,
    dry_run: bool,
    mock_usage: bool,
    mock_inputs: bool,
    library_dir: list[str] | None,
    costs: bool | None = None,
    dynamic_output_concept_ref: str | None = None,
    save_csv: str | None = None,
) -> None:
    """Core async execution logic for running a pipe.

    Shared between the ``method`` and ``pipe`` subcommands.
    """
    # Fail fast on an unusable --save-csv target BEFORE running the pipeline, so a bad path (empty,
    # or an unsupported suffix like .xlsx) doesn't waste a full inference run. The output-shape and
    # row-flatness checks need the result, so they stay in the save block after execution.
    if save_csv is not None:
        if not save_csv.strip():
            typer.secho("Failed to --save-csv: an empty output path was given.", fg=typer.colors.RED, err=True)
            raise typer.Exit(1)
        try:
            assert_supported_table_suffix(Path(save_csv))
        except CsvError as exc:
            typer.secho(f"Failed to --save-csv: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc

    mthds_content: str | None = None
    if bundle_path:
        try:
            mthds_content = Path(bundle_path).read_text(encoding="utf-8")
            # Use lightweight parsing to extract main_pipe without full validation
            # Full validation happens later during execute
            if not pipe_code:
                bundle_blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=mthds_content)
                main_pipe_code = bundle_blueprint.main_pipe
                if not main_pipe_code:
                    msg = (
                        f"Bundle '{bundle_path}' does not declare a main_pipe. In order to run a bundle, "
                        "you must specify a main pipe in the bundle itself or specify a pipe code in the command line using the --pipe option."
                    )
                    typer.secho(msg, fg=typer.colors.RED, err=True)
                    raise typer.Exit(1)
                pipe_code = main_pipe_code
        except FileNotFoundError as exc:
            print_traceback_if_requested(console=get_console())
            typer.secho(f"Failed to load bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc
        except MthdsParserError as exc:
            print_traceback_if_requested(console=get_console())
            typer.secho(f"Failed to parse bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc
    elif not pipe_code:
        typer.secho("Failed to run: no pipe code specified", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    # Load inputs if provided
    pipeline_inputs = None
    # Directory bare relative file paths resolve against (Smart Inputs D3). Set only when inputs are
    # file-loaded (its parent); None for inline JSON — an inline caller has no file to anchor to.
    inputs_base_dir: Path | None = None
    if inputs:
        if inputs.startswith("{"):
            try:
                pipeline_inputs = json.loads(inputs)
            except json.JSONDecodeError as json_decode_exc:
                print_traceback_if_requested(console=get_console())
                typer.secho(f"Failed to parse inline JSON inputs: {json_decode_exc}", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from json_decode_exc
        else:
            try:
                # expanduser so a quoted / `=`-form `~/inputs.json` resolves to the home dir, not a
                # literal `~` component (unquoted `~` is shell-expanded, but the quoted/`=` forms are not).
                inputs_path = Path(inputs).expanduser()
                pipeline_inputs = load_inputs_dict_from_path(inputs_path)
                # Resolve relative url paths against the inputs file's parent directory. The same
                # directory is threaded to the runner as inputs_base_dir so the shaper can resolve
                # bare relative file-ish / CSV strings (whose declared concept the CLI cannot see).
                inputs_base_dir = inputs_path.parent.resolve()
                pipeline_inputs = resolve_inputs_paths(pipeline_inputs, base_dir=inputs_base_dir)
                typer.echo(f"Loaded inputs from: {inputs}")
            except FileNotFoundError as file_not_found_exc:
                print_traceback_if_requested(console=get_console())
                typer.secho(f"Failed to load input file '{inputs}': file not found", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from file_not_found_exc
            except json.JSONDecodeError as json_decode_exc:
                print_traceback_if_requested(console=get_console())
                typer.secho(f"Failed to parse input file '{inputs}': invalid JSON: {json_decode_exc}", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from json_decode_exc
            except JsonTypeError as json_type_error_exc:
                print_traceback_if_requested(console=get_console())
                typer.secho(f"Failed to parse input file '{inputs}': must be a valid JSON dictionary", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from json_type_error_exc
            except TomlError as toml_error_exc:
                print_traceback_if_requested(console=get_console())
                typer.secho(f"Failed to parse input file: {toml_error_exc.message}", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from toml_error_exc

    # Determine pipe run mode
    pipe_run_mode = PipeRunMode.DRY if dry_run else None

    # Build effective execution config with CLI overrides
    execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(
        generate_graph=graph,
        generate_usage=costs,
        force_include_full_data=graph_full_data,
        mock_inputs=mock_inputs or None,
    )

    try:
        runner = PipelexMTHDSProtocol(
            bundle_uris=[bundle_path] if bundle_path else None,
            pipe_run_mode=pipe_run_mode,
            is_mock_usage=mock_usage,
            execution_config=execution_config,
            library_dirs=library_dir,
            inputs_base_dir=inputs_base_dir,
        )
        response = await runner.execute(
            pipe_code=pipe_code,
            mthds_contents=[mthds_content] if mthds_content else None,
            inputs=pipeline_inputs,
            dynamic_output_concept_ref=dynamic_output_concept_ref,
        )
        pipe_output = response.pipe_output
    except PipelineExecutionError as exc:
        print_traceback_if_requested(console=get_console())
        typer.secho(f"Failed to execute pipeline '{exc.pipe_code}': {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    except PipelexError as exc:
        print_traceback_if_requested(console=get_console())
        typer.secho(f"Failed to execute pipeline '{pipe_code or bundle_path}': {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc

    # Pretty print the resolved main result unless disabled or in dry run mode. A completed run
    # always resolves its declared output: a value or a recorded absence.
    main_resolved = pipe_output.working_memory.resolve_main_stuff()
    if not no_pretty_print and not dry_run:
        if isinstance(main_resolved, AbsenceRecord):
            get_console().print(
                f"Final output of pipe [red]{pipe_code}[/red] resolved absent: {main_resolved.reason}",
            )
        else:
            title = f"Final output of pipe [red]{pipe_code}[/red]"
            main_resolved.pretty_print_stuff(title=title)

    # Determine if we need an output directory
    output_path: Path | None = None
    graph_spec = pipe_output.graph_spec
    needs_output_path = (graph_spec is not None) or save_main_stuff or save_working_memory

    if needs_output_path:
        output_path = get_incremental_directory_path(base_path=Path(output_dir), base_name=f"{pipe_code}_output")
        output_path.mkdir(parents=True, exist_ok=True)

    # Save graph outputs if requested
    saved_graphs: list[str] = []
    if graph_spec:
        if not output_path:
            typer.secho("Failed to save graphs: no output directory specified", fg=typer.colors.RED, err=True)
            raise typer.Exit(1)

        graph_outputs = await generate_graph_outputs(
            graph_spec=graph_spec,
            graph_config=execution_config.graph,
            pipe_code=pipe_code,
        )

        saved_graph_files = save_graph_outputs_to_dir(graph_outputs=graph_outputs, output_dir=output_path)
        for output_type in saved_graph_files:
            if "mermaidflow" in output_type and "mermaidflow" not in saved_graphs:
                saved_graphs.append("mermaidflow")
            elif "reactflow" in output_type and "reactflow" not in saved_graphs:
                saved_graphs.append("reactflow")

    # Save main_stuff files if enabled. An absent main output saves the explicit absence
    # artifact (json + md, no interactive viewer — nothing to view), never value renders.
    saved_main_stuff_formats: list[str] = []
    if save_main_stuff and output_path:
        if isinstance(main_resolved, AbsenceRecord):
            absence_json_path = output_path / "main_stuff.json"
            absence_json_path.write_text(build_absence_json(main_resolved), encoding="utf-8")
            log.verbose(f"Main stuff absence JSON saved to: {absence_json_path}")
            saved_main_stuff_formats.append("json")

            absence_md_path = output_path / "main_stuff.md"
            absence_md_path.write_text(build_absence_markdown(main_resolved), encoding="utf-8")
            log.verbose(f"Main stuff absence Markdown saved to: {absence_md_path}")
            saved_main_stuff_formats.append("md")
        else:
            main_stuff = main_resolved
            main_stuff_json = await main_stuff.content.rendered_json_async()
            main_stuff_json_path = output_path / "main_stuff.json"
            main_stuff_json_path.write_text(main_stuff_json, encoding="utf-8")
            log.verbose(f"Main stuff JSON saved to: {main_stuff_json_path}")
            saved_main_stuff_formats.append("json")

            main_stuff_md = await main_stuff.content.rendered_markdown_async()
            main_stuff_md_path = output_path / "main_stuff.md"
            main_stuff_md_path.write_text(main_stuff_md, encoding="utf-8")
            log.verbose(f"Main stuff Markdown saved to: {main_stuff_md_path}")
            saved_main_stuff_formats.append("md")

            main_stuff_html = await main_stuff.content.rendered_html_async()
            main_stuff_html_path = output_path / "main_stuff.html"
            main_stuff_html_path.write_text(main_stuff_html, encoding="utf-8")
            log.verbose(f"Main stuff HTML saved to: {main_stuff_html_path}")
            saved_main_stuff_formats.append("html")

            main_stuff_viewer = await render_stuff_viewer(main_stuff)
            main_stuff_viewer_path = output_path / "main_stuff_viewer.html"
            main_stuff_viewer_path.write_text(main_stuff_viewer, encoding="utf-8")
            log.verbose(f"Main stuff HTML viewer saved to: {main_stuff_viewer_path}")
            saved_main_stuff_formats.append("html_viewer")

    # Save working memory to JSON if enabled
    working_memory_output_path: str | None = None
    if save_working_memory and output_path:
        if working_memory_path:
            working_memory_output_path = working_memory_path
        else:
            working_memory_output_path = str(output_path / "working_memory.json")
        working_memory_dict = pipe_output.working_memory.smart_dump()
        save_as_json_to_path(object_to_save=working_memory_dict, path=Path(working_memory_output_path))
        log.verbose(f"Working memory saved to: {working_memory_output_path}")

    # Save main_stuff as CSV if requested. CQ1: write to the literal <path> (cwd-relative),
    # NOT resolved under --output-dir. Requires the main stuff to be a flat list (e.g. PersonSummary[]);
    # the codec rejects a non-flat row concept with a clear CsvFlatnessError.
    if save_csv is not None:
        # The path string and its suffix were already validated up front (fail-fast, before the run).
        if isinstance(main_resolved, AbsenceRecord):
            typer.secho(
                f"Failed to --save-csv: the main output resolved absent ({main_resolved.reason}). "
                "CSV output requires the pipe to produce a flat list (e.g. 'PersonSummary[]').",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(1)
        csv_main_stuff = main_resolved
        csv_content = csv_main_stuff.content
        if not isinstance(csv_content, ListContent):
            typer.secho(
                f"Failed to --save-csv: the main stuff is a {type(csv_content).__name__}, not a list. "
                "CSV output requires the pipe to produce a flat list (e.g. 'PersonSummary[]').",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(1)
        csv_list_content = cast("ListContent[StuffContent]", csv_content)
        # expanduser so a quoted/`=`-form `~/out.csv` writes to the home dir, not a literal `./~` dir.
        csv_path = Path(save_csv).expanduser()
        # A CSV-save failure (output concept with no structure class, non-flat output, write error) is
        # framed as a --save-csv failure, not a pipeline failure — the pipeline already succeeded.
        # ConceptValueError (a ValueError) and CsvError would otherwise escape execute_run's generic
        # `except PipelexError` and read as "Failed to execute pipeline" (or as a raw traceback).
        try:
            # Resolving the row model is the one post-run step that needs the run's library, and
            # `runner.execute` tore that library down on its way out — along with the ClassRegistry its
            # dynamically generated structure classes were registered in. So there is no ambient registry
            # left to resolve `<domain>__<Concept>` by name against, and the model is recovered two ways:
            # from the rows the run produced (each is an instance of exactly the class the pipeline
            # structured its output into), and — for an empty result, which has no instance to ask —
            # by reloading the bundle into a throwaway library just long enough to resolve the declared
            # concept's class. The reload is what keeps `--save-csv` writing a correct header-only file
            # for a run that produced no rows. Its failures are ConceptValueError/PipelexError, framed as
            # a save-csv failure by the guard below rather than escaping as a pipeline failure.
            csv_row_model: type[StuffContent]
            if csv_list_content.items:
                csv_row_model = type(csv_list_content.items[0])
            else:
                csv_row_model = _resolve_row_model_for_empty_result(
                    concept=csv_main_stuff.concept,
                    bundle_path=bundle_path,
                    mthds_content=mthds_content,
                    library_dir=library_dir,
                )
            # Validate the row flatness BEFORE touching the filesystem, so a non-flat output leaves no
            # directory behind (the suffix was already validated up front).
            flat_field_names(csv_row_model)
            # CQ1: write to the literal cwd-relative path, but still create its parent dirs so a
            # nested target (e.g. reports/2026/out.csv) doesn't fail late after the run completed.
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            csv_from_list_content(csv_list_content, row_model=csv_row_model, path=csv_path)
        except (CsvError, ConceptValueError, PipelexError, OSError) as csv_exc:
            typer.secho(f"Failed to --save-csv to '{save_csv}': {csv_exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from csv_exc
        log.verbose(f"Main stuff CSV saved to: {save_csv}")

    # Render the end-of-run cost report from the usage assembled onto pipe_output (event-sourced).
    # The gate is read off the output itself — pipe_output.tokens_usages is None exactly when cost
    # reporting was off for this run — so the submitter no longer re-derives it from config. Channels
    # (console / CSV) follow the reporting config (D6).
    render_cost_report_for_output(pipe_output)

    # Print completion recap
    console = get_console()
    if dry_run:
        console.print("\n[yellow]✓[/yellow] [bold]Dry run completed successfully[/bold]")
    else:
        console.print("\n[green]✓[/green] [bold]Pipeline execution completed successfully[/bold]")
    if output_path:
        console.print(f"  Output saved to [bold magenta]{output_path}[/bold magenta]:")
        if saved_graphs:
            console.print(f"    [green]✓[/green] graphs: {', '.join(saved_graphs)}")
        if saved_main_stuff_formats:
            console.print(f"    [green]✓[/green] main_stuff: {', '.join(saved_main_stuff_formats)}")
        if working_memory_output_path:
            if Path(working_memory_output_path).is_relative_to(output_path):
                console.print("    [green]✓[/green] working_memory.json")
            else:
                console.print(f"    [green]✓[/green] working_memory: {working_memory_output_path}")
    # CSV output is written to a literal cwd-relative path (CQ1), independent of --output-dir.
    if save_csv is not None:
        console.print(f"  [green]✓[/green] CSV saved to [bold magenta]{save_csv}[/bold magenta]")


def execute_run(
    *,
    pipe_code: str | None,
    bundle_path: str | None,
    inputs: str | None,
    save_working_memory: bool,
    working_memory_path: str | None,
    save_main_stuff: bool,
    no_pretty_print: bool,
    graph: bool | None,
    graph_full_data: bool | None,
    output_dir: str,
    dry_run: bool,
    mock_usage: bool,
    mock_inputs: bool,
    library_dir: list[str] | None,
    costs: bool | None = None,
    telemetry_command_label: str = COMMAND,
    orchestrator: str | None = None,
    dynamic_output_concept_ref: str | None = None,
    save_csv: str | None = None,
) -> None:
    """Synchronous entry point that wraps the async execution with Pipelex setup/teardown.

    Shared between the ``method`` and ``pipe`` subcommands.
    """
    # A dry run makes no inference call, so it must not demand credentials: `needs_inference=False`
    # forces every run to DRY and skips a backend whose key is missing instead of failing the boot.
    # `needs_model_specs=True` keeps the real gateway model specs (not the dummy ones), so wherever
    # credentials ARE present a dry run resolves model handles exactly as a live run would. It does not
    # help on a machine with no key at all: a skipped backend contributes no models, so a pipe pinning a
    # bare handle served only by that backend reports it as not found (see docs/features/validation-dry-run.md).
    # This is the same boot `pipelex-agent run --dry-run` uses, so the two CLIs agree either way.
    make_pipelex_for_cli(
        context=ErrorContext.VALIDATION_BEFORE_PIPE_RUN,
        library_dirs=library_dir,
        needs_inference=not dry_run,
        boot_orchestrator=orchestrator,
        needs_model_specs=True,
    )

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
            tag(name=EventProperty.CLI_COMMAND, value=telemetry_command_label)
            asyncio.run(
                _execute_run(
                    pipe_code=pipe_code,
                    bundle_path=bundle_path,
                    inputs=inputs,
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
                    dynamic_output_concept_ref=dynamic_output_concept_ref,
                    save_csv=save_csv,
                )
            )

    except PipeOperatorModelChoiceError as exc:
        handle_model_choice_error(exc, context=ErrorContext.PIPE_RUN)

    except PipeOperatorModelAvailabilityError as exc:
        handle_model_availability_error(exc, context=ErrorContext.PIPE_RUN)

    except typer.Exit:
        raise

    except PipelexError as exc:
        console = get_console()
        print_traceback_if_requested(console=console)
        console.print("\n[bold red]Failed to execute pipeline[/bold red]\n")
        console.print(f"  {exc.message}\n")
        raise typer.Exit(1) from exc

    except Exception as exc:
        # CLI command root: any unexpected failure is reported to the user and exits non-zero via typer.Exit.
        log.error(f"Error executing pipeline: {exc}")
        console = get_console()
        console.print("\n[bold red]Failed to execute pipeline[/bold red]\n")
        console.print_exception(show_locals=True)
        raise typer.Exit(1) from exc

    finally:
        Pipelex.teardown_if_needed()
