from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from pipelex.cli.commands.bundle_path_resolver import resolve_bundle_target
from pipelex.cli.commands.validate._validate_core import COMMAND, execute_validate

_NOT_A_BUNDLE_HINT = (
    "  To validate a pipe by code, use: pipelex validate pipe <code>\n"
    "  To validate a bundle, pass a .mthds file or directory: pipelex validate bundle <path>"
)


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
    orchestrator: Annotated[
        str | None,
        typer.Option(
            "--orchestrator",
            help="Boot this process under the named orchestrator plugin (e.g. 'temporal'). The validation sweep "
            "stays in-process either way; use it to verify validation does not dispatch to an orchestrator runtime.",
        ),
    ] = None,
) -> None:
    """Validate a bundle file (.mthds) or pipeline directory.

    Examples:
        pipelex validate bundle my_bundle.mthds
        pipelex validate bundle pipeline_01/
        pipelex validate bundle my_bundle.mthds --allow-signatures
    """
    bundle_path, library_dir = resolve_bundle_target(
        path,
        library_dir=library_dir,
        command=COMMAND,
        not_a_bundle_hint=_NOT_A_BUNDLE_HINT,
    )
    library_dirs_paths = [Path(lib_dir) for lib_dir in library_dir] if library_dir else None

    execute_validate(
        pipe_code=None,
        bundle_path=Path(bundle_path),
        library_dirs=library_dirs_paths,
        telemetry_command_label=f"{COMMAND} bundle",
        allow_signatures=allow_signatures,
        orchestrator=orchestrator,
    )
