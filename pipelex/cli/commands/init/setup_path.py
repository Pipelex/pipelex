"""Where runs execute, as `pipelex init` sets it up: on the hosted Pipelex API, or on this machine.

The answer is written to `[run] execution` in the target `pipelex.toml`, the default `pipelex run` and
`pipelex-agent run` take when a command passes neither `--hosted` nor `--local`. The hosted path then needs a
Pipelex API key, which `pipelex login` obtains; the local path is the backends, routing and credentials steps the
init command runs itself.
"""

from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any, NamedTuple, cast

import tomlkit
from rich.console import Console
from rich.markup import escape

from pipelex.cli.commands.login.api_key_store import find_pipelex_api_key
from pipelex.cli.commands.login.command import LOGIN_PASTE_COMMAND, login_with_browser, warn_about_shadowing_env_file
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

    @property
    def is_hosted(self) -> bool:
        return self.run_execution.is_hosted

    @classmethod
    def from_run_execution(cls, *, execution: RunExecution) -> "SetupPath":
        """The path that writes this `[run] execution`."""
        match execution:
            case RunExecution.HOSTED:
                return SetupPath.HOSTED
            case RunExecution.LOCAL:
                return SetupPath.LOCAL


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


def describe_where_runs_execute(*, execution: RunExecution) -> str:
    """Where runs with this execution run, in words."""
    match execution:
        case RunExecution.HOSTED:
            return "on the hosted Pipelex API"
        case RunExecution.LOCAL:
            return "on this machine"


def _setting_text(*, execution: RunExecution) -> str:
    return f'[{RUN_SECTION}] {RUN_EXECUTION_KEY} = "{execution}"'


class ProjectExecutionShadow(NamedTuple):
    """A project's `pipelex.toml` setting another `[run] execution` than the one just written to the home directory."""

    pipelex_toml_path: Path
    execution: RunExecution


def find_project_execution_shadow(
    *, target_config_dir: Path, execution: RunExecution, project_config_dir: Path | None
) -> ProjectExecutionShadow | None:
    """The project's `pipelex.toml` when it sets another `[run] execution` than the one written to `target_config_dir`.

    The project's setting wins over the home one, so a choice written globally does not apply to runs started in that
    project. Nothing is found when there is no project configuration, when it is the target itself, or when it sets the
    same execution or none.

    Args:
        target_config_dir: The configuration directory the setting was written to.
        execution: The setting written there.
        project_config_dir: The `.pipelex/` of the project around the working directory, when there is one.
    """
    if project_config_dir is None or project_config_dir.resolve() == target_config_dir.resolve():
        return None
    project_pipelex_toml_path = project_config_dir / "pipelex.toml"
    project_execution = read_run_execution(pipelex_toml_path=project_pipelex_toml_path)
    if project_execution is None or project_execution == execution:
        return None
    return ProjectExecutionShadow(pipelex_toml_path=project_pipelex_toml_path, execution=project_execution)


def describe_project_execution_shadow(*, shadow: ProjectExecutionShadow) -> str:
    """The warning for a project that overrides the global choice, as plain text."""
    return (
        f"{shadow.pipelex_toml_path} sets {_setting_text(execution=shadow.execution)}, and a project's setting wins over the "
        f"global one: runs started in that project execute {describe_where_runs_execute(execution=shadow.execution)}. "
        "Change it there, or pass --hosted or --local on a run."
    )


def apply_setup_path_setting(*, console: Console, setup_path: SetupPath, pipelex_toml_path: Path, project_config_dir: Path | None) -> None:
    """Write where runs execute for this setup path, say so, and warn when the working directory's project overrides it.

    Args:
        console: Where to say it.
        setup_path: The path chosen.
        pipelex_toml_path: The `pipelex.toml` to write the setting to.
        project_config_dir: The `.pipelex/` of the project around the working directory, when there is one.
    """
    execution = setup_path.run_execution
    write_run_execution(pipelex_toml_path=pipelex_toml_path, execution=execution)
    setting = escape(_setting_text(execution=execution))
    console.print(
        f"[green]✓[/green] Runs execute {describe_where_runs_execute(execution=execution)} by default "
        f"[dim]({setting} in {escape(str(pipelex_toml_path))})[/dim]"
    )
    shadow = find_project_execution_shadow(target_config_dir=pipelex_toml_path.parent, execution=execution, project_config_dir=project_config_dir)
    if shadow is not None:
        console.print(f"[yellow]⚠ {escape(describe_project_execution_shadow(shadow=shadow))}[/yellow]")


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
        warn_about_shadowing_env_file(console=console)
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
