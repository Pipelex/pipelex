import asyncio
import time
from typing import Annotated

import typer

from pipelex import pretty_print
from pipelex.hub import get_report_delegate
from pipelex.language.plx_factory import PlxFactory
from pipelex.libraries.pipelines.builder.builder import PipelexBundleSpec
from pipelex.libraries.pipelines.builder.builder_loop import BuilderLoop
from pipelex.pipelex import Pipelex
from pipelex.pipeline.execute import execute_pipeline
from pipelex.tools.misc.file_utils import ensure_directory_for_file_path, save_text_to_path
from pipelex.tools.misc.json_utils import save_as_json_to_path

build_app = typer.Typer(help="Build artifacts like pipelines", no_args_is_help=True)

"""
Today's example:
pipelex build pipe "Given an expense report, apply company rules"
pipelex build partial "Given an expense report, apply company rules" -o results/generated.json

Other ideas:
pipelex build pipe "Take a photo as input, and render the opposite of the photo"
pipelex build pipe "Given an RDFP PDF, build a compliance matrix"
"""


@build_app.command("one-shot")
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
    Pipelex.make(relative_config_folder_path="../../../pipelex/libraries", from_file=True)
    typer.echo("=" * 70)
    typer.echo(typer.style("🔥 Starting pipe builder... 🚀", fg=typer.colors.GREEN))
    typer.echo("")

    async def run_pipeline():
        if no_output:
            typer.echo(typer.style("\n⚠️  Pipeline will not be saved to file (--no-output specified)", fg=typer.colors.YELLOW))
        elif not output_path:
            typer.echo(typer.style("\n🛑  Cannot save a pipeline to an empty file name", fg=typer.colors.RED))
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
            typer.echo(typer.style("\n⚠️  Pipeline not saved to file (--no-output specified)", fg=typer.colors.YELLOW))
            return

        pipelex_bundle_spec = pipe_output.working_memory.get_stuff_as(name="pipelex_bundle_spec", content_type=PipelexBundleSpec)
        plx_content = PlxFactory.make_plx_content(blueprint=pipelex_bundle_spec.to_blueprint())
        save_text_to_path(text=plx_content, path=output_path)
        typer.echo(typer.style(f"\n✅ Pipeline saved to: {output_path}", fg=typer.colors.GREEN))

    start_time = time.time()
    asyncio.run(run_pipeline())
    end_time = time.time()
    typer.echo(typer.style(f"\n✅ Pipeline built in {end_time - start_time:.2f} seconds", fg=typer.colors.GREEN))

    get_report_delegate().generate_report()


@build_app.command("pipe")
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
    Pipelex.make(relative_config_folder_path="../../../pipelex/libraries", from_file=True)
    typer.echo("=" * 70)
    typer.echo(typer.style("🔥 Starting pipe builder... 🚀", fg=typer.colors.GREEN))
    typer.echo("")

    async def run_pipeline():
        if no_output:
            typer.echo(typer.style("\n⚠️  Pipeline will not be saved to file (--no-output specified)", fg=typer.colors.YELLOW))
        elif not output_path:
            typer.echo(typer.style("\n🛑  Cannot save a pipeline to an empty file name", fg=typer.colors.RED))
            raise typer.Exit(1)
        else:
            ensure_directory_for_file_path(file_path=output_path)

        builder_loop = BuilderLoop()
        # Save to file unless explicitly disabled with --no-output
        if no_output:
            typer.echo(typer.style("\n⚠️  Pipeline not saved to file (--no-output specified)", fg=typer.colors.YELLOW))
            return

        pipelex_bundle_spec = await builder_loop.build_and_fix(pipe_code="pipe_builder", input_memory={"brief": brief})
        plx_content = PlxFactory.make_plx_content(blueprint=pipelex_bundle_spec.to_blueprint())
        save_text_to_path(text=plx_content, path=output_path)
        typer.echo(typer.style(f"\n✅ Pipeline saved to: {output_path}", fg=typer.colors.GREEN))

    start_time = time.time()
    asyncio.run(run_pipeline())
    end_time = time.time()
    typer.echo(typer.style(f"\n✅ Pipeline built in {end_time - start_time:.2f} seconds", fg=typer.colors.GREEN))

    get_report_delegate().generate_report()


@build_app.command("partial")
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
    Pipelex.make(relative_config_folder_path="../../../pipelex/libraries", from_file=True)
    typer.echo("=" * 70)
    typer.echo(typer.style("🔥 Starting pipe builder... 🚀", fg=typer.colors.GREEN))
    typer.echo("")

    async def run_pipeline():
        if no_output:
            typer.echo(typer.style("\n⚠️  Pipeline will not be saved to file (--no-output specified)", fg=typer.colors.YELLOW))
        elif not output_path:
            typer.echo(typer.style("\n🛑  Cannot save a pipeline to an empty file name", fg=typer.colors.RED))
            raise typer.Exit(1)
        else:
            ensure_directory_for_file_path(file_path=output_path)

        pipe_output = await execute_pipeline(
            pipe_code="pipe_builder",
            input_memory={"brief": brief},
        )
        # Save to file unless explicitly disabled with --no-output
        if no_output:
            typer.echo(typer.style("\n⚠️  Pipeline not saved to file (--no-output specified)", fg=typer.colors.YELLOW))
            return
        json_output = pipe_output.main_stuff.content.smart_dump()
        save_as_json_to_path(object_to_save=json_output, path=output_path)
        typer.echo(typer.style(f"\n✅ Pipeline saved to: {output_path}", fg=typer.colors.GREEN))

    start_time = time.time()
    asyncio.run(run_pipeline())
    end_time = time.time()
    typer.echo(typer.style(f"\n✅ Pipeline built in {end_time - start_time:.2f} seconds", fg=typer.colors.GREEN))

    get_report_delegate().generate_report()
