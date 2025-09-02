from __future__ import annotations

import asyncio
from typing import Annotated, Optional

import typer

from pipelex.create.build_blueprint import do_build_blueprint
from pipelex.create.draft_pipeline import do_draft_pipeline, do_draft_pipeline_text
from pipelex.exceptions import PipelexCLIError
from pipelex.pipelex import Pipelex
from pipelex.tools.misc.file_utils import load_text_from_path

# Typer group for build commands
build_app = typer.Typer(help="Build artifacts like pipeline blueprints", no_args_is_help=True)


@build_app.command("draft")
def build_draft_pipeline_cmd(
    pipeline_name: Annotated[
        str,
        typer.Argument(help="Name/code of the pipeline to generate"),
    ],
    domain: Annotated[
        str,
        typer.Option("--domain", "-d", help="Domain of the pipeline to generate"),
    ] = "wip_domain",
    requirements: Annotated[
        Optional[str],
        typer.Option("--requirements", "-r", help="Requirements text to generate the pipeline blueprint from"),
    ] = None,
    requirements_file: Annotated[
        Optional[str],
        typer.Option("--file", "-f", help="Path to a file containing the requirements text"),
    ] = None,
    output_path: Annotated[
        Optional[str],
        typer.Option("--output", "-o", help="Path to save the generated PLX blueprint (optional)"),
    ] = None,
    raw: Annotated[
        bool,
        typer.Option("--raw", help="Raw text draft"),
    ] = False,
    relative_config_folder_path: Annotated[
        str,
        typer.Option(
            "--config-folder-path",
            "-c",
            help="Relative path to the config folder path (libraries)",
        ),
    ] = "./pipelex_libraries",
) -> None:
    # Initialize Pipelex (loads libraries and pipes)
    Pipelex.make(relative_config_folder_path=relative_config_folder_path, from_file=False)

    # Get requirements text
    try:
        requirements_text: str
        if requirements_file:
            requirements_text = load_text_from_path(requirements_file)
        else:
            if not requirements:
                raise PipelexCLIError("You must provide requirements text via --requirements or a file via --file")
            requirements_text = requirements
    except Exception as exc:
        raise PipelexCLIError(f"Failed to load requirements: {exc}") from exc

    if raw:
        asyncio.run(
            do_draft_pipeline_text(
                domain=domain,
                pipeline_name=pipeline_name,
                requirements=requirements_text,
                output_path=output_path,
            )
        )
    else:
        asyncio.run(
            do_draft_pipeline(
                pipeline_name=pipeline_name,
                requirements=requirements_text,
                output_path=output_path,
            )
        )


@build_app.command("blueprint")
def build_blueprint_cmd(
    pipeline_name: Annotated[
        str,
        typer.Argument(help="Name/code of the pipeline to generate"),
    ],
    domain: Annotated[
        str,
        typer.Option("--domain", "-d", help="Domain of the pipeline to generate"),
    ] = "wip_domain",
    requirements: Annotated[
        Optional[str],
        typer.Option("--requirements", "-r", help="Requirements text to generate the pipeline blueprint from"),
    ] = None,
    requirements_file: Annotated[
        Optional[str],
        typer.Option("--file", "-f", help="Path to a file containing the requirements text"),
    ] = None,
    output_path: Annotated[
        Optional[str],
        typer.Option("--output", "-o", help="Path to save the generated PLX blueprint (optional)"),
    ] = None,
    validate: Annotated[
        bool,
        typer.Option("--validate", help="Dry-run the first generated pipe from the blueprint"),
    ] = False,
    relative_config_folder_path: Annotated[
        str,
        typer.Option(
            "--config-folder-path",
            "-c",
            help="Relative path to the config folder path (libraries)",
        ),
    ] = "./pipelex_libraries",
) -> None:
    # Initialize Pipelex (loads libraries and pipes)
    Pipelex.make(relative_config_folder_path=relative_config_folder_path, from_file=False)

    # Get requirements text
    try:
        requirements_text: str
        if requirements_file:
            requirements_text = load_text_from_path(requirements_file)
        else:
            if not requirements:
                raise PipelexCLIError("You must provide requirements text via --requirements or a file via --file")
            requirements_text = requirements
    except Exception as exc:
        raise PipelexCLIError(f"Failed to load requirements: {exc}") from exc

    asyncio.run(
        do_build_blueprint(
            domain=domain,
            pipeline_name=pipeline_name,
            requirements=requirements_text,
            output_path=output_path,
            validate=validate,
        )
    )
