"""The usage statistics of a `pipelex` or `pipelex-agent` command: read before it runs, reported once it ends.

Both CLIs' root groups run every invocation through `run_with_usage_stats`, which, before the command does any work,
finds the command's path in the click tree (never its arguments), reads every switch and prints the notice; and once
the command ends, whatever its outcome, records one `command_completed` and delivers what the command recorded. The
contract is `conformance/specs/usage-statistics.md`, "`command_completed`" and "Notice".

No event is sent for `--help`, `--version`, an invocation with no command, or the `usage-stats` group itself, whose
commands never send, queue or print the notice.
"""

import time
from collections.abc import Callable, Sequence
from typing import NamedTuple, TypeVar

import click

from pipelex.base_exceptions import PipelexError
from pipelex.system.usage_stats.usage_stats_client import configure_usage_stats_for_cli, get_usage_stats_client
from pipelex.system.usage_stats.usage_stats_contract import (
    OTHER_COMMAND,
    PIPELEX_AGENT_COMMANDS,
    PIPELEX_COMMANDS,
    UsageStatsEventName,
    UsageStatsOutcome,
    UsageStatsSurface,
)
from pipelex.system.usage_stats.usage_stats_events import CommandCompletedProperties, UsageStatsEvent, bounded_duration_ms
from pipelex.system.usage_stats.usage_stats_runs import usage_stats_error_domain

#: The statistics command group, `pipelex usage-stats`.
STATISTICS_GROUP_NAME = "usage-stats"
#: The exit code of a command interrupted by Ctrl-C, as Typer and the shells report it.
INTERRUPTED_EXIT_CODE = 130

_FORMAT_OPTION = "--format"
_ERROR_FORMAT_OPTION = "--error-format"
_JSON = "json"

ResultT = TypeVar("ResultT")


class CliInvocation(NamedTuple):
    """What an invocation is, as far as statistics go: the command it runs, if one is counted, and who reads its stderr."""

    command: str | None
    is_statistics_group: bool
    is_machine_read: bool


def _find_param(*, command: click.Command, token: str) -> click.Parameter | None:
    for param in command.params:
        if token in param.opts or token in param.secondary_opts:
            return param
    return None


def _takes_value(*, param: click.Parameter) -> bool:
    if isinstance(param, click.Option):
        return not param.is_flag and not param.count
    return True


def _option_value(*, args: Sequence[str], option: str) -> str | None:
    """The last value given to `option` among a leaf command's arguments, as `--option value` or `--option=value`."""
    value: str | None = None
    index_arg = 0
    while index_arg < len(args):
        token = args[index_arg]
        if token == "--":
            break
        if token == option and index_arg + 1 < len(args):
            value = args[index_arg + 1]
            index_arg += 2
            continue
        if token.startswith(f"{option}="):
            value = token.split("=", 1)[1]
        index_arg += 1
    return value


def _default_of(*, command: click.Command, option: str) -> str | None:
    param = _find_param(command=command, token=option)
    if param is None or param.default is None or callable(param.default):
        return None
    return str(param.default)


def _errors_are_json(*, command: click.Command, args: Sequence[str]) -> bool:
    """Whether a `pipelex-agent` command's errors are JSON: `--error-format`, else `--format`, else its defaults.

    A command with neither option is one of the JSON-only commands, whose errors are always the JSON envelope.
    """
    has_error_format = _find_param(command=command, token=_ERROR_FORMAT_OPTION) is not None
    has_format = _find_param(command=command, token=_FORMAT_OPTION) is not None
    if not has_error_format and not has_format:
        return True
    chosen = _option_value(args=args, option=_ERROR_FORMAT_OPTION) if has_error_format else None
    if chosen is None and has_format:
        chosen = _option_value(args=args, option=_FORMAT_OPTION)
    if chosen is None and has_error_format:
        chosen = _default_of(command=command, option=_ERROR_FORMAT_OPTION)
    if chosen is None and has_format:
        chosen = _default_of(command=command, option=_FORMAT_OPTION)
    return chosen is not None and chosen.strip().lower() == _JSON


def _allowed_commands(*, surface: UsageStatsSurface) -> frozenset[str]:
    match surface:
        case UsageStatsSurface.PIPELEX:
            return PIPELEX_COMMANDS
        case UsageStatsSurface.PIPELEX_AGENT:
            return PIPELEX_AGENT_COMMANDS
        case UsageStatsSurface.API | UsageStatsSurface.PYTHON:
            return frozenset({OTHER_COMMAND})


def _is_machine_read_surface(*, surface: UsageStatsSurface) -> bool:
    match surface:
        case UsageStatsSurface.PIPELEX_AGENT:
            return True
        case UsageStatsSurface.PIPELEX | UsageStatsSurface.API | UsageStatsSurface.PYTHON:
            return False


