"""Command refreshing the pytest-split duration map committed at ``.test_durations``.

Wired into ``make store-test-durations`` (incremental, the default) and
``make store-test-durations-force`` (re-measure everything). The policies it applies — refresh on
missing *coverage* rather than on age, and keep a stored value that has not meaningfully moved —
are stated and justified in ``duration_map``; the contributor-facing page is
``docs/contribute/test-duration-map.md``.

The shape of the work is: snapshot the map, run pytest with ``--store-durations`` over the tests that
need measuring, then post-process what the plugin merged back in. ``--store-durations`` merges into
the existing file rather than replacing it, which is what makes measuring only the missing tests a
legitimate refresh instead of a partial overwrite.
"""

from __future__ import annotations

import subprocess  # noqa: S404
import sys
from pathlib import Path

from rich.markup import escape
from rich.panel import Panel

from pipelex.cli.dev_cli.commands.duration_map import (
    FULL_RUN_RATIO,
    load_duration_map,
    missing_node_ids,
    prune_dead_paths,
    stabilize,
    write_duration_map,
)
from pipelex.runtime_hub import get_console

#: Relative to the repo root, which is where the Make targets invoke this command from.
DURATIONS_PATH = Path(".test_durations")
REPO_ROOT = Path()

#: pytest exits 5 when a selection matches nothing. That is a legitimate no-op here (every test
#: already covered, or a marker expression that excludes the whole subset), not a failure.
PYTEST_EXIT_NO_TESTS_COLLECTED = 5


def _pytest_command(*, extra: list[str]) -> list[str]:
    """A pytest invocation on this interpreter, so the venv is inherited rather than searched for."""
    return [sys.executable, "-m", "pytest", *extra]


def _collect_node_ids(*, markers: str) -> list[str]:
    """Every node id the sharded CI selection would run, in collection order.

    Cheap on purpose — this is the check that decides whether a refresh is owed at all, so it must
    cost seconds rather than a suite run.
    """
    # S603: the argv is built here from this interpreter's path and constants; `markers` comes from the
    # Makefile, and this is a developer-only command that already runs the test suite it is measuring.
    completed = subprocess.run(  # noqa: S603
        _pytest_command(extra=["--collect-only", "-q", "-p", "no:cacheprovider", "-m", markers]),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        console = get_console()
        console.print("[red]✗ Test collection failed — cannot tell which durations are missing.[/red]")
        console.print(escape(completed.stdout[-4000:] or completed.stderr[-4000:]))
        sys.exit(1)
    return [line.strip() for line in completed.stdout.splitlines() if "::" in line]


def _run_and_store(*, markers: str, node_ids: list[str] | None) -> int:
    """Measure tests with ``--store-durations``; ``node_ids=None`` means the whole marker selection.

    Returns pytest's exit code. Output is streamed rather than captured: this is the long step, and a
    silent multi-minute wait reads as a hang.
    """
    extra = [
        "-n",
        "auto",
        "--dist=worksteal",
        "--store-durations",
        "--durations-path",
        str(DURATIONS_PATH),
        "--timeout=180",
        "--timeout-method=thread",
        "--tb=line",
        "-p",
        "no:cacheprovider",
        "--no-header",
        "-m",
        markers,
    ]
    if node_ids is not None:
        extra.extend(node_ids)
    return subprocess.run(_pytest_command(extra=extra), check=False).returncode  # noqa: S603


def store_test_durations_cmd(*, markers: str, force: bool = False, quiet: bool = False) -> None:
    """Refresh ``.test_durations``, measuring only what is missing unless ``force`` is set.

    Args:
        markers: The pytest marker expression the sharded CI job runs, threaded through from the
            Makefile so this can never drift from what ``gha-tests`` selects.
        force: Re-measure the whole marker selection instead of only the tests absent from the map.
        quiet: Trim the success output to a single line. Failures stay loud either way.
    """
    console = get_console()
    previous = load_duration_map(path=DURATIONS_PATH)

    if force:
        console.print(f"[cyan]Re-measuring the full suite[/cyan] ({len(previous)} entries currently recorded)")
        exit_code = _run_and_store(markers=markers, node_ids=None)
    else:
        console.print("[cyan]Collecting tests to find durations that are missing…[/cyan]")
        collected = _collect_node_ids(markers=markers)
        missing = missing_node_ids(collected=collected, durations=previous)
        coverage = 100.0 * (len(collected) - len(missing)) / len(collected) if collected else 100.0
        console.print(f"  {len(collected)} tests collected, {len(missing)} missing from the map ([bold]{coverage:.1f}%[/bold] covered)")

        if not missing:
            # Nothing is missing, so nothing can be bought by re-measuring: recorded values that
            # merely drifted are worth a fraction of a point of shard balance.
            _finalize(previous=previous, quiet=quiet, measured="nothing (coverage already complete)")
            return

        if len(missing) > FULL_RUN_RATIO * len(collected):
            console.print(f"  [yellow]More than {FULL_RUN_RATIO:.0%} of the suite is missing — re-measuring everything instead.[/yellow]")
            exit_code = _run_and_store(markers=markers, node_ids=None)
        else:
            exit_code = _run_and_store(markers=markers, node_ids=missing)

    if exit_code not in {0, PYTEST_EXIT_NO_TESTS_COLLECTED}:
        # The plugin still wrote what it measured, so say so — the file on disk has moved either way.
        console.print(
            f"[red]✗ pytest exited {exit_code}. `{DURATIONS_PATH}` still holds whatever was measured; re-run once the suite is green.[/red]"
        )
        sys.exit(exit_code)

    _finalize(previous=previous, quiet=quiet, measured="the tests that ran")


def _finalize(*, previous: dict[str, float], quiet: bool, measured: str) -> None:
    """Prune, stabilize and write the merged map, then report what actually changed on disk."""
    console = get_console()
    merged = load_duration_map(path=DURATIONS_PATH)
    pruned, dropped = prune_dead_paths(durations=merged, repo_root=REPO_ROOT)
    stabilized = stabilize(previous=previous, current=pruned)
    write_duration_map(path=DURATIONS_PATH, durations=stabilized)

    changed = sum(1 for node_id, value in stabilized.items() if previous.get(node_id) != value)
    added = sum(1 for node_id in stabilized if node_id not in previous)

    if quiet:
        console.print(f"[green]✓ Test durations: {len(stabilized)} entries[/green] ({added} added, {changed} rewritten, {len(dropped)} pruned)")
        return

    lines = [
        f"Measured [cyan]{measured}[/cyan].",
        "",
        f"  entries recorded   [bold]{len(stabilized)}[/bold]",
        f"  newly added        [bold]{added}[/bold]",
        f"  rewritten          [bold]{changed}[/bold]   (values within tolerance keep their stored spelling)",
        f"  pruned (dead file) [bold]{len(dropped)}[/bold]",
    ]
    if dropped:
        lines.append("")
        lines.append("Pruned entries whose test file no longer exists:")
        lines.extend(f"  {escape(node_id)}" for node_id in dropped[:10])
        if len(dropped) > 10:
            lines.append(f"  … and {len(dropped) - 10} more")
    console.print(Panel("\n".join(lines), title="[green]Test durations refreshed[/green]", border_style="green"))
