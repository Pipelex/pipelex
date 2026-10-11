"""Passthrough helper for delegating to the plxt CLI binary."""

import os
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import]

import typer

from pipelex.cli.agent_cli.commands.agent_output import agent_error
from pipelex.system.usage_stats.usage_stats_contract import UsageStatsEnvVar


def run_plxt(subcommand: str, *, file_path: str) -> None:
    """Execute a plxt subcommand with full stdin/stdout/stderr passthrough.

    Locates the plxt binary, runs ``plxt <subcommand> <file_path>``,
    and exits with the same return code.

    Args:
        subcommand: The plxt subcommand to run (e.g., "fmt", "lint").
        file_path: Path to the file to process.
    """
    plxt_path = shutil.which("plxt")
    if plxt_path is None:
        agent_error(
            message="plxt binary not found. Install via: uv tool install pipelex-tools",
            error_type="BinaryNotFoundError",
        )

    # The command's usage statistics are pipelex-agent's own, so the plxt it delegates to reports none of its own.
    result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        [plxt_path, subcommand, file_path],
        check=False,
        env={**os.environ, UsageStatsEnvVar.TOOL_SWITCH: "0"},
    )
    raise typer.Exit(result.returncode)
