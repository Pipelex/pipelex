"""CLI command to locate a pipe definition, similar to 'which' for executables."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from posthog import tag

from pipelex import log
from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import ErrorContext
from pipelex.hub import (
    get_console,
    get_library_manager,
    get_optional_pipe,
    get_telemetry_manager,
    set_current_library,
)
from pipelex.pipelex import Pipelex
from pipelex.system.environment import PIPELEXPATH_ENV_KEY, get_pipelexpath_dirs
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventName, EventProperty
from pipelex.tools.misc.package_utils import get_package_version

COMMAND = "which"


def do_which_pipe(pipe_code: str, library_dirs: list[Path]) -> None:
    """Locate where a pipe is defined."""
    console = get_console()

    # Show search path
    pipelexpath_dirs = get_pipelexpath_dirs()
    all_dirs = pipelexpath_dirs + library_dirs

    console.print(f"\n[bold]Search path for '[cyan]{pipe_code}[/cyan]':[/bold]")
    if not all_dirs:
        console.print("  [dim](no directories configured)[/dim]")
    else:
        for index_dir, dir_path in enumerate(all_dirs):
            source = f"({PIPELEXPATH_ENV_KEY})" if index_dir < len(pipelexpath_dirs) else "(--library-dir)"
            exists_marker = "[green]✓[/green]" if dir_path.exists() else "[red]✗[/red]"
            console.print(f"  {exists_marker} {dir_path} [dim]{source}[/dim]")

    console.print("")

    # Try to find the pipe
    pipe = get_optional_pipe(pipe_code=pipe_code)

    if pipe:
        console.print(f"[green]Found:[/green] [bold]{pipe_code}[/bold]")
        console.print(f"  Type: [cyan]{pipe.pipe_type}[/cyan]")
        console.print(f"  Domain: [cyan]{pipe.domain_code}[/cyan]")
        log.verbose(f"Pipe '{pipe_code}' resolved", title="which")
    else:
        console.print(f"[red]Not found:[/red] [bold]{pipe_code}[/bold]")
        console.print("\n[dim]Tip: Check that the pipe code is correct and that the containing[/dim]")
        console.print(f"[dim]directory is in {PIPELEXPATH_ENV_KEY} or passed via --library-dir[/dim]")

    console.print("")


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

        # Combine PIPELEXPATH with library_dir args
        pipelexpath_dirs = get_pipelexpath_dirs()
        cli_dirs = [Path(lib_dir) for lib_dir in library_dir] if library_dir else []
        effective_dirs = pipelexpath_dirs + cli_dirs

        if effective_dirs:
            library_manager.load_libraries(library_id=library_id, library_dirs=effective_dirs)

        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
            tag(name=EventProperty.CLI_COMMAND, value=COMMAND)

            do_which_pipe(pipe_code=pipe_code, library_dirs=cli_dirs)
            get_telemetry_manager().track_event(EventName.PIPE_SHOW)
    finally:
        Pipelex.teardown_if_needed()