def resolve_invocation(*, root: click.Group, args: Sequence[str], surface: UsageStatsSurface) -> CliInvocation:
    """Find the command an invocation runs by walking its arguments down the click tree, reading no argument's value.

    The command is its path of names in the tree, `other` when the schema does not list it (or no command has that
    name), and `None` when nothing is counted: help, the version, no command at all, or the statistics group.
    """
    not_counted = CliInvocation(command=None, is_statistics_group=False, is_machine_read=False)
    help_names = {"--help"}
    current: click.Command = root
    path: list[str] = []
    index_arg = 0
    while isinstance(current, click.Group):
        if index_arg >= len(args):
            # A group with no command under it: its help, or a usage error, but no command was run.
            return not_counted
        token = args[index_arg]
        if token in help_names or token == "--":
            return not_counted
        if token.startswith("-"):
            param = _find_param(command=current, token=token.split("=", 1)[0])
            if param is not None and isinstance(param, click.Option) and param.is_eager:
                # `--version` and `-V`: they print and exit before any command runs.
                return not_counted
            consumed = 2 if param is not None and "=" not in token and _takes_value(param=param) else 1
            index_arg += consumed
            continue
        if not path and token == STATISTICS_GROUP_NAME:
            return CliInvocation(command=None, is_statistics_group=True, is_machine_read=False)
        subcommand = current.commands.get(token)
        if subcommand is None:
            return CliInvocation(command=OTHER_COMMAND, is_statistics_group=False, is_machine_read=_is_machine_read_surface(surface=surface))
        path.append(token)
        current = subcommand
        index_arg += 1

    leaf_args = list(args[index_arg:])
    before_separator = leaf_args[: leaf_args.index("--")] if "--" in leaf_args else leaf_args
    if any(token in help_names for token in before_separator):
        return not_counted
    command_path = " ".join(path)
    command = command_path if command_path in _allowed_commands(surface=surface) else OTHER_COMMAND
    is_machine_read = _is_machine_read_surface(surface=surface) and _errors_are_json(command=current, args=leaf_args)
    return CliInvocation(command=command, is_statistics_group=False, is_machine_read=is_machine_read)


def outcome_for_exit_code(*, code: object) -> UsageStatsOutcome:
    """A command's outcome by its exit code: 0 succeeded, 130 cancelled by Ctrl-C, anything else failed."""
    if code is None or code == 0:
        return UsageStatsOutcome.SUCCEEDED
    if code == INTERRUPTED_EXIT_CODE:
        return UsageStatsOutcome.CANCELLED
    return UsageStatsOutcome.FAILED


def run_with_usage_stats(
    *,
    root: click.Group,
    args: Sequence[str],
    surface: UsageStatsSurface,
    strip_flags: frozenset[str],
    invoke: Callable[[], ResultT],
) -> ResultT:
    """Run a CLI invocation between its statistics' start and end.

    Args:
        root: The CLI's root group, whose tree the command is found in.
        args: The invocation's arguments, without the program name.
        surface: Which CLI this is.
        strip_flags: Global flags the root group removes wherever they appear, so they are no command's argument.
        invoke: Runs the invocation, as click's `main` does, standalone mode included.
    """
    invocation = resolve_invocation(root=root, args=[arg for arg in args if arg not in strip_flags], surface=surface)
    if invocation.command is None:
        return invoke()

    client = configure_usage_stats_for_cli(surface=surface, is_machine_read=invocation.is_machine_read)
    started = time.monotonic()
    outcome = UsageStatsOutcome.FAILED
    failure: PipelexError | None = None
    try:
        result = invoke()
        outcome = UsageStatsOutcome.SUCCEEDED
        return result
    except SystemExit as exit_signal:
        outcome = outcome_for_exit_code(code=exit_signal.code)
        raise
    except KeyboardInterrupt:
        outcome = UsageStatsOutcome.CANCELLED
        raise
    except PipelexError as pipelex_error:
        failure = pipelex_error
        raise
    finally:
        if client.is_enabled:
            error_domain = None
            if outcome.is_failed:
                error_domain = usage_stats_error_domain(error=failure) if failure is not None else client.command_error_domain
            client.record(
                event=UsageStatsEvent(
                    name=UsageStatsEventName.COMMAND_COMPLETED,
                    properties=CommandCompletedProperties(
                        command=invocation.command,
                        outcome=outcome,
                        error_domain=error_domain,
                        duration_ms=bounded_duration_ms(seconds=time.monotonic() - started),
                        hosted=True if client.is_command_hosted else None,
                    ),
                )
            )
            # The process's client may have been replaced while the command ran, never its events: finish both.
            current_client = get_usage_stats_client()
            client.finish_command()
            if current_client is not None and current_client is not client:
                current_client.finish_command()
