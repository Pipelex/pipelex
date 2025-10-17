import asyncio
import time
from typing import Annotated

import typer

from pipelex import pretty_print
from pipelex.builder.builder import PipelexBundleSpec
from pipelex.builder.builder_loop import BuilderLoop
from pipelex.builder.runner_code import generate_runner_code
from pipelex.hub import get_report_delegate, get_required_pipe
from pipelex.language.plx_factory import PlxFactory
from pipelex.pipelex import Pipelex
from pipelex.pipeline.execute import execute_pipeline
from pipelex.tools.misc.file_utils import ensure_directory_for_file_path, save_text_to_path
from pipelex.tools.misc.json_utils import save_as_json_to_path

build_app = typer.Typer(help="Build working pipelines from natural language requirements", no_args_is_help=True)

"""
Today's example:
pipelex build pipe "Imagine a cute animal mascot for a startup based on its elevator pitch"
pipelex build pipe "Given an expense report, apply company rules"
pipelex build pipe "Take a CV in a PDF file, a Job offer text, and analyze if they match"

pipelex build partial "Given an expense report, apply company rules" -o results/generated.json
pipelex build flow "Given an expense report, apply company rules" -o results/flow.json

Other ideas:
pipelex build pipe "Take a photo as input, and render the opposite of the photo, don't structure anything, use only text content, be super concise"
pipelex build pipe "Take a photo as input, and render the opposite of the photo"
pipelex build pipe "Given an RDFP PDF, build a compliance matrix"
pipelex build pipe "Given an theme, write a Haiku"
"""


@build_app.command("pipe", help="Build a Pipelex bundle with one validation/fix loop correcting deterministic issues")
def build_pipe_cmd(
    brief: Annotated[
        str,
        typer.Argument(help="Brief description of what the pipeline should do"),
    ],
    output_path: Annotated[
        str,
        typer.Option("--output", "-o", help="Path to save the generated PLX file"),
    ] = "./results/generated_pipeline.plx",
    no_output: Annotated[
        bool,
        typer.Option("--no-output", help="Skip saving the pipeline to file"),
    ] = False,
) -> None:
    Pipelex.make()
    typer.echo("=" * 70)
    typer.secho("🔥 Starting pipe builder... 🚀", fg=typer.colors.GREEN)
    typer.echo("")

    async def run_pipeline():
        if no_output:
            typer.secho("\n⚠️  Pipeline will not be saved to file (--no-output specified)", fg=typer.colors.YELLOW)
        elif not output_path:
            typer.secho("\n🛑  Cannot save a pipeline to an empty file name", fg=typer.colors.RED)
            raise typer.Exit(1)
        else:
            ensure_directory_for_file_path(file_path=output_path)

        builder_loop = BuilderLoop()
        # Save to file unless explicitly disabled with --no-output
        if no_output:
            typer.secho("\n⚠️  Pipeline not saved to file (--no-output specified)", fg=typer.colors.YELLOW)
            return

        pipelex_bundle_spec = await builder_loop.build_and_fix(pipe_code="pipe_builder", input_memory={"brief": brief})
        plx_content = PlxFactory.make_plx_content(blueprint=pipelex_bundle_spec.to_blueprint())
        save_text_to_path(text=plx_content, path=output_path)
        typer.secho(f"\n✅ Pipeline saved to: {output_path}", fg=typer.colors.GREEN)

    start_time = time.time()
    asyncio.run(run_pipeline())
    end_time = time.time()
    typer.secho(f"\n✅ Pipeline built in {end_time - start_time:.2f} seconds", fg=typer.colors.GREEN)

    get_report_delegate().generate_report()


@build_app.command("runner", help="Build the Python code to run a pipe using its pipe code, including the necessary inputs")
def prepare_runner_cmd(
    pipe_code: Annotated[str, typer.Argument(help="The pipe code to run")],
    output_path: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Path to save the generated Python file"),
    ] = None,
) -> None:
    """Prepare a Python runner file for a pipe.

    The generated file will include:
    - All necessary imports
    - Example input values based on the pipe's input types

    Native concept types (Text, Image, PDF, etc.) will be automatically handled.
    Custom concept types will have their structure recursively generated.
    """
    # Initialize Pipelex
    Pipelex.make()

    # Get the pipe
    try:
        pipe = get_required_pipe(pipe_code=pipe_code)
    except Exception as e:
        typer.secho(f"❌ Error: Could not find pipe '{pipe_code}': {e}", fg=typer.colors.RED)
        raise typer.Exit(1) from e

    # Generate the code
    try:
        runner_code = generate_runner_code(pipe)
    except Exception as e:
        typer.secho(f"❌ Error generating runner code: {e}", fg=typer.colors.RED)
        raise typer.Exit(1) from e

    # Determine output path
    if not output_path:
        output_path = f"run_{pipe_code}.py"

    # Save the file
    try:
        ensure_directory_for_file_path(file_path=output_path)
        save_text_to_path(text=runner_code, path=output_path)
        typer.secho(f"✅ Generated runner file: {output_path}", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"❌ Error saving file: {e}", fg=typer.colors.RED)
        raise typer.Exit(1) from e


