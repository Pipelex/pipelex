"""`pipelex usage-stats`: see and change the anonymous usage statistics of every Pipelex tool on this machine.

The group's commands act on the shared state every reporting tool reads (`~/.mthds/usage-stats/`), so `disable` here
turns statistics off for `plxt`, the VS Code extension and the `mthds` CLI too. They never send, queue or print the
notice, and exit 0 unless they could not do what they say. The group also serves `pipelex-agent`, which has none of its
own. The contract is `conformance/specs/usage-statistics.md`, "Commands".
"""

import os
from enum import StrEnum
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from pipelex.system.usage_stats.usage_stats_client import is_pytest_process
from pipelex.system.usage_stats.usage_stats_contract import NOTICE_DETAILS_URL
from pipelex.system.usage_stats.usage_stats_core import UsageStatsState
from pipelex.system.usage_stats.usage_stats_status import describe_off_by, read_usage_stats_status
from pipelex.system.usage_stats.usage_stats_switches import read_switches

usage_stats_app = typer.Typer(no_args_is_help=True)


class UsageStatsStatusFormat(StrEnum):
    TEXT = "text"
    JSON = "json"

    @property
    def is_json(self) -> bool:
        match self:
            case UsageStatsStatusFormat.JSON:
                return True
            case UsageStatsStatusFormat.TEXT:
                return False


def _current_dir(*, state: UsageStatsState) -> Path:
    try:
        return Path.cwd()
    except OSError:
        # A working directory deleted under the process: no project around it, so no project setting.
        return state.home


def _fail(*, message: str) -> NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(1)


@usage_stats_app.command(name="status", help="Show whether usage statistics are on, what turns them off, and the installation identifier")
def status_command(
    output_format: Annotated[
        UsageStatsStatusFormat,
        typer.Option("--format", help="Output format: text (default) or json, the status object other tools read"),
    ] = UsageStatsStatusFormat.TEXT,
) -> None:
    """Show the statistics status. Read-only: it creates nothing, migrates nothing and prints no notice."""
    state = UsageStatsState.make_for_current_home()
    status = read_usage_stats_status(state=state, env=os.environ, cwd=_current_dir(state=state), is_pytest=is_pytest_process())
    if output_format.is_json:
        typer.echo(status.model_dump_json())
        return
    if status.enabled:
        typer.echo("Usage statistics are on.")
    else:
        typer.echo("Usage statistics are off, turned off by:")
        for token in status.off_by:
            typer.echo(f"  - {describe_off_by(token=token)} ({token})")
    typer.echo(f"Installation identifier: {status.installation_id or 'none yet'}")
    typer.echo(f"Notice version seen on this machine: {status.notice_version}")
    if status.internal:
        typer.echo("This machine is marked as one of the Pipelex team's.")
    typer.echo(f"In CI: {'yes' if status.ci else 'no'}; in a container: {'yes' if status.container else 'no'}")
    typer.echo(f"Shared state: {status.state_dir}")
    typer.echo(f"Details: {NOTICE_DETAILS_URL}")


@usage_stats_app.command(name="disable", help="Turn usage statistics off on this machine, for every Pipelex tool")
def disable_command() -> None:
    """Create the shared `disabled` file and delete every event any tool has queued."""
    state = UsageStatsState.make_for_current_home()
    try:
        state.disable()
    except OSError as os_error:
        _fail(message=f"Usage statistics could not be turned off: {state.disabled_file} could not be written ({os_error.strerror}).")
    typer.echo("Usage statistics are off on this machine, for every Pipelex tool, and every queued event was deleted.")


@usage_stats_app.command(name="enable", help="Turn usage statistics back on on this machine, and name any other switch that keeps them off")
def enable_command() -> None:
    """Delete the shared `disabled` file, set `legacy-migrated`, and name every switch that still says off."""
    state = UsageStatsState.make_for_current_home()
    try:
        state.enable()
    except OSError as os_error:
        _fail(message=f"Usage statistics could not be turned on: the shared state in {state.state_dir} could not be written ({os_error.strerror}).")
    still_off = read_switches(state=state, env=os.environ, cwd=_current_dir(state=state), is_pytest=is_pytest_process())
    if not still_off:
        typer.echo("Usage statistics are on on this machine.")
        return
    typer.echo("This machine's choice is now on, but usage statistics stay off, turned off by:")
    for token in still_off:
        typer.echo(f"  - {describe_off_by(token=token)} ({token})")


@usage_stats_app.command(name="reset-id", help="Replace this machine's anonymous installation identifier with a new one")
def reset_id_command() -> None:
    """Delete every queued event and the identifier, create a new identifier and print it."""
    state = UsageStatsState.make_for_current_home()
    try:
        new_id = state.replace_installation_id()
    except OSError as os_error:
        _fail(message=f"The installation identifier could not be replaced in {state.state_dir} ({os_error.strerror}).")
    typer.echo(new_id)
