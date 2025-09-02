from __future__ import annotations

import asyncio
from typing import Annotated, Optional

import typer

from pipelex.create.build_blueprint import do_build_blueprint
from pipelex.pipelex import Pipelex

build_app = typer.Typer(help="Build artifacts like pipeline blueprints", no_args_is_help=True)


@build_app.command("blueprint")
def build_blueprint_cmd(
    brief: Annotated[
        str,
        typer.Argument(help="Brief description of what the pipeline should do"),
    ],
    output_path: Annotated[
        Optional[str],
        typer.Option("--output", "-o", help="Path to save the generated PLX blueprint (optional)"),
    ] = None,
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

    asyncio.run(
        do_build_blueprint(
            brief=brief,
            output_path=output_path,
        )
    )
