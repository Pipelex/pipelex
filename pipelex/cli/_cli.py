import os
import shutil
from itertools import groupby
from typing import Annotated, Dict, Optional

import typer
from click import Command, Context
from rich import box
from rich.table import Table
from typer.core import TyperGroup
from typing_extensions import override

from pipelex import log, pretty_print
from pipelex.exceptions import PipelexCLIError, PipelexConfigError
from pipelex.hub import get_pipe_provider
from pipelex.libraries.library_config import LibraryConfig
from pipelex.pipelex import Pipelex
from pipelex.tools.config.manager import config_manager


class PipelexCLI(TyperGroup):
    @override
    def get_command(self, ctx: Context, cmd_name: str) -> Optional[Command]:
        cmd = super().get_command(ctx, cmd_name)
        if cmd is None:
            typer.echo(f"Unknown command: {cmd_name}")
            typer.echo(ctx.get_help())
            ctx.exit(1)
        return cmd


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    cls=PipelexCLI,
)


@app.command("init-libraries")
def init_libraries(
    overwrite: Annotated[bool, typer.Option("--overwrite", "-o", help="Warning: If set, existing files will be overwritten.")] = False,
) -> None:
    """Initialize pipelex libraries in the current directory.

    If overwrite is False, only create files that don't exist yet.
    If overwrite is True, all files will be overwritten even if they exist.
    """
    try:
        # TODO: Have a more proper print message regarding the overwrited files (e.g. list of files that were overwritten or not)
        LibraryConfig.export_libraries(overwrite=overwrite)
        if overwrite:
            typer.echo("Successfully initialized pipelex libraries (all files overwritten)")
        else:
            typer.echo("Successfully initialized pipelex libraries (only created non-existing files)")
    except Exception as e:
        raise PipelexCLIError(f"Failed to initialize libraries: {e}")


@app.command("init-config")
def init_config(
    reset: Annotated[bool, typer.Option("--reset", "-r", help="Warning: If set, existing files will be overwritten.")] = False,
) -> None:
    """Initialize pipelex configuration in the current directory."""
    pipelex_template_path = os.path.join(config_manager.pipelex_root_dir, "pipelex_template.toml")
    target_config_path = os.path.join(config_manager.local_root_dir, "pipelex.toml")

    if os.path.exists(target_config_path) and not reset:
        typer.echo("Warning: pipelex.toml already exists. Use --reset to force creation.")
        return

    try:
        shutil.copy2(pipelex_template_path, target_config_path)
        typer.echo(f"Created pipelex.toml at {target_config_path}")
    except Exception as e:
        raise PipelexCLIError(f"Failed to create pipelex.toml: {e}")


@app.command()
def validate() -> None:
    """Run the setup sequence."""
    LibraryConfig.export_libraries()
    Pipelex.make()
    log.info("Setup sequence passed OK, config and pipelines are validated.")


@app.command()
def show_config() -> None:
    """Show the pipelex configuration."""
    try:
        final_config = config_manager.load_config()
        pretty_print(final_config, title=f"Pipelex configuration for project: {config_manager.get_project_name()}")
    except Exception as e:
        raise PipelexConfigError(f"Error loading configuration: {e}")


@app.command()
def list_pipes() -> None:
    """List all available pipes."""
    Pipelex.make()

    def _format_concept_code(concept_code: Optional[str], current_domain: str) -> str:
        """Format concept code by removing domain prefix if it matches current domain."""
        if not concept_code:
            return ""
        parts = concept_code.split(".")
        if len(parts) == 2 and parts[0] == current_domain:
            return parts[1]
        return concept_code

    try:
        pipe_provider = get_pipe_provider()
        pipes = pipe_provider.get_pipes()

        # Sort pipes by domain and code
        ordered_items = sorted(pipes, key=lambda x: (x.domain or "", x.code or ""))

        # Create dictionary for return value
        pipes_dict: Dict[str, Dict[str, Dict[str, str]]] = {}

        # Group by domain and create separate tables
        for domain, domain_pipes in groupby(ordered_items, key=lambda x: x.domain):
            table = Table(
                title=f"[bold magenta]domain = {domain}[/]",
                show_header=True,
                show_lines=True,
                header_style="bold cyan",
                box=box.SQUARE_DOUBLE_HEAD,
                border_style="blue",
            )

            table.add_column("Code", style="green")
            table.add_column("Definition", style="white")
            table.add_column("Input", style="yellow")
            table.add_column("Output", style="yellow")

            pipes_dict[domain] = {}

            for pipe in domain_pipes:
                if pipe.code:
                    input_code = _format_concept_code(pipe.input_concept_code, domain)
                    output_code = _format_concept_code(pipe.output_concept_code, domain)

                    table.add_row(
                        pipe.code,
                        pipe.definition or "",
                        input_code,
                        output_code,
                    )

                    pipes_dict[domain][pipe.code] = {
                        "definition": pipe.definition or "",
                        "input": pipe.input_concept_code or "",
                        "output": pipe.output_concept_code or "",
                    }

            pretty_print(table)

    except Exception as e:
        raise PipelexCLIError(f"Failed to list pipes: {e}")


def main() -> None:
    """Entry point for the pipelex CLI."""
    app()
