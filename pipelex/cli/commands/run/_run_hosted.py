"""`pipelex run … --hosted`: run a method on the hosted Pipelex API, without booting the local runtime.

A hosted run needs no provider key and no inference configuration on this machine: it reads the `[run]` setting and
the scan settings from the configuration files, sends the method and its inputs through pipelex-sdk, and writes what
the hosted API returns where a local run writes its own outputs.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import typer
from mthds.protocol.exceptions import PipelineRequestError
from pipelex_sdk.errors import ApiResponseError
from rich.markup import escape

from pipelex.base_exceptions import PipelexError
from pipelex.cli.commands.run._run_core import load_run_inputs
from pipelex.cli.error_handlers import handle_validate_bundle_error, print_traceback_if_requested
from pipelex.hosted.client_factory import make_hosted_client
from pipelex.hosted.error_rendering import describe_hosted_error
from pipelex.hosted.exceptions import HostedRunError
from pipelex.hosted.execution import resolve_run_execution
from pipelex.hosted.hosted_run import HostedRunOutcome, HostedRunRequest, run_hosted
from pipelex.hosted.run_config import RunExecution
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle_translation import translate_to_validate_bundle_error
from pipelex.runtime_hub import get_console
from pipelex.tools.misc.file_utils import get_incremental_directory_path
from pipelex.tools.misc.json_utils import save_as_json_to_path
from pipelex.tools.misc.pretty import pretty_print, pretty_print_md

if TYPE_CHECKING:
    from pipelex_sdk.client import PipelexAPIClient
    from pipelex_sdk.crate_models import MthdsFileItem

_NATIVE_TEXT_CONCEPT_REF = "native.Text"
_MAIN_STUFF_NAME = "main_stuff"
_WORKING_MEMORY_FILENAME = "working_memory.json"
_GRAPHSPEC_FILENAME = "graphspec.json"


def _fail(*, message: str) -> typer.Exit:
    """Print a refusal and hand back the exit to raise."""
    typer.secho(f"Failed to run: {message}", fg=typer.colors.RED, err=True)
    return typer.Exit(1)


def resolve_cli_run_execution(*, hosted: bool | None, base_url: str | None) -> RunExecution:
    """Where this `pipelex run` executes: `--hosted`/`--local`, else `[run] execution`, else local.

    `--base-url` names the hosted API to call, so it is refused on a run that executes locally rather than ignored.

    Raises:
        typer.Exit: If the configuration cannot be read, or `--base-url` is given to a local run.
    """
    try:
        execution = resolve_run_execution(requested=RunExecution.from_hosted_flag(hosted=hosted))
    except PipelexError as exc:
        print_traceback_if_requested(console=get_console())
        raise _fail(message=exc.message) from exc
    if base_url is not None and not execution.is_hosted:
        msg = "--base-url names the hosted API a hosted run calls, and this run executes locally. Add --hosted, or drop --base-url."
        raise _fail(message=msg)
    return execution


def refuse_local_only_flags(
    *,
    dry_run: bool,
    mock_usage: bool,
    mock_inputs: bool,
    orchestrator: str | None,
    save_csv: str | None,
    costs: bool | None,
    graph_full_data: bool | None,
) -> None:
    """Refuse the flags that steer this machine's runtime, which a hosted run never boots.

    Raises:
        typer.Exit: If any of them is given, naming each and `--local`.
    """
    named: list[str] = []
    if dry_run:
        named.append("--dry-run")
    if mock_usage:
        named.append("--mock-usage")
    if mock_inputs:
        named.append("--mock-inputs")
    if orchestrator is not None:
        named.append("--orchestrator")
    if save_csv is not None:
        named.append("--save-csv")
    if costs is not None:
        named.append("--costs/--no-costs")
    if graph_full_data is not None:
        named.append("--graph-full-data/--graph-no-data")
    if named:
        msg = f"{', '.join(named)} only apply to a run on this machine, and this run executes on the hosted API. Pass --local to run it here."
        raise _fail(message=msg)


def _print_hosted_failure(*, error: PipelineRequestError | HostedRunError) -> None:
    """Print a hosted run's failure as `pipelex.hosted.error_rendering` reads it, the view the agent CLI's envelope carries.

    Its validation items name the file each fault is in when the hosted API was told it, and the run id is printed
    once the hosted API acknowledged the run, so a run that failed, outlived the wait or was lost on the way can be
    looked up.
    """
    view = describe_hosted_error(error=error)
    console = get_console()
    console.print("\n[bold red]Failed to run on the hosted API[/bold red]\n")
    console.print(f"  {escape(view.message)}\n")
    if view.validation_errors:
        for item in view.validation_errors:
            location = item.source or item.pipe_code or item.concept_code or item.domain_code
            prefix = f"{location}: " if location else ""
            console.print(f"  - {escape(prefix + item.message)}")
        console.print("")
    console.print(f"  [bold]Next step:[/bold] {escape(view.next_step)}\n")
    if view.pipeline_run_id is not None:
        console.print(f"  Run id: {escape(view.pipeline_run_id)}\n")
    if isinstance(error, ApiResponseError) and error.request_id:
        console.print(f"  Request id: {escape(error.request_id)}\n")


async def _start_and_wait(*, client: PipelexAPIClient, request: HostedRunRequest) -> HostedRunOutcome:
    async with client:
        return await run_hosted(client=client, request=request)


def _main_stuff_concept_ref(*, outcome: HostedRunOutcome) -> str | None:
    """The concept of the main output, read from the working memory, where a step that named its output keeps it
    under that name and points the `main_stuff` alias at it.
    """
    working_memory = outcome.results.working_memory
    if working_memory is None:
        return None
    main_stuff_name = working_memory.aliases.get(_MAIN_STUFF_NAME, _MAIN_STUFF_NAME)
    main_stuff = working_memory.root.get(main_stuff_name)
    return main_stuff.concept if main_stuff is not None else None


def _main_text(*, outcome: HostedRunOutcome) -> str | None:
    """The main output's text when it is native Text, which reads best rendered as Markdown."""
    main_stuff = outcome.results.main_stuff
    if _main_stuff_concept_ref(outcome=outcome) != _NATIVE_TEXT_CONCEPT_REF or not isinstance(main_stuff, dict):
        return None
    text = cast("dict[str, Any]", main_stuff).get("text")
    return text if isinstance(text, str) else None


