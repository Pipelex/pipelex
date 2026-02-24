"""Passthrough helper for delegating to the mthds CLI binary."""

import shutil
import subprocess  # noqa: S404
import sys

import typer


def run_mthds(args: list[str], cwd: str | None = None) -> None:
    """Execute a mthds subcommand with full stdin/stdout/stderr passthrough.

    Locates the mthds binary on PATH, runs ``mthds <args>``, and exits with
    the same return code.

    Args:
        args: The full argument list to pass to the mthds binary.
        cwd: Optional working directory for the subprocess.
    """
    mthds_path = shutil.which("mthds")
    if mthds_path is None:
        print(
            "mthds binary not found. Try: pip install mthds",
            file=sys.stderr,
        )
        raise typer.Exit(1)

    result = subprocess.run(  # noqa: S603
        [mthds_path, *args],
        check=False,
        cwd=cwd,
    )
    raise typer.Exit(result.returncode)
