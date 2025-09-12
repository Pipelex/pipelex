from __future__ import annotations

import asyncio
from typing import Annotated, Optional

import typer

from pipelex.core.interpreter import PipelexInterpreter
from pipelex.libraries.pipelines.builder.builder import PipelexBundleBlueprint
from pipelex.pipelex import Pipelex
from pipelex.pipeline.execute import execute_pipeline

build_app = typer.Typer(help="Build artifacts like pipelines", no_args_is_help=True)


@build_app.command("pipe")
def build_pipe_cmd(
    brief: Annotated[
        str,
        typer.Argument(help="Brief description of what the pipeline should do"),
    ],
    output_path: Annotated[
        Optional[str],
        typer.Option("--output", "-o", help="Path to save the generated PLX file (use --output='' to skip saving)"),
    ] = "./your_pipe.plx",
    relative_config_folder_path: Annotated[
        str,
        typer.Option(
            "--config-folder-path",
            "-c",
            help="Relative path to the config folder path (libraries)",
        ),
    ] = "./pipelex_libraries",
) -> None:
    Pipelex.make(relative_config_folder_path=relative_config_folder_path, from_file=False)

    typer.echo("=" * 70)
    typer.echo(typer.style("⚠️  CAUTION: Pipe Builder v1", fg=typer.colors.YELLOW, bold=True))
    typer.echo("=" * 70)
    typer.echo(typer.style("This is the v1 of the pipe builder. Please note:", fg=typer.colors.YELLOW))
    typer.echo(typer.style("• Processing can take up to 7 minutes to complete", fg=typer.colors.YELLOW))
    typer.echo(typer.style("• Requires multiple different LLMs from various providers", fg=typer.colors.YELLOW))
    typer.echo(typer.style("• May consume significant API credits across providers", fg=typer.colors.YELLOW))
    typer.echo("=" * 70)
    typer.echo(typer.style("Starting pipe builder...", fg=typer.colors.GREEN))
    typer.echo("")

    async def run_pipeline():
        pipe_output = await execute_pipeline(
            pipe_code="pipe_builder",
            input_memory={"brief": brief},
        )
        blueprint = pipe_output.working_memory.get_stuff_as(name="pipelex_bundle_blueprint", content_type=PipelexBundleBlueprint)
        plx_content = PipelexInterpreter.make_plx_content(blueprint=blueprint.to_core_blueprint())

        # Save to file unless explicitly disabled with empty string
        if output_path and output_path != "":
            with open(output_path, "w") as f:
                f.write(plx_content)
            typer.echo(typer.style(f"\n✅ Pipeline saved to: {output_path}", fg=typer.colors.GREEN))
        elif output_path == "":
            typer.echo(typer.style("\n⚠️  Pipeline not saved to file (--output='' specified)", fg=typer.colors.YELLOW))

    asyncio.run(run_pipeline())
