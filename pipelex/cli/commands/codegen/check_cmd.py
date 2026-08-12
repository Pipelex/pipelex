"""CLI command `pipelex codegen check`: the offline drift check.

Pure hashing over `codegen.lock` and the files on disk — it does **not** boot Pipelex, load the crate,
touch the network, or need an API key (the whole point: CI checks offline, regeneration is a dev
action). The verdict rides the structured `CodegenCheckReport`; the exit code mirrors the bare
`validate`/`resolve` group — `0` current, `1` drift present (a negative verdict), `2` no lock found (no
verdict).

See the codegen spec → "Offline check algorithm".
"""

from pathlib import Path
from typing import Annotated

import typer

from pipelex.codegen.check import CodegenCheckReport, run_codegen_check
from pipelex.codegen.exceptions import CodegenLockError
from pipelex.codegen.lock import CODEGEN_LOCK_FILENAME


def codegen_check_cmd(
    root: Annotated[
        str,
        typer.Argument(help=f"Directory holding the {CODEGEN_LOCK_FILENAME} and generated artifacts (default: current directory)."),
    ] = ".",
) -> None:
    """Verify generated artifacts are current, offline — no engine, no network, no API key."""
    root_path = Path(root).expanduser()
    try:
        report = run_codegen_check(root=root_path)
    except CodegenLockError as exc:
        typer.secho(exc.message, fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc
    if not report.lock_found:
        typer.secho(f"No {CODEGEN_LOCK_FILENAME} found in '{root_path}' — nothing to check.", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(2)

    _print_report(report, root=root_path)
    if not report.is_current:
        raise typer.Exit(1)


def _print_report(report: CodegenCheckReport, *, root: Path) -> None:
    if report.is_current:
        typer.secho(f"Generated artifacts in '{root}' are up to date.", fg=typer.colors.GREEN)
        return
    typer.secho(f"Generated artifacts in '{root}' have drifted:", fg=typer.colors.RED, err=True)
    for drift in report.drifts:
        typer.secho(f"  [{drift.category}] {drift.path} — {drift.detail}", fg=typer.colors.RED, err=True)
