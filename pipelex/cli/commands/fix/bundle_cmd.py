from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from pipelex.cli.commands.bundle_path_resolver import resolve_bundle_target
from pipelex.cli.commands.fix._fix_core import COMMAND, execute_fix
from pipelex.pipeline.fixes.planner import KNOWN_FIX_CODES

_NOT_A_BUNDLE_HINT = "  To fix a bundle, pass a .mthds file or directory: pipelex fix bundle <path>"


def _reject_invalid_rule_filters(*, select_codes: tuple[str, ...] | None, ignore_codes: tuple[str, ...] | None) -> None:
    """Reject a contradictory or typo'd rule selection loudly (exit 2, no verdict).

    A typo'd filter selects *behavior*, so lenient-ignore is wrong — mirrors the agent CLI's
    check with human text-stream presentation.
    """
    if select_codes is not None and ignore_codes is not None:
        typer.secho("Failed to fix: --select and --ignore are mutually exclusive", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    requested_codes: set[str] = set(select_codes or ()) | set(ignore_codes or ())
    unknown_codes = sorted(requested_codes - KNOWN_FIX_CODES)
    if unknown_codes:
        known = ", ".join(sorted(KNOWN_FIX_CODES))
        unknown = ", ".join(unknown_codes)
        typer.secho(f"Failed to fix: unknown fix rule code(s): {unknown}. Known codes: {known}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)


def fix_bundle_cmd(
    path: Annotated[
        str,
        typer.Argument(help="Path to a .mthds bundle file or a pipeline directory"),
    ],
    library_dir: Annotated[
        list[str] | None,
        typer.Option(
            "--library-dir",
            "-L",
            help="Directory to search for pipe definitions (.mthds files). Can be specified multiple times. "
            "Files under these directories are inside the fix write scope.",
        ),
    ] = None,
    allow_signatures: Annotated[
        bool,
        typer.Option(
            "--allow-signatures",
            help="Accept PipeSignature placeholders in the dependency graph (lenient mode).",
        ),
    ] = False,
    max_iterations: Annotated[
        int | None,
        typer.Option("--max-iterations", min=1, help="Maximum fix-apply rounds before reporting non-convergence"),
    ] = None,
    select_codes_raw: Annotated[
        list[str] | None,
        typer.Option("--select", help="Only apply the named fix rule code. Can be specified multiple times."),
    ] = None,
    ignore_codes_raw: Annotated[
        list[str] | None,
        typer.Option("--ignore", help="Skip the named fix rule code. Can be specified multiple times."),
    ] = None,
    diff: Annotated[
        bool,
        typer.Option(
            "--diff",
            help="Preview: show the changes as a unified diff without writing any file. Exit codes keep the same verdict semantics.",
        ),
    ] = False,
) -> None:
    """Fix a bundle file (.mthds) or pipeline directory in place.

    Runs the validate → apply safe fixes → re-validate loop until the bundle is valid, out
    of fixes, or the iteration cap is reached, and names every change made.

    Examples:
        pipelex fix bundle my_bundle.mthds
        pipelex fix bundle pipeline_01/
        pipelex fix bundle my_bundle.mthds --select match-sequence-output
        pipelex fix bundle my_bundle.mthds --diff
    """
    select_codes = tuple(select_codes_raw) if select_codes_raw else None
    ignore_codes = tuple(ignore_codes_raw) if ignore_codes_raw else None
    _reject_invalid_rule_filters(select_codes=select_codes, ignore_codes=ignore_codes)

    bundle_path, library_dir = resolve_bundle_target(
        path,
        library_dir=library_dir,
        command=COMMAND,
        not_a_bundle_hint=_NOT_A_BUNDLE_HINT,
    )
    library_dirs = [Path(lib_dir) for lib_dir in library_dir] if library_dir else None

    execute_fix(
        Path(bundle_path),
        library_dirs=library_dirs,
        allow_signatures=allow_signatures,
        max_iterations=max_iterations,
        select_codes=select_codes,
        ignore_codes=ignore_codes,
        diff=diff,
    )
