"""Credential prompting and persistent storage for the init command."""

import os
import stat
from pathlib import Path
from typing import Any, cast

from dotenv import dotenv_values, set_key
from rich.console import Console
from rich.markup import escape
from rich.prompt import Prompt

from pipelex.system.configuration.config_loader import config_manager
from pipelex.tools.misc.dict_utils import extract_vars_from_strings_recursive
from pipelex.tools.misc.toml_utils import load_toml_from_path


def get_global_env_path() -> Path:
    """Return the path to the credentials file in the home configuration directory (`~/.pipelex/.env`, or under `PIPELEX_HOME`)."""
    return config_manager.global_config_dir / ".env"


def read_env_file(env_path: Path) -> dict[str, str]:
    """Read an existing .env file and return key-value pairs.

    Ignores blank lines and comment lines (starting with #).

    Args:
        env_path: Path to the .env file.

    Returns:
        Dictionary of environment variable names to values.
    """
    entries: dict[str, str] = {}
    if not env_path.is_file():
        return entries
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        entries[key.strip()] = value.strip()
    return entries


def write_env_file(env_path: Path, *, entries: dict[str, str]) -> None:
    """Write key-value pairs to a .env file with a header comment.

    Creates parent directories if needed. Sets file permissions to 0600 (user-only).

    Args:
        env_path: Path to the .env file.
        entries: Dictionary of environment variable names to values.
    """
    env_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [
        "# Pipelex credentials — managed by 'pipelex init' and 'pipelex login'",
        "# You can also edit this file manually.",
        "",
    ]
    for key, value in entries.items():
        lines.append(f"{key}={value}")
    lines.append("")  # trailing newline

    env_path.write_text("\n".join(lines), encoding="utf-8")
    env_path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def set_env_file_entry(*, env_path: Path, key: str, value: str) -> None:
    """Set one entry of a .env file, keeping every other line as it is, comments included.

    Creates the file and its parent directories when missing. Every assignment of `key` already in the file, an
    `export` one included, is replaced by `key=value`, so no later line can shadow it. The file is readable and
    writable by its owner only (mode 0600), before and after the write, so the value never sits in a file others can read.

    Args:
        env_path: Path to the .env file.
        key: The variable to set.
        value: Its value, written unquoted: the caller passes a value with no whitespace, quote, `#` or backslash.
    """
    env_path.parent.mkdir(parents=True, exist_ok=True)
    owner_only = stat.S_IRUSR | stat.S_IWUSR
    if env_path.is_file():
        # The rewrite keeps the mode it finds, so tighten it first rather than after.
        env_path.chmod(owner_only)
    set_key(env_path, key, value, quote_mode="never")
    env_path.chmod(owner_only)


def read_env_file_value(*, env_path: Path, key: str) -> str | None:
    """The value a .env file gives `key`, read as the runtime's own `.env` loading reads it, or `None` when it gives none."""
    if not env_path.is_file():
        return None
    value = dotenv_values(env_path).get(key)
    return value or None


def get_required_vars_for_enabled_backends(backends_toml_path: Path) -> dict[str, list[str]]:
    """Determine which env vars are required by each enabled backend.

    Args:
        backends_toml_path: Path to backends.toml.

    Returns:
        Dictionary mapping env var names to the list of backend display names that need them.
    """
    if not backends_toml_path.exists():
        return {}

    toml_data = load_toml_from_path(backends_toml_path)
    var_to_backends: dict[str, list[str]] = {}

    for backend_key, backend_section in toml_data.items():
        if backend_key == "internal":
            continue
        if not isinstance(backend_section, dict):
            continue
        typed_section = cast("dict[str, Any]", backend_section)
        if not typed_section.get("enabled", False):
            continue

        display_name: str = typed_section.get("display_name", backend_key)
        required_vars = extract_vars_from_strings_recursive(typed_section)
        for var_name in sorted(required_vars):
            var_to_backends.setdefault(var_name, []).append(display_name)

    return var_to_backends


def prompt_credentials(*, console: Console, backends_toml_path: Path) -> None:
    """Prompt the user for missing credentials and persist them to the `.env` in the home configuration directory.

    Reads the backends.toml to find which env vars are needed by enabled backends,
    checks which are already set, and prompts only for missing ones.

    Args:
        console: Rich Console instance for user interaction.
        backends_toml_path: Path to the backends.toml file.
    """
    var_to_backends = get_required_vars_for_enabled_backends(backends_toml_path)
    if not var_to_backends:
        return

    # Determine which vars are missing from the environment
    missing_vars = {var_name: backend_names for var_name, backend_names in var_to_backends.items() if not os.getenv(var_name)}

    if not missing_vars:
        console.print("[green]All required credentials are already set.[/green]")
        return

    console.print()
    console.print("[bold cyan]Credential Setup[/bold cyan]")
    console.print(f"[dim]{len(missing_vars)} credential(s) needed for your enabled backends.[/dim]")
    console.print("[dim]Press Enter to skip any credential — you can set it later.[/dim]")
    console.print()

    # Read existing .env file to preserve manually-set values
    global_env_path = get_global_env_path()
    entries = read_env_file(global_env_path)

    collected_count = 0
    for var_name, backend_names in sorted(missing_vars.items()):
        backends_str = ", ".join(backend_names)
        value = Prompt.ask(
            f"  [bold]{escape(var_name)}[/bold] [dim](required by {escape(backends_str)})[/dim]", default="", console=console, password=True
        )
        if value:
            entries[var_name] = value
            os.environ[var_name] = value
            collected_count += 1

    if collected_count > 0:
        write_env_file(global_env_path, entries=entries)
        console.print()
        console.print(f"[green]Saved {collected_count} credential(s) to {escape(str(global_env_path))}[/green]")
    else:
        console.print()
        console.print("[dim]No credentials entered. You can set them later by running:[/dim] [cyan]pipelex init credentials[/cyan]")
