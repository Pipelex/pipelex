"""CLI command to locate a pipe definition, similar to 'which' for executables."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

if TYPE_CHECKING:
    from pathlib import Path

import typer
from posthog import tag

from pipelex import log
from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import ErrorContext
from pipelex.hub import (
    get_console,
    get_library_manager,
    get_optional_pipe,
    get_pipe_source,
    get_telemetry_manager,
    resolve_library_dirs,
    set_current_library,
)
from pipelex.pipelex import Pipelex
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventName, EventProperty
from pipelex.tools.misc.package_utils import get_package_version

COMMAND = "which"


def do_which_pipe(pipe_code: str, library_dirs: list[Path], source_label: str) -> bool:
    """Locate where a pipe is defined."""
    console = get_console()

    # Show search path
    console.print(f"\n[bold]Search path for '[cyan]{pipe_code}[/cyan]':[/bold]")
    if not library_dirs:
        console.print("  [dim](no directories configured)[/dim]")
    else:
        for dir_path in library_dirs:
            exists_marker = "[green]✓[/green]" if dir_path.exists() else "[red]✗[/red]"
            console.print(f"  {exists_marker} {dir_path} [dim]({source_label})[/dim]")

    console.print("")

    # Try to find the pipe
    pipe = get_optional_pipe(pipe_code=pipe_code)

    if pipe:
        console.print(f"[green]Found:[/green] [bold]{pipe_code}[/bold]")
        console.print(f"  Type: [cyan]{pipe.pipe_type}[/cyan]")
        console.print(f"  Domain: [cyan]{pipe.domain_code}[/cyan]")
        source_path = get_pipe_source(pipe_code=pipe_code)
        if source_path:
            console.print(f"  Source: [cyan]{source_path}[/cyan]")
        log.verbose(f"Pipe '{pipe_code}' resolved", title="which")
        console.print("")
        return True
    else:
        console.print(f"[red]Not found:[/red] [bold]{pipe_code}[/bold]")
        console.print("\n[dim]Tip: Check that the pipe code is correct and that the containing[/dim]")
        console.print("[dim]directory is in PIPELEXPATH or passed via --library-dir[/dim]")
        console.print("")
        return False


def which_cmd(
    pipe_code: Annotated[str, typer.Argument(help="Pipe code to locate (e.g., 'my_domain.my_pipe')")],
    library_dir: Annotated[
        list[str] | None,
        typer.Option("--library-dir", "-L", help="Directory to search for pipe definitions. Can be specified multiple times."),
    ] = None,
) -> None:
    """Locate where a pipe is defined, similar to 'which' for executables.

    Shows the search path (PIPELEXPATH + --library-dir) and whether the pipe was found.

    Examples:
        pipelex which hello_world
        pipelex which my_domain.my_pipe -L ./my_pipes
        PIPELEXPATH=/path/to/pipes pipelex which some_pipe
    """
    make_pipelex_for_cli(context=ErrorContext.VALIDATION_BEFORE_SHOW_PIPE)

    try:
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        set_current_library(library_id=library_id)

        # Resolve library directories using the standard 3-tier priority
        # CLI --library-dir args override instance defaults and PIPELEXPATH
        cli_dirs = library_dir or None
        effective_dirs, source_label = resolve_library_dirs(cli_dirs)

        if effective_dirs:
            library_manager.load_libraries(library_id=library_id, library_dirs=effective_dirs)

        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
            tag(name=EventProperty.CLI_COMMAND, value=COMMAND)

            found = do_which_pipe(pipe_code=pipe_code, library_dirs=effective_dirs, source_label=source_label)
            get_telemetry_manager().track_event(EventName.PIPE_SHOW)
            if not found:
                raise typer.Exit(1)
    finally:
        Pipelex.teardown_if_needed()
