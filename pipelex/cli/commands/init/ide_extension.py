"""IDE extension detection and installation for Pipelex."""

import shutil
import subprocess  # noqa: S404
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm

EXTENSION_FOLDER_PATTERN = "pipelex.pipelex-*"
EXTENSION_ID = "Pipelex.pipelex"
EXTENSION_URL = "https://open-vsx.org/extension/Pipelex/pipelex"

_IDE_COMMANDS = {
    "VS Code": "code",
    "Cursor": "cursor",
}

_EXTENSIONS_DIRS = {
    "VS Code": Path.home() / ".vscode" / "extensions",
    "Cursor": Path.home() / ".cursor" / "extensions",
}


def _get_ides_with_extension_installed() -> set[str]:
    """Return the set of IDE names that already have the Pipelex extension installed."""
    installed_in: set[str] = set()
    for ide_name, extensions_dir in _EXTENSIONS_DIRS.items():
        if extensions_dir.is_dir() and list(extensions_dir.glob(EXTENSION_FOLDER_PATTERN)):
            installed_in.add(ide_name)
    return installed_in


def _get_available_ide_commands() -> dict[str, str]:
    """Return a dict of IDE name -> CLI command for IDEs whose CLI is available on PATH."""
    return {ide_name: cmd for ide_name, cmd in _IDE_COMMANDS.items() if shutil.which(cmd) is not None}


def _install_extension(ide_name: str, cmd: str, console: Console) -> bool:
    """Install the Pipelex extension for a given IDE.

    Args:
        ide_name: Human-readable IDE name (e.g. "VS Code").
        cmd: CLI command for the IDE (e.g. "code").
        console: Rich Console instance for output.

    Returns:
        True if installation succeeded, False otherwise.
    """
    try:
        result = subprocess.run(  # noqa: S603
            [cmd, "--install-extension", EXTENSION_ID],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode == 0:
            console.print(f"  [green]✓ Installed in {ide_name}[/green]")
            return True
        else:
            console.print(f"  [red]✗ Failed to install in {ide_name}: {result.stderr.strip()}[/red]")
            return False
    except subprocess.TimeoutExpired:
        console.print(f"  [red]✗ Installation timed out for {ide_name}[/red]")
        return False
    except OSError as exc:
        console.print(f"  [red]✗ Could not run '{cmd}' for {ide_name}: {exc}[/red]")
        return False


def suggest_extension_install_if_needed(console: Console) -> None:
    """Check whether the Pipelex IDE extension is installed and offer to install it.

    Checks VS Code and Cursor extension directories for a folder matching
    ``pipelex.pipelex-*``. If the extension is not found in any IDE, prints a
    suggestion and offers to install it via the IDE CLI commands if available.
    """
    installed_in = _get_ides_with_extension_installed()
    available_commands = _get_available_ide_commands()

    # Determine which IDEs still need the extension
    ides_needing_install = {ide_name: cmd for ide_name, cmd in available_commands.items() if ide_name not in installed_in}

    if not ides_needing_install:
        # Either already installed everywhere or no IDE CLI available
        return

    ide_names = " and ".join(ides_needing_install.keys())
    console.print(f"💡 The Pipelex extension for {ide_names} provides syntax highlighting for .pplx files.")
    console.print(f"   More info: [cyan]{EXTENSION_URL}[/cyan]")

    install = Confirm.ask(
        f"[bold]Install the Pipelex extension in {ide_names}?[/bold]",
        console=console,
        default=True,
    )

    if install:
        for ide_name, cmd in ides_needing_install.items():
            _install_extension(ide_name, cmd, console)
    else:
        console.print("[dim]You can install it later from the IDE marketplace or the link above.[/dim]")
