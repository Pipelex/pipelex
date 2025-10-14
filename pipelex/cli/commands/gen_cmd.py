"""Commands for generating Python runner files from pipe definitions."""

import subprocess
from typing import Annotated

import typer

from pipelex.hub import get_required_pipe
from pipelex.pipelex import Pipelex
from pipelex.tools.codegen.runner_generator import generate_runner_code
from pipelex.tools.misc.file_utils import ensure_directory_for_file_path, save_text_to_path

gen_app = typer.Typer(help="Generate Python runner files from pipe definitions", no_args_is_help=True)


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


@gen_app.command("runner")
def generate_runner_cmd(
    pipe_code: Annotated[str, typer.Argument(help="The pipe code to generate a runner for")],
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
    """Generate a Python runner file for a pipe.

    The generated file will include:
    - All necessary imports
    - Example input values based on the pipe's input types
    - A function to run the pipeline
    - Code to execute the pipeline

    Native concept types (Text, Image, PDF, etc.) will be automatically handled.
    Custom concept types will include TODO comments for filling in required fields.
    """
    do_generate_runner(pipe_code=pipe_code, output_path=output, execute=execute, lint=lint)
