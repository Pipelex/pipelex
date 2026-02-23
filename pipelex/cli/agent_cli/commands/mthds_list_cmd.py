"""Agent CLI mthds-list command — display the package manifest."""

from pipelex.cli.agent_cli.commands.mthds_passthrough import run_mthds


def mthds_list_cmd() -> None:
    """Display the package manifest (METHODS.toml) for the current directory.

    This is a thin wrapper around ``mthds list`` that eliminates the need
    for agents to call the mthds binary directly.
    """
    run_mthds(["list"])
