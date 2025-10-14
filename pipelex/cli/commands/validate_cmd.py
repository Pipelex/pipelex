from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from pipelex import log
from pipelex.hub import get_pipeline_tracker, get_pipes, get_required_pipe
from pipelex.pipe_run.dry_run import dry_run_pipe, dry_run_pipes
from pipelex.pipelex import Pipelex


def do_validate_all_libraries_and_dry_run() -> None:
    """Validate libraries and dry-run all pipes."""
    pipelex_instance = Pipelex.make()
    pipelex_instance.validate_libraries()
    asyncio.run(dry_run_pipes(pipes=get_pipes(), raise_on_failure=True))
    log.info("Setup sequence passed OK, config and pipelines are validated.")


def do_dry_run_pipe(pipe_code: str) -> None:
    """Dry run a single pipe."""
    pipelex_instance = Pipelex.make()
    pipelex_instance.validate_libraries()

    asyncio.run(
        dry_run_pipe(
            get_required_pipe(pipe_code=pipe_code),
            raise_on_failure=True,
        ),
    )
    get_pipeline_tracker().output_flowchart()


# Typer group for validation commands
validate_app = typer.Typer(help="Validation and dry-run commands", no_args_is_help=True)


@validate_app.command("all")
def validate_all_cmd() -> None:
    do_validate_all_libraries_and_dry_run()


@validate_app.command("pipe")
def dry_run_pipe_cmd(
    pipe_code: Annotated[str, typer.Argument(help="The pipe code to dry run")],
) -> None:
    do_dry_run_pipe(pipe_code=pipe_code)
