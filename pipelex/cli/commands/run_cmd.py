from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from pipelex import log, pretty_print
from pipelex.builder.builder_validation import dry_run_bundle_blueprint, extract_pipe_failures_from_dry_run_result_by_blueprint
from pipelex.core.interpreter import PipelexInterpreter
from pipelex.pipelex import Pipelex
from pipelex.pipeline.execute import execute_pipeline
from pipelex.tools.misc.json_utils import JsonTypeError, load_json_dict_from_path, save_as_json_to_path


async def _load_pipe_from_bundle(bundle_path: str) -> str:
    """Load a bundle file and extract its main_pipe.

    Args:
        bundle_path: Path to the .plx bundle file.

    Returns:
        The pipe_code from the bundle's main_pipe.

    Raises:
        typer.Exit: If file not found or no main_pipe declared.
    """
    bundle_path_obj = Path(bundle_path)
    if not bundle_path_obj.exists():
        typer.echo(typer.style(f"Error: Bundle file not found: {bundle_path}", fg=typer.colors.RED))
        raise typer.Exit(1)

    interpreter = PipelexInterpreter(file_path=bundle_path_obj)
    bundle_blueprint = interpreter.make_pipelex_bundle_blueprint()

    if not bundle_blueprint.main_pipe:
        typer.echo(typer.style(f"Error: Bundle '{bundle_path}' does not declare a main_pipe", fg=typer.colors.RED))
        raise typer.Exit(1)

    dry_run_result = await dry_run_bundle_blueprint(bundle_blueprint=bundle_blueprint)
    pipe_failures = extract_pipe_failures_from_dry_run_result_by_blueprint(bundle_blueprint=bundle_blueprint, dry_run_result=dry_run_result)
    if pipe_failures:
        typer.echo(typer.style(f"Error: Pipes failed during dry run: {pipe_failures}", fg=typer.colors.RED))
        raise typer.Exit(1)
    return bundle_blueprint.main_pipe


def run_cmd(
    target: Annotated[
        str | None,
        typer.Argument(help="Pipe code or bundle file path (auto-detected)"),
    ] = None,
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Explicitly specify pipe code to run"),
    ] = None,
    bundle: Annotated[
        str | None,
        typer.Option("--bundle", help="Bundle file path (.plx) - runs its main_pipe"),
    ] = None,
    inputs: Annotated[
        str | None,
        typer.Option("--inputs", "-i", help="Path to JSON file with input_memory"),
    ] = None,
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Path to save output JSON (default: {pipe_code}.json)"),
    ] = None,
    no_output: Annotated[
        bool,
        typer.Option("--no-output", help="Skip saving output to file"),
    ] = False,
    no_pretty_print: Annotated[
        bool,
        typer.Option("--no-pretty-print", help="Skip pretty printing the main_stuff"),
    ] = False,
) -> None:
    """Execute a pipeline by pipe code or bundle file.

    Examples:
        pipelex run my_pipe
        pipelex run --pipe my_pipe --inputs data.json
        pipelex run --bundle my_bundle.plx
        pipelex run my_bundle.plx --inputs data.json
        pipelex run my_pipe --output results.json --no-pretty-print
    """
    # Initialize Pipelex
    Pipelex.make()

    # Validate mutual exclusivity
    provided_options = sum([target is not None, pipe is not None, bundle is not None])
    if provided_options == 0:
        typer.echo(typer.style("Error: Must provide a pipe code, bundle file, or target", fg=typer.colors.RED))
        raise typer.Exit(1)
    if provided_options > 1:
        typer.echo(
            typer.style(
                "Error: Cannot use multiple options (--pipe, --bundle, or positional target) simultaneously",
                fg=typer.colors.RED,
            )
        )
        raise typer.Exit(1)

    async def run_pipeline():
        pipe_code: str
        source_description: str

        try:
            if bundle:
                # Explicit bundle option
                pipe_code = await _load_pipe_from_bundle(bundle)
                source_description = f"bundle '{bundle}' (main_pipe: {pipe_code})"
            elif pipe:
                # Explicit pipe option
                pipe_code = pipe
                source_description = f"pipe '{pipe_code}'"
            elif target:
                # Auto-detect: is it a .plx file or a pipe code?
                if target.endswith(".plx"):
                    pipe_code = await _load_pipe_from_bundle(target)
                    source_description = f"bundle '{target}' (main_pipe: {pipe_code})"
                else:
                    pipe_code = target
                    source_description = f"pipe '{pipe_code}'"
            else:
                # Should never reach here due to validation above
                typer.echo(typer.style("Error: No pipe or bundle specified", fg=typer.colors.RED))
                raise typer.Exit(1)

            # Load inputs if provided
            input_memory = None
            if inputs:
                try:
                    input_memory = load_json_dict_from_path(inputs)
                    typer.echo(f"Loaded inputs from: {inputs}")
                except FileNotFoundError as file_not_found_exc:
                    typer.echo(typer.style(f"Error: Input file not found: {inputs}", fg=typer.colors.RED))
                    raise typer.Exit(1) from file_not_found_exc
                except JsonTypeError as json_type_error_exc:
                    typer.echo(typer.style(f"Error: Input file is not a proper JSON dictionary: {inputs}", fg=typer.colors.RED))
                    raise typer.Exit(1) from json_type_error_exc

            # Execute pipeline
            typer.echo("=" * 70)
            typer.echo(typer.style(f"🚀 Executing {source_description}...", fg=typer.colors.GREEN))
            typer.echo("")

            pipe_output = await execute_pipeline(
                pipe_code=pipe_code,
                input_memory=input_memory,
            )

            # Pretty print main_stuff unless disabled
            if not no_pretty_print:
                typer.echo("")
                typer.echo("=" * 70)
                pretty_print(pipe_output.main_stuff, title="Pipeline Output")
                typer.echo("")

            # Save working memory to JSON unless disabled
            if not no_output:
                output_path = output or f"{pipe_code}.json"
                working_memory_dict = pipe_output.working_memory.model_dump()
                save_as_json_to_path(object_to_save=working_memory_dict, path=output_path)
                typer.echo(typer.style(f"✅ Working memory saved to: {output_path}", fg=typer.colors.GREEN))

            typer.echo(typer.style("✅ Pipeline execution completed successfully", fg=typer.colors.GREEN))

        except Exception as exc:
            log.error(f"Error executing pipeline: {exc}")
            typer.echo(typer.style(f"Error: {exc}", fg=typer.colors.RED))
            raise typer.Exit(1) from exc

    asyncio.run(run_pipeline())
