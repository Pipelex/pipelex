"""Agent CLI fix function-names command."""

from pathlib import Path
from typing import Annotated, Any

import typer

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat, agent_error, agent_success_formatted, set_agent_cli_error_format
from pipelex.migration.exceptions import FunctionNamesMigrationError
from pipelex.migration.function_names import FunctionNamesMigration, migrate_function_names_in_directory
from pipelex.migration.function_names_render import format_function_names_markdown


def _payload(*, migration: FunctionNamesMigration, directory: Path, is_dry_run: bool) -> dict[str, Any]:
    return {
        "success": True,
        "directory": str(directory.resolve()),
        "is_dry_run": is_dry_run,
        "is_complete": migration.is_complete,
        "changed_files": sorted(migration.changed_files),
        **migration.model_dump(mode="json", include={"rewrites", "marker_removals", "unresolved"}),
    }


def fix_function_names_cmd(
    path: Annotated[
        str,
        typer.Argument(help="The folder of the method, whose tree holds its bundles and its Python"),
    ],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Report what would change without writing any file"),
    ] = False,
    output_format: Annotated[
        CliOutputFormat,
        typer.Option("--format", help="Success output format: markdown (default) or json (structured)"),
    ] = CliOutputFormat.MARKDOWN,
    error_format: Annotated[
        CliOutputFormat | None,
        typer.Option("--error-format", help="Error output format (defaults to --format value): markdown or json"),
    ] = None,
) -> None:
    """Rewrite every flat PipeFunc function_name of a method as its import path; branch on `is_complete`."""
    set_agent_cli_error_format(error_format or output_format)
    directory = Path(path)
    try:
        migration = migrate_function_names_in_directory(directory=directory, is_dry_run=dry_run)
    except FunctionNamesMigrationError as exc:
        agent_error(exc.message, error_type=type(exc).__name__, cause=exc, exit_code=2)
    agent_success_formatted(
        _payload(migration=migration, directory=directory, is_dry_run=dry_run),
        markdown_renderer=lambda _payload_dict: format_function_names_markdown(migration=migration, directory=path, is_dry_run=dry_run),
        output_format=output_format,
    )
    if not migration.is_complete:
        raise typer.Exit(1)
