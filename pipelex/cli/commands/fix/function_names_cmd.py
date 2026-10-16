from pathlib import Path
from typing import Annotated

import typer

from pipelex.migration.exceptions import FunctionNamesMigrationError
from pipelex.migration.function_names import migrate_function_names_in_directory
from pipelex.migration.function_names_render import format_function_names_markdown


def fix_function_names_cmd(
    path: Annotated[
        str,
        typer.Argument(help="The folder of the method, whose tree holds its bundles and its Python"),
    ],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would change without writing any file"),
    ] = False,
) -> None:
    """Rewrite every flat PipeFunc function_name of a method as its import path from the method's folder.

    A PipeFunc names its function by import path, such as 'funcs.totals.compute_totals' for the function
    compute_totals of funcs/totals.py. This finds the @pipe_func function each flat name registered, writes its
    import path, and drops the registration name of every @pipe_func(name=...) marker. Nothing is imported, and
    Pipelex does not boot. A name it cannot resolve is left as it is and reported; the command then exits 1.

    Examples:
        pipelex fix function-names my_method/
        pipelex fix function-names my_method/ --dry-run
    """
    try:
        migration = migrate_function_names_in_directory(directory=Path(path), is_dry_run=dry_run)
    except FunctionNamesMigrationError as exc:
        typer.secho(f"Failed to migrate the function names: {exc.message}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc
    typer.echo(format_function_names_markdown(migration=migration, directory=path, is_dry_run=dry_run))
    if not migration.is_complete:
        raise typer.Exit(1)