@build_app.command("one-shot-pipe", help="Developer utility for contributors: deliver pipeline in one shot, without validation loop")
def build_one_shot_cmd(
    brief: Annotated[
        str,
        typer.Argument(help="Brief description of what the pipeline should do"),
    ],
    output_path: Annotated[
        str,
        typer.Option("--output", "-o", help="Path to save the generated PLX file"),
    ] = "./results/generated_pipeline.plx",
    no_output: Annotated[
        bool,
        typer.Option("--no-output", help="Skip saving the pipeline to file"),
    ] = False,
) -> None:
    Pipelex.make()
    typer.echo("=" * 70)
    typer.secho("🔥 Starting pipe builder... 🚀", fg=typer.colors.GREEN)
    typer.echo("")

    async def run_pipeline():
        if no_output:
            typer.secho("\n⚠️  Pipeline will not be saved to file (--no-output specified)", fg=typer.colors.YELLOW)
        elif not output_path:
            typer.secho("\n🛑  Cannot save a pipeline to an empty file name", fg=typer.colors.RED)
            raise typer.Exit(1)
        else:
            ensure_directory_for_file_path(file_path=output_path)

        pipe_output = await execute_pipeline(
            pipe_code="pipe_builder",
            input_memory={"brief": brief},
        )
        pretty_print(pipe_output, title="Pipe Output")

        # Save to file unless explicitly disabled with --no-output
        if no_output:
            typer.secho("\n⚠️  Pipeline not saved to file (--no-output specified)", fg=typer.colors.YELLOW)
            return

        pipelex_bundle_spec = pipe_output.working_memory.get_stuff_as(name="pipelex_bundle_spec", content_type=PipelexBundleSpec)
        plx_content = PlxFactory.make_plx_content(blueprint=pipelex_bundle_spec.to_blueprint())
        save_text_to_path(text=plx_content, path=output_path)
        typer.secho(f"\n✅ Pipeline saved to: {output_path}", fg=typer.colors.GREEN)

    start_time = time.time()
    asyncio.run(run_pipeline())
    end_time = time.time()
    typer.secho(f"\n✅ Pipeline built in {end_time - start_time:.2f} seconds", fg=typer.colors.GREEN)

    get_report_delegate().generate_report()


@build_app.command(
    "partial-pipe", help="Developer utility for contributors: deliver a partial pipeline specification (not an actual bundle) and save it as JSON"
)
def build_partial_cmd(
    brief: Annotated[
        str,
        typer.Argument(help="Brief description of what the pipeline should do"),
    ],
    output_path: Annotated[
        str,
        typer.Option("--output", "-o", help="Path to save the generated PLX file"),
    ] = "./results/generated_pipeline.plx",
    no_output: Annotated[
        bool,
        typer.Option("--no-output", help="Skip saving the pipeline to file"),
    ] = False,
) -> None:
    Pipelex.make()
    typer.echo("=" * 70)
    typer.secho("🔥 Starting pipe builder... 🚀", fg=typer.colors.GREEN)
    typer.echo("")

    async def run_pipeline():
        if no_output:
            typer.secho("\n⚠️  Pipeline will not be saved to file (--no-output specified)", fg=typer.colors.YELLOW)
        elif not output_path:
            typer.secho("\n🛑  Cannot save a pipeline to an empty file name", fg=typer.colors.RED)
            raise typer.Exit(1)
        else:
            ensure_directory_for_file_path(file_path=output_path)

        pipe_output = await execute_pipeline(
            pipe_code="pipe_builder",
            input_memory={"brief": brief},
        )
        # Save to file unless explicitly disabled with --no-output
        if no_output:
            typer.secho("\n⚠️  Pipeline not saved to file (--no-output specified)", fg=typer.colors.YELLOW)
            return
        json_output = pipe_output.main_stuff.content.smart_dump()
        save_as_json_to_path(object_to_save=json_output, path=output_path)
        typer.secho(f"\n✅ Pipeline saved to: {output_path}", fg=typer.colors.GREEN)

    start_time = time.time()
    asyncio.run(run_pipeline())
    end_time = time.time()
    typer.secho(f"\n✅ Pipeline built in {end_time - start_time:.2f} seconds", fg=typer.colors.GREEN)

    get_report_delegate().generate_report()
