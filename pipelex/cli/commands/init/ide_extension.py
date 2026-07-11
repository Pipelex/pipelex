"""IDE extension detection and installation for Pipelex."""

import shutil
import subprocess  # noqa: S404

from rich.console import Console
from rich.markup import escape
from rich.prompt import Confirm

EXTENSION_ID = "Pipelex.pipelex"

_IDE_INFO: dict[str, dict[str, str]] = {
    "VS Code": {
        "cmd": "code",
        "url": "https://marketplace.visualstudio.com/items?itemName=pipelex.pipelex",
        "marketplace_name": "VS Code Marketplace",
    },
    "Cursor": {
        "cmd": "cursor",
        "url": "https://open-vsx.org/extension/Pipelex/pipelex",
        "marketplace_name": "Open VSX Registry",
    },
}


def _is_extension_installed(cmd: str) -> bool:
    """Check if the Pipelex extension is installed using the IDE CLI.

    Args:
        cmd: CLI command for the IDE (e.g. "code" or "cursor").

    Returns:
        True if the extension is listed by --list-extensions, False otherwise.
    """
    try:
        result = subprocess.run(  # noqa: S603
            [cmd, "--list-extensions"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            return False
        installed_extensions = result.stdout.strip().lower().splitlines()
        return EXTENSION_ID.lower() in installed_extensions
    except (subprocess.TimeoutExpired, OSError):
        return False


def _get_available_ide_commands() -> dict[str, dict[str, str]]:
    """Return IDE info dicts for IDEs whose CLI is available on PATH."""
    return {ide_name: info for ide_name, info in _IDE_INFO.items() if shutil.which(info["cmd"]) is not None}


def _install_extension(ide_name: str, *, cmd: str, console: Console) -> bool:
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
            console.print(f"  [red]✗ Failed to install in {ide_name}: {escape(result.stderr.strip())}[/red]")
            return False
    except subprocess.TimeoutExpired:
        console.print(f"  [red]✗ Installation timed out for {ide_name}[/red]")
        return False
    except OSError as exc:
        console.print(f"  [red]✗ Could not run '{cmd}' for {ide_name}: {escape(str(exc))}[/red]")
        return False


def suggest_extension_install_if_needed(*, console: Console) -> None:
    """Check whether the Pipelex IDE extension is installed and offer to install it.

    Uses ``<cmd> --list-extensions`` to reliably detect whether the extension
    is active in each IDE. Prompts to install for each IDE that has a CLI
    available but does not have the extension.
    """
    available_ides = _get_available_ide_commands()

    # Determine which IDEs still need the extension
    ides_needing_install = {ide_name: info for ide_name, info in available_ides.items() if not _is_extension_installed(info["cmd"])}

    if not ides_needing_install:
        return

    ide_names = " and ".join(ides_needing_install.keys())
    console.print(f"💡 The Pipelex extension for {ide_names} provides syntax highlighting for .mthds files.")
    for info in ides_needing_install.values():
        console.print(f"   {info['marketplace_name']}: [cyan]{info['url']}[/cyan]")

    install = Confirm.ask(
        f"[bold]Install the Pipelex extension in {ide_names}?[/bold]",
        console=console,
        default=True,
    )

    if install:
        for ide_name, info in ides_needing_install.items():
            _install_extension(ide_name, cmd=info["cmd"], console=console)
    else:
        console.print("[dim]You can install it later from the IDE marketplace or the links above.[/dim]")
