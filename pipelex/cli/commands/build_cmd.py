import asyncio
import time
from typing import Annotated, Optional

import typer

from pipelex import pretty_print
from pipelex.core.interpreter import PipelexInterpreter
from pipelex.hub import get_report_delegate
from pipelex.libraries.pipelines.builder.builder import PipelexBundleBlueprint
from pipelex.pipelex import Pipelex
from pipelex.pipeline.execute import execute_pipeline

build_app = typer.Typer(help="Build artifacts like pipelines", no_args_is_help=True)

"""
Exmaples:
pipelex build pipe "Take a photo as input, and render the opposite of the photo" -o ./built.plx
pipelex build pipe "Given a invoice pdf, extract employee and articles" -o ./built.plx
pipelex build pipe "Given an RDFP PDF, build a compliance matrix" -o ./built.plx
"""


@build_app.command("pipe")
def build_pipe_cmd(
    brief: Annotated[
        str,
        typer.Argument(help="Brief description of what the pipeline should do"),
    ],
    output_path: Annotated[
        Optional[str],
        typer.Option("--output", "-o", help="Path to save the generated PLX file (use --output='' to skip saving)"),
    ] = "./generated_pipeline.plx",
) -> None:
    Pipelex.make(relative_config_folder_path="pipelex/libraries", from_file=False)

    typer.echo("=" * 70)
    typer.echo(typer.style("🔥 Starting pipe builder... 🚀", fg=typer.colors.GREEN))
    typer.echo("")

    async def run_pipeline():
        pipe_output = await execute_pipeline(
            pipe_code="pipe_builder",
            input_memory={"brief": brief},
        )
        pretty_print(pipe_output, title="Pipe Output")
        blueprint = pipe_output.working_memory.get_stuff_as(name="pipelex_bundle_blueprint", content_type=PipelexBundleBlueprint)
        plx_content = PipelexInterpreter.make_plx_content(blueprint=blueprint.to_core_blueprint())

        # Save to file unless explicitly disabled with empty string
        if output_path and output_path != "":
            with open(output_path, "w") as f:
                f.write(plx_content)
            typer.echo(typer.style(f"\n✅ Pipeline saved to: {output_path}", fg=typer.colors.GREEN))
        elif output_path == "":
            typer.echo(typer.style("\n⚠️  Pipeline not saved to file (--output='' specified)", fg=typer.colors.YELLOW))

    start_time = time.time()
    asyncio.run(run_pipeline())
    end_time = time.time()
    typer.echo(typer.style(f"\n✅ Pipeline built in {end_time - start_time:.2f} seconds", fg=typer.colors.GREEN))

    get_report_delegate().generate_report()
