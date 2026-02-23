"""Agent CLI mthds-install command — install dependencies from methods.lock."""

from pipelex.cli.agent_cli.commands.mthds_passthrough import run_mthds


def mthds_install_cmd() -> None:
    """Install dependencies from methods.lock.

    This is a thin wrapper around ``mthds install`` that eliminates the need
    for agents to call the mthds binary directly.
    """
    run_mthds(["install"])
