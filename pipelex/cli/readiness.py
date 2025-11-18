"""System readiness checks for Pipelex CLI."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pipelex
from pipelex.cli.exceptions import ReadinessCheckError
from pipelex.hub import get_console


def _is_in_virtual_environment() -> bool:
    """Check if the current Python process is running inside a virtual environment.

    Returns:
        True if running in a virtual environment, False otherwise
    """
    # Check if we're in a venv (sys.prefix != sys.base_prefix)
    # or in a conda environment (CONDA_DEFAULT_ENV env var is set)
    return sys.prefix != sys.base_prefix or os.environ.get("CONDA_DEFAULT_ENV") is not None or os.environ.get("VIRTUAL_ENV") is not None


def _find_venv_directories() -> list[str]:
    """Find common virtual environment directories in the current project.

    Returns:
        List of found venv directory names
    """
    common_venv_names = [".venv", "venv", "env", ".env"]
    found_venvs: list[str] = []

    # Check current directory and parent directories (up to 3 levels)
    current_path = Path.cwd()
    for _ in range(3):
        for venv_name in common_venv_names:
            venv_path = current_path / venv_name
            if venv_path.is_dir() and (venv_path / "bin" / "python").exists():
                found_venvs.append(venv_name)
        if current_path.parent == current_path:
            break
        current_path = current_path.parent

    return found_venvs


def _is_development_install() -> bool:
    """Check if Pipelex is installed in development/editable mode.

    Returns:
        True if running from a development install (has .git directory in parent paths)
    """
    try:
        pipelex_path = Path(pipelex.__file__).parent
        current = pipelex_path
        for _ in range(5):  # Check up to 5 levels up
            if (current / ".git").exists():
                return True
            if current.parent == current:
                break
            current = current.parent
    except (AttributeError, OSError):
        # If pipelex.__file__ doesn't exist or path operations fail, not a dev install
        return False
    return False


def check_readiness() -> None:
    """For development installs, enforces virtual environment activation

    Raises:
        ReadinessCheckError: if development install without virtual environment
    """
    # Then check virtual environment requirement for development installs
    if _is_development_install() and not _is_in_virtual_environment():
        console = get_console()
        console.print("\n[bold red]❌ Virtual Environment Required (Development Mode)[/bold red]\n")
        console.print("[yellow]Pipelex is running in development mode but no virtual environment is active.[/yellow]\n")

        # Try to find venv directories and provide specific activation instructions
        found_venvs = _find_venv_directories()
        if found_venvs:
            console.print("[bold cyan]Found virtual environment(s) in your project:[/bold cyan]")
            for venv_name in found_venvs:
                console.print(f"  • [green]{venv_name}[/green]")
            console.print()
            console.print("[bold green]To activate your virtual environment:[/bold green]")
            venv_example = found_venvs[0]
            console.print(f"  [cyan]source {venv_example}/bin/activate[/cyan]  [dim]# On macOS/Linux[/dim]")
            console.print(f"  [cyan]{venv_example}\\Scripts\\activate[/cyan]     [dim]# On Windows[/dim]\n")
        else:
            console.print("[bold green]To create and activate a virtual environment:[/bold green]")
            console.print("  [cyan]python -m venv .venv[/cyan]")
            console.print("  [cyan]source .venv/bin/activate[/cyan]  [dim]# On macOS/Linux[/dim]")
            console.print("  [cyan].venv\\Scripts\\activate[/cyan]     [dim]# On Windows[/dim]\n")

        console.print("[bold yellow]Why is this required?[/bold yellow]")
        console.print("Development mode requires a virtual environment to avoid conflicts\nwith system packages and ensure reproducible builds.\n")

        msg = "Development install detected but no virtual environment is active. Please activate your virtual environment and try again."
        raise ReadinessCheckError(msg)
