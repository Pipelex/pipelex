from __future__ import annotations

import asyncio
import subprocess
from typing import Annotated

import typer

from pipelex import log, pretty_print_md
from pipelex.builder.builder import load_pipe_from_bundle
from pipelex.builder.builder_errors import PipelexBundleError
from pipelex.exceptions import PipeInputError
from pipelex.hub import get_required_pipe
from pipelex.pipelex import Pipelex
from pipelex.pipeline.execute import execute_pipeline
from pipelex.tools.codegen.runner_generator import generate_runner_code
from pipelex.tools.misc.file_utils import ensure_directory_for_file_path, get_incremental_file_path, save_text_to_path
from pipelex.tools.misc.json_utils import JsonTypeError, load_json_dict_from_path, save_as_json_to_path

run_app = typer.Typer(help="Run pipelines and generate runner files", no_args_is_help=True)


def do_generate_runner(pipe_code: str, output_path: str | None, execute: bool, lint: bool) -> None:
    """Generate a Python runner file for the given pipe."""
    # Initialize Pipelex
    Pipelex.make()

    # Get the pipe
    try:
        pipe = get_required_pipe(pipe_code=pipe_code)
    except Exception as e:
        typer.echo(typer.style(f"❌ Error: Could not find pipe '{pipe_code}': {e}", fg=typer.colors.RED))
        raise typer.Exit(1) from e

    # Generate the code
    try:
        runner_code = generate_runner_code(pipe)
    except Exception as e:
        typer.echo(typer.style(f"❌ Error generating runner code: {e}", fg=typer.colors.RED))
        raise typer.Exit(1) from e

    # Determine output path
    if not output_path:
        output_path = f"run_{pipe_code}.py"

    # Save the file
    try:
        ensure_directory_for_file_path(file_path=output_path)
        save_text_to_path(text=runner_code, path=output_path)
        typer.echo(typer.style(f"✅ Generated runner file: {output_path}", fg=typer.colors.GREEN))
    except Exception as e:
        typer.echo(typer.style(f"❌ Error saving file: {e}", fg=typer.colors.RED))
        raise typer.Exit(1) from e

    # Lint the file if requested
    if lint:
        typer.echo("\n🔍 Running linter...")
        result = subprocess.run(  # noqa: S603
            ["ruff", "check", output_path],  # noqa: S607
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            typer.echo(typer.style("✅ Linting passed", fg=typer.colors.GREEN))
        else:
            typer.echo(typer.style("⚠️  Linting found issues:", fg=typer.colors.YELLOW))
            typer.echo(result.stdout)
            typer.echo(result.stderr)

    # Execute the file if requested (with warning)
    if execute:
        typer.echo("\n⚠️  Note: Execution may fail if input values need to be filled in")
        typer.echo("🚀 Executing generated file...")
        result = subprocess.run(  # noqa: S603
            ["python", output_path],  # noqa: S607
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            typer.echo(typer.style("✅ Execution successful:", fg=typer.colors.GREEN))
            typer.echo(result.stdout)
        else:
            typer.echo(typer.style("❌ Execution failed:", fg=typer.colors.RED))
            typer.echo(result.stdout)
            typer.echo(result.stderr)


@run_app.command("prepare")
def prepare_runner_cmd(
    pipe_code: Annotated[str, typer.Argument(help="The pipe code to prepare a runner for")],
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Path to save the generated Python file"),
    ] = None,
    execute: Annotated[
        bool,
        typer.Option("--execute", "-e", help="Execute the generated file after creation"),
    ] = False,
    lint: Annotated[
        bool,
        typer.Option("--lint", "-l", help="Run linter on the generated file"),
    ] = False,
) -> None:
    """Prepare a Python runner file for a pipe.

    The generated file will include:
    - All necessary imports
    - Example input values based on the pipe's input types
    - A function to run the pipeline
    - Code to execute the pipeline

    Native concept types (Text, Image, PDF, etc.) will be automatically handled.
    Custom concept types will have their structure recursively generated.
    """
    do_generate_runner(pipe_code=pipe_code, output_path=output, execute=execute, lint=lint)


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
        typer.secho("Failed to run: must provide a pipe code, bundle file, or target", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    if provided_options > 1:
        typer.secho(
            "Failed to run: cannot use multiple options (--pipe, --bundle, or positional target) simultaneously",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    async def run_pipeline():
        # Initialize to satisfy linter (will be assigned before use)
        pipe_code: str = ""
        source_description: str = ""
        bundle_path: str | None = None

        # Determine source: bundle path or pipe code
        if bundle:
            bundle_path = bundle
        elif pipe:
            pipe_code = pipe
            source_description = f"pipe '{pipe_code}'"
        elif target:
            if target.endswith(".plx"):
                bundle_path = target
            else:
                pipe_code = target
                source_description = f"pipe '{pipe_code}'"
        else:
            # Should never reach here due to validation above
            typer.secho("Failed to run: no pipe or bundle specified", fg=typer.colors.RED, err=True)
            raise typer.Exit(1)

        # Load bundle if needed
        if bundle_path:
            try:
                pipe_code = await load_pipe_from_bundle(bundle_path)
                source_description = f"bundle '{bundle_path}' • main_pipe: '{pipe_code}'"
            except FileNotFoundError as exc:
                typer.secho(f"Failed to load bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from exc
            except PipelexBundleError as exc:
                typer.secho(f"Failed to load bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from exc
            except PipeInputError as exc:
                typer.secho(f"Failed to load bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from exc

        try:
            # Load inputs if provided
            input_memory = None
            if inputs:
                try:
                    input_memory = load_json_dict_from_path(inputs)
                    typer.echo(f"Loaded inputs from: {inputs}")
                except FileNotFoundError as file_not_found_exc:
                    typer.secho(f"Failed to load input file '{inputs}': file not found", fg=typer.colors.RED, err=True)
                    raise typer.Exit(1) from file_not_found_exc
                except JsonTypeError as json_type_error_exc:
                    typer.secho(f"Failed to parse input file '{inputs}': must be a valid JSON dictionary", fg=typer.colors.RED, err=True)
                    raise typer.Exit(1) from json_type_error_exc

            # Execute pipeline
            typer.secho(f"\n🚀 Executing {source_description}...\n", fg=typer.colors.GREEN, bold=True)

            pipe_output = await execute_pipeline(
                pipe_code=pipe_code,
                input_memory=input_memory,
            )

            # Pretty print main_stuff unless disabled
            if not no_pretty_print:
                typer.echo("")
                pretty_print_md(content=pipe_output.main_stuff.content.rendered_markdown(), title=f"Main output of '{pipe_code}'")
                typer.echo("")

            # Save working memory to JSON unless disabled
            if not no_output:
                output_path = output or get_incremental_file_path(
                    base_path="results",
                    base_name=f"run_{pipe_code}",
                    extension="json",
                )
                working_memory_dict = pipe_output.working_memory.model_dump()
                save_as_json_to_path(object_to_save=working_memory_dict, path=output_path)
                typer.echo(typer.style(f"✅ Working memory saved to: {output_path}", fg=typer.colors.GREEN))

            typer.echo(typer.style("✅ Pipeline execution completed successfully", fg=typer.colors.GREEN))

        except Exception as exc:
            log.error(f"Error executing pipeline: {exc}")
            typer.secho(f"Failed to execute pipeline: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc

    asyncio.run(run_pipeline())
