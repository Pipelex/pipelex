"""Agent CLI mthds-update command — re-resolve dependencies and update methods.lock."""

from pipelex.cli.agent_cli.commands.mthds_passthrough import run_mthds


def mthds_update_cmd() -> None:
    """Re-resolve dependencies and update methods.lock.

    This is a thin wrapper around ``mthds update`` that eliminates the need
    for agents to call the mthds binary directly.
    """
    run_mthds(["update"])
