"""Where runs execute, as `pipelex init` sets it up: on the hosted Pipelex API, or on this machine.

The answer is written to `[run] execution` in the target `pipelex.toml`, the default `pipelex run` and
`pipelex-agent run` take when a command passes neither `--hosted` nor `--local`. The hosted path then needs a
Pipelex API key, which `pipelex login` obtains; the local path is the backends, routing and credentials steps the
init command runs itself.
"""

from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

import tomlkit
from rich.console import Console
from rich.markup import escape

from pipelex.cli.commands.login.api_key_store import find_pipelex_api_key
from pipelex.cli.commands.login.command import LOGIN_PASTE_COMMAND, login_with_browser
from pipelex.cli.exceptions import PipelexCLIError
from pipelex.hosted.api_key_check import PIPELEX_API_KEY_PREFIX, is_well_formed_pipelex_api_key
from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY
from pipelex.hosted.run_config import RunExecution
from pipelex.tools.misc.exceptions import TomlError
from pipelex.tools.misc.toml_utils import load_toml_from_path, load_toml_with_tomlkit, save_toml_to_path

#: The section of `pipelex.toml` holding the run commands' defaults, and the key naming where runs execute.
RUN_SECTION = "run"
RUN_EXECUTION_KEY = "execution"


class SetupPath(StrEnum):
    """The two ways `pipelex init` sets up running methods."""

    HOSTED = "hosted"
    LOCAL = "local"

    @property
    def run_execution(self) -> RunExecution:
        """The `[run] execution` this path writes."""
        match self:
            case SetupPath.HOSTED:
                return RunExecution.HOSTED
            case SetupPath.LOCAL:
                return RunExecution.LOCAL


#: The path Enter takes, and the one taken when nobody is asked (`pipelex doctor --fix`).
DEFAULT_SETUP_PATH = SetupPath.HOSTED


def read_run_execution(*, pipelex_toml_path: Path) -> RunExecution | None:
    """The `[run] execution` a `pipelex.toml` sets, or `None` when the file is missing, unreadable or sets none."""
    if not pipelex_toml_path.is_file():
        return None
    try:
        document = load_toml_from_path(pipelex_toml_path)
    except (OSError, TomlError):
        return None
    run_section: Any = document.get(RUN_SECTION)
    if not isinstance(run_section, Mapping):
        return None
    value: Any = cast("Mapping[str, Any]", run_section).get(RUN_EXECUTION_KEY)
    if not isinstance(value, str):
        return None
    try:
        return RunExecution(value)
    except ValueError:
        return None


def write_run_execution(*, pipelex_toml_path: Path, execution: RunExecution) -> None:
    """Set `[run] execution` in a `pipelex.toml`, keeping every other line, comments included.

    Creates the file, or the `[run]` table, when missing.

    Raises:
        PipelexCLIError: If the file holds a `run` that is not a table.
    """
    if pipelex_toml_path.is_file():
        document = load_toml_with_tomlkit(pipelex_toml_path)
    else:
        pipelex_toml_path.parent.mkdir(parents=True, exist_ok=True)
        document = tomlkit.document()
    if RUN_SECTION not in document:
        document[RUN_SECTION] = tomlkit.table()
    run_section = document[RUN_SECTION]
    if not isinstance(run_section, dict):
        msg = f"'{RUN_SECTION}' in {pipelex_toml_path} is not a table, so where runs execute cannot be written there"
        raise PipelexCLIError(msg)
    run_section[RUN_EXECUTION_KEY] = execution.value
    save_toml_to_path(document, path=pipelex_toml_path)


def apply_setup_path_setting(*, console: Console, setup_path: SetupPath, pipelex_toml_path: Path) -> None:
    """Write where runs execute for this setup path, and say so."""
    write_run_execution(pipelex_toml_path=pipelex_toml_path, execution=setup_path.run_execution)
    match setup_path:
        case SetupPath.HOSTED:
            where = "on the hosted Pipelex API"
        case SetupPath.LOCAL:
            where = "on this machine"
    setting = escape(f'[{RUN_SECTION}] {RUN_EXECUTION_KEY} = "{setup_path.value}"')
    console.print(f"[green]✓[/green] Runs execute {where} by default [dim]({setting} in {escape(str(pipelex_toml_path))})[/dim]")


def ensure_pipelex_api_key(*, console: Console, interactive: bool) -> None:
    """Make sure hosted runs have a Pipelex API key: keep the one already set, else sign in, else say how.

    A key already in `PIPELEX_API_KEY` or saved in the home `.env` is kept without a login or a network call, so a
    machine or a test that sets one goes through without waiting. With no key and nobody to answer, it prints
    `pipelex login` instead of opening a browser.

    Args:
        console: Where to say what happened.
        interactive: Whether someone is there to sign in through the browser.
    """
    console.print()
    existing_key = find_pipelex_api_key()
    if existing_key:
        console.print(f"[green]✓[/green] A Pipelex API key is already set ({PIPELEX_API_KEY_ENV_KEY}); hosted runs will use it.")
        if not is_well_formed_pipelex_api_key(api_key=existing_key):
            console.print(f"[yellow]⚠ It does not look like a Pipelex API key, which starts with {PIPELEX_API_KEY_PREFIX}.[/yellow]")
        console.print("[dim]To replace it, run[/dim] [cyan]pipelex login[/cyan][dim].[/dim]")
        return
    if not interactive:
        console.print("[yellow]Hosted runs need a Pipelex API key.[/yellow] Run [cyan]pipelex login[/cyan] to get one.")
        return
    console.print("[bold]Hosted runs need a Pipelex API key: let's get one.[/bold]")
    outcome = login_with_browser(console=console)
    if not outcome.is_saved:
        console.print(
            "[yellow]No key was saved.[/yellow] Hosted runs need one: run [cyan]pipelex login[/cyan] "
            f"(or [cyan]{LOGIN_PASTE_COMMAND}[/cyan]) when you are ready."
        )
