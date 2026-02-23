"""Agent CLI mthds-lock command — resolve dependencies and generate methods.lock."""

from pipelex.cli.agent_cli.commands.mthds_passthrough import run_mthds


def mthds_lock_cmd() -> None:
    """Resolve dependencies and generate methods.lock.

    This is a thin wrapper around ``mthds lock`` that eliminates the need
    for agents to call the mthds binary directly.
    """
    run_mthds(["lock"])