def bundle_main_pipe_code(*, bundle_path: str, library_dirs: list[str] | None) -> str:
    """The `main_pipe` a bundle declares, read by parsing it here, as a local run reads it when `--pipe` is not given.

    Raises:
        typer.Exit: If the bundle cannot be read, does not parse, or declares no `main_pipe`.
    """
    try:
        mthds_content = Path(bundle_path).read_text(encoding="utf-8")
        with translate_to_validate_bundle_error():
            bundle_blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=mthds_content, mthds_source=bundle_path)
    except (OSError, UnicodeDecodeError) as exc:
        raise _fail(message=f"could not read the bundle '{bundle_path}': {exc}") from exc
    except ValidateBundleError as exc:
        library_dir_paths = [Path(one_dir) for one_dir in library_dirs] if library_dirs else None
        handle_validate_bundle_error(exc, bundle_path=Path(bundle_path), library_dirs=library_dir_paths)
    if not bundle_blueprint.main_pipe:
        msg = f"the bundle '{bundle_path}' declares no main_pipe. Name the pipe to run with --pipe, or declare a main_pipe in the bundle."
        raise _fail(message=msg)
    return bundle_blueprint.main_pipe


def execute_hosted_run(
    *,
    mthds_files: list[MthdsFileItem] | None = None,
    method_ref: str | None = None,
    method_id: str | None = None,
    pipe_code: str | None,
    inputs: str | None,
    dynamic_output_concept_ref: str | None,
    base_url: str | None,
    output_label: str,
    output_dir: str,
    save_working_memory: bool,
    working_memory_path: str | None,
    save_main_stuff: bool,
    no_pretty_print: bool,
    graph: bool | None,
) -> None:
    """Run on the hosted API, print the main output, and save the outputs as a local run saves them.

    The method is named by exactly one of `mthds_files`, `method_ref` and `method_id`. `inputs` is `--inputs` as the
    command resolved it: inline JSON or a JSON or TOML file, read as a local run reads it, and a local file it names
    at a document or image input is uploaded first.

    The outputs go to `<output_dir>/<output_label>_output_NN/`: `main_stuff.json` (and `main_stuff.md` for a text
    output), `working_memory.json`, and `graphspec.json` when the hosted API returned the run's graph, which
    `pipelex graph render` turns into a viewer.

    Raises:
        typer.Exit: If the base URL is not an origin, the inputs cannot be read, or the hosted run fails, after
            printing why and what next.
    """
    try:
        client = make_hosted_client(base_url=base_url)
    except PipelexError as exc:
        raise _fail(message=exc.message) from exc

    loaded_inputs = load_run_inputs(inputs=inputs)
    request = HostedRunRequest(
        mthds_files=mthds_files,
        method_ref=method_ref,
        method_id=method_id,
        pipe_code=pipe_code,
        inputs=loaded_inputs.pipeline_inputs,
        inputs_base_dir=loaded_inputs.inputs_base_dir,
        dynamic_output_concept_ref=dynamic_output_concept_ref,
    )

    console = get_console()
    console.print(f"Running on the hosted Pipelex API at [bold]{escape(client.base_url)}[/bold]")
    try:
        outcome = asyncio.run(_start_and_wait(client=client, request=request))
    except (PipelineRequestError, HostedRunError) as exc:
        print_traceback_if_requested(console=console)
        _print_hosted_failure(error=exc)
        raise typer.Exit(1) from exc
    except Exception as exc:
        # CLI command root: any unexpected failure is reported to the user and exits non-zero via typer.Exit.
        print_traceback_if_requested(console=console)
        console.print("\n[bold red]Failed to run on the hosted API[/bold red]\n")
        console.print(f"  {escape(f'{type(exc).__name__}: {exc}')}\n")
        raise typer.Exit(1) from exc

    results = outcome.results
    main_text = _main_text(outcome=outcome)
    if not no_pretty_print:
        title = f"Final output of {output_label}"
        if main_text is not None:
            pretty_print_md(main_text, title=title)
        else:
            pretty_print(json.dumps(results.main_stuff, indent=2, ensure_ascii=False), title=title)

    output_path: Path | None = None
    saved: list[str] = []
    if save_main_stuff or save_working_memory or (graph is not False and results.graph_spec is not None):
        output_path = get_incremental_directory_path(base_path=Path(output_dir), base_name=f"{output_label}_output")
        output_path.mkdir(parents=True, exist_ok=True)

    if output_path is not None and save_main_stuff:
        save_as_json_to_path(object_to_save=results.main_stuff, path=output_path / "main_stuff.json")
        saved.append("main_stuff.json")
        if main_text is not None:
            (output_path / "main_stuff.md").write_text(main_text, encoding="utf-8")
            saved.append("main_stuff.md")

    working_memory_output_path: Path | None = None
    if output_path is not None and save_working_memory and results.working_memory is not None:
        working_memory_output_path = Path(working_memory_path) if working_memory_path else output_path / _WORKING_MEMORY_FILENAME
        save_as_json_to_path(object_to_save=results.working_memory.model_dump(mode="json"), path=working_memory_output_path)
        saved.append(_WORKING_MEMORY_FILENAME if working_memory_output_path.parent == output_path else str(working_memory_output_path))

    graphspec_path: Path | None = None
    if output_path is not None and graph is not False and results.graph_spec is not None:
        graphspec_path = output_path / _GRAPHSPEC_FILENAME
        save_as_json_to_path(object_to_save=results.graph_spec, path=graphspec_path)
        saved.append(_GRAPHSPEC_FILENAME)

    console.print("\n[green]✓[/green] [bold]Hosted run completed successfully[/bold]")
    console.print(f"  Run id: {escape(results.pipeline_run_id)}")
    if outcome.uploads:
        console.print(f"  Uploaded {len(outcome.uploads)} local file(s) for the run")
    if output_path is not None and saved:
        console.print(f"  Output saved to [bold magenta]{escape(str(output_path))}[/bold magenta]:")
        for saved_name in saved:
            console.print(f"    [green]✓[/green] {escape(saved_name)}")
    if graphspec_path is not None:
        console.print(f"  View the run's graph with: pipelex graph render {escape(str(graphspec_path))}")
