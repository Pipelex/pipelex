"""Passthrough helper for delegating to the plxt CLI binary."""

import shutil
import subprocess  # noqa: S404
import sys

import typer


def run_plxt(subcommand: str, file_path: str) -> None:
    """Execute a plxt subcommand with full stdin/stdout/stderr passthrough.

    Locates the plxt binary (guaranteed co-installed via pipelex-tools dependency),
    runs ``plxt <subcommand> <file_path>``, and exits with the same return code.

    Args:
        subcommand: The plxt subcommand to run (e.g., "fmt", "lint").
        file_path: Path to the file to process.
    """
    plxt_path = shutil.which("plxt")
    if plxt_path is None:
        print(
            "plxt binary not found. It should be installed as part of pipelex-tools. Try: pip install pipelex-tools",
            file=sys.stderr,
        )
        raise typer.Exit(1)

    result = subprocess.run(  # noqa: S603
        [plxt_path, subcommand, file_path],
        check=False,
    )
    raise typer.Exit(result.returncode)
