from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from pipelex.builder.conventions import DEFAULT_BUNDLE_FILE_NAME
from pipelex.cli.commands.validate._validate_core import COMMAND, execute_validate
from pipelex.core.interpreter.helpers import MTHDS_EXTENSION, is_pipelex_file


def validate_bundle_cmd(
    path: Annotated[
        str,
        typer.Argument(help="Path to a .mthds bundle file or a pipeline directory"),
    ],
    library_dir: Annotated[
        list[str] | None,
        typer.Option(
            "--library-dir",
            "-L",
            help="Directory to search for pipe definitions (.mthds files). Can be specified multiple times.",
        ),
    ] = None,
    allow_signatures: Annotated[
        bool,
        typer.Option(
            "--allow-signatures",
            help="Accept PipeSignature placeholders in the dependency graph (lenient mode).",
        ),
    ] = False,
    temporal: Annotated[
        bool | None,
        typer.Option(
            "--temporal/--no-temporal",
            help="Override config temporal.is_enabled for the boot. The sweep stays in-process either way; "
            "use it to verify validation does not dispatch to Temporal under a Temporal-enabled hub.",
        ),
    ] = None,
) -> None:
    """Validate a bundle file (.mthds) or pipeline directory.

    Examples:
        pipelex validate bundle my_bundle.mthds
        pipelex validate bundle pipeline_01/
        pipelex validate bundle my_bundle.mthds --allow-signatures
    """
    bundle_path: str | None = None
    target_path = Path(path)

    if target_path.is_dir():
        # Directory mode: auto-detect bundle file
        bundle_file = target_path / DEFAULT_BUNDLE_FILE_NAME
        if bundle_file.is_file():
            bundle_path = str(bundle_file)
        else:
            mthds_files = list(target_path.glob(f"*{MTHDS_EXTENSION}"))
            if len(mthds_files) == 0:
                typer.secho(
                    f"Failed to validate: no .mthds bundle file found in directory '{path}'",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(2)
            if len(mthds_files) > 1:
                mthds_names = ", ".join(mthds_file.name for mthds_file in mthds_files)
                typer.secho(
                    f"Failed to validate: multiple .mthds files found in '{path}' ({mthds_names}) "
                    f"and no '{DEFAULT_BUNDLE_FILE_NAME}'. "
                    f"Pass the .mthds file directly, e.g.: pipelex validate bundle {target_path / mthds_files[0].name}",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(2)
            bundle_path = str(mthds_files[0])

        # Add directory as library dir
        target_dir_str = str(target_path)
        if library_dir is None:
            library_dir = [target_dir_str]
        elif target_dir_str not in library_dir:
            library_dir = [target_dir_str, *library_dir]

        typer.echo(f"Auto-detected bundle: {bundle_path}")

    elif is_pipelex_file(target_path):
        bundle_path = path
    else:
        typer.secho(
            f"Failed to validate: '{path}' is not a .mthds file or directory.\n"
            f"  To validate a pipe by code, use: pipelex validate pipe <code>\n"
            f"  To validate a bundle, pass a .mthds file or directory: pipelex validate bundle <path>",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(2)

    library_dirs_paths = [Path(lib_dir) for lib_dir in library_dir] if library_dir else None

    execute_validate(
        pipe_code=None,
        bundle_path=Path(bundle_path) if bundle_path else None,
        library_dirs=library_dirs_paths,
        telemetry_command_label=f"{COMMAND} bundle",
        allow_signatures=allow_signatures,
        temporal=temporal,
    )
