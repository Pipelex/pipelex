"""CLI command `pipelex build structures`: alias of `pipelex codegen types --target python-structures`.

The legacy per-file generator (one always-qualified class file per concept) was deleted when the
codegen engine landed (D9): this command now delegates verbatim to the engine, which emits a single
stamped `structures.py` (bare-when-unique class names, declared imprecision, `codegen.lock` beside
it). See the codegen spec -> "CLI: codegen".
"""

from pathlib import Path
from typing import Annotated

import typer

from pipelex.cli.commands.codegen.types_cmd import codegen_types_cmd
from pipelex.codegen.emitters.target import CodegenTarget

SUB_COMMAND_STRUCTURES = "structures"


def build_structures_command(
    target: Annotated[
        str,
        typer.Argument(help="Directory of .mthds bundles to resolve, or a .mthds file (its directory is used)"),
    ],
    output_dir: Annotated[
        str | None,
        typer.Option("--output-dir", "-o", help="Output directory for the generated module (default: structures/ in the target's directory)"),
    ] = None,
    library_dir: Annotated[
        list[str] | None,
        typer.Option(
            "--library-dir",
            "-L",
            help="Directory to search for pipe definitions (.mthds files). Can be specified multiple times.",
        ),
    ] = None,
) -> None:
    """Generate Python structure classes from concept definitions in .mthds files.

    Alias of `pipelex codegen types --target python-structures`: emits a single stamped
    `structures.py` plus its `codegen.lock`.

    Examples:
        pipelex build structures ./my_pipes/
        pipelex build structures my_bundle.mthds
        pipelex build structures my_bundle.mthds -o ./generated/
        pipelex build structures my_bundle.mthds -L ./shared_pipes/
    """
    target_path = Path(target)
    if not target_path.exists():
        typer.secho(f"Cannot resolve — target does not exist: {target_path}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    closure_dir = target_path.parent if target_path.is_file() else target_path

    codegen_types_cmd(
        target=CodegenTarget.PYTHON_STRUCTURES,
        paths=[closure_dir],
        output_dir=output_dir or str(closure_dir / "structures"),
        library_dir=[Path(lib_dir) for lib_dir in library_dir] if library_dir else None,
    )
