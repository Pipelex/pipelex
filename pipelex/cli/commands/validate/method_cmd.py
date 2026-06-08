from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from pipelex.cli.commands.validate._validate_core import COMMAND, execute_validate
from pipelex.cli.method_resolver import resolve_method_target


def validate_method_cmd(
    name: Annotated[
        str,
        typer.Argument(help="Name of the installed method to validate"),
    ],
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code to validate (overrides method's main_pipe)"),
    ] = None,
    library_dir: Annotated[
        list[str] | None,
        typer.Option(
            "--library-dir",
            "-L",
            help="Directory to search for pipe definitions (.mthds files). Can be specified multiple times.",
        ),
    ] = None,
    temporal: Annotated[
        bool | None,
        typer.Option(
            "--temporal/--no-temporal",
            help="Override config temporal.is_enabled for the boot. The sweep stays in-process either way; "
            "use it to verify validation does not dispatch to Temporal under a Temporal-enabled hub.",
        ),
    ] = None,
) -> None:
    """Validate an installed method by name.

    Resolves the method from ~/.mthds/methods/ or .mthds/methods/,
    determines the pipe to validate, and runs validation.

    Examples:
        pipelex validate method my-method
        pipelex validate method my-method --pipe custom_pipe
    """
    pipe_code, method_library_dirs, _ = resolve_method_target(
        method_name=name,
        pipe_override=pipe,
        library_dirs=library_dir,
    )

    library_dirs_paths: list[Path] = [Path(lib_dir) for lib_dir in method_library_dirs]
    if library_dir:
        library_dirs_paths.extend(Path(lib_dir) for lib_dir in library_dir)

    execute_validate(
        pipe_code=pipe_code,
        bundle_path=None,
        library_dirs=library_dirs_paths,
        telemetry_command_label=f"{COMMAND} method",
        temporal=temporal,
    )
