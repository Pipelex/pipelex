from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from pipelex.cli.commands.bundle_path_resolver import resolve_bundle_target
from pipelex.cli.commands.validate._validate_core import COMMAND, execute_validate
from pipelex.cli.error_handlers import handle_validate_bundle_error
from pipelex.pipeline.exceptions import ValidateBundleError

_NOT_A_BUNDLE_HINT = (
    "  To validate a pipe by code, use: pipelex validate pipe <code>\n"
    "  To validate a bundle, pass a .mthds file or directory: pipelex validate bundle <path>"
)


def validate_bundle_cmd(
    path: Annotated[
        str,
        typer.Argument(help="Path to a .mthds bundle file, or a method's folder, whose every bundle is judged"),
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
    """Validate a bundle file (.mthds) or a method's folder.

    A folder is judged whole, every bundle of its method tree, as the MTHDS protocol's validation judges a method: it
    needs no pipe to start at.

    Examples:
        pipelex validate bundle my_bundle.mthds
        pipelex validate bundle my_method/
        pipelex validate bundle my_bundle.mthds --allow-signatures
    """
    try:
        target = resolve_bundle_target(
            path,
            library_dir=library_dir,
            command=COMMAND,
            not_a_bundle_hint=_NOT_A_BUNDLE_HINT,
        )
    except ValidateBundleError as exc:
        # A folder whose tree is refused is the invalid verdict, naming the folder.
        handle_validate_bundle_error(
            exc,
            bundle_path=Path(path).expanduser(),
            library_dirs=[Path(one_dir).expanduser() for one_dir in library_dir] if library_dir else None,
            allow_signatures=allow_signatures,
        )

    execute_validate(
        pipe_code=None,
        bundle_path=target.bundle_path,
        method_dir=target.method_dir,
        library_dirs=target.library_dirs,
        telemetry_command_label=f"{COMMAND} bundle",
        allow_signatures=allow_signatures,
        orchestrator=orchestrator,
        tree_listing=target.tree_listing,
    )
