"""Command enforcing the two-hub layering boundary across ``pipelex/`` source and ``tests/``.

`interpreter_hub` may import `runtime_hub`; **`runtime_hub` must never import `interpreter_hub`.** The guard
checks the forbidden direction — a declared runtime-layer module may not import or name
``pipelex.interpreter_hub`` — plus the dead-module rule: nothing anywhere may still reference the deleted
``pipelex.hub``. The canonical human-readable specification lives in ``docs/contribute/hub-layering.md``.

The pure-AST collection logic lives in the stdlib-only ``hub_layering_guard`` module; this module is
the ``rich``/``pipelex.runtime_hub`` presentation layer wired into the ``pipelex-dev`` Typer app
(``make check-hub-layering`` / ``make agent-check`` / CI). The tree is fully compliant, so the guard
hard-blocks on ANY violation; the only sanctioned exceptions are a ``TYPE_CHECKING``-deferred type-only
import and the inline ``# hub-layering: ignore`` escape hatch.

The guard checks the *rule*. The *property* it protects — importing the inference layer loads zero
interpreter modules — is pinned separately by ``tests/unit/pipelex/test_runtime_layer_import_closure.py``, because
a stray import somewhere else entirely could break the property without touching a hub import.
"""

from __future__ import annotations

import sys

from rich.markup import escape
from rich.panel import Panel

from pipelex.cli.dev_cli.commands.hub_layering_guard import (
    RUNTIME_LAYER_PACKAGES,
    SCAN_ROOTS,
    HubLayeringViolation,
    collect_all_violations,
)
from pipelex.runtime_hub import get_console

# --------------------------------------------------------------------------------------
# Command entrypoint
# --------------------------------------------------------------------------------------


def check_hub_layering_cmd(*, quiet: bool = False) -> None:
    """Enforce the ``runtime_hub`` / ``interpreter_hub`` layering boundary.

    Args:
        quiet: If True, keep the success output to a single line (for Make targets / CI). Quiet only
            trims the happy path — a failure still prints the full actionable violation list.
    """
    console = get_console()

    missing = [root for root in SCAN_ROOTS if not root.exists()]
    if missing:
        # An error is always loud — quiet only trims success output, never failures.
        roots = ", ".join(f"[cyan]{escape(root.as_posix())}/[/cyan]" for root in missing)
        console.print(f"[red]✗ Hub-layering check: FAILED[/red] - scan root(s) {roots} do not exist")
        sys.exit(1)

    violations = collect_all_violations(roots=SCAN_ROOTS)

    if not violations:
        # Success is the only thing quiet trims: one line in quiet mode, a panel otherwise.
        if quiet:
            console.print("[green]✓ Hub-layering check: PASSED[/green]")
        else:
            _print_success_panel()
        return

    # Failure is always actionable: list the offending sites so no re-run is needed — in quiet mode
    # too, since the Make targets and CI invoke the guard quietly.
    if quiet:
        console.print(f"[red]✗ Hub-layering check: FAILED[/red] - {len(violations)} violation(s):")
    else:
        _print_failure_panel(violations=violations)
    _print_violations_by_kind(violations=violations)
    sys.exit(1)


def _print_success_panel() -> None:
    """Verbose success output (no violations)."""
    console = get_console()
    layers = ", ".join(RUNTIME_LAYER_PACKAGES)
    console.print()
    console.print(
        Panel(
            f"[green]✓[/green] No hub-layering violations.\n\n[dim]Runtime layer: {escape(layers)}[/dim]",
            title="[bold green]Hub-layering Check: PASSED[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
    )
    console.print()


def _print_failure_panel(*, violations: list[HubLayeringViolation]) -> None:
    """Verbose failure output header."""
    console = get_console()
    console.print()
    console.print(
        Panel(
            f"[red]✗[/red] {len(violations)} hub-layering violation(s) found.\n\n"
            "[dim]The runtime layer must stay importable without loading the method interpreter — "
            "each violation kind below names its remedy.[/dim]",
            title="[bold red]Hub-layering Check: FAILED[/bold red]",
            border_style="red",
            padding=(1, 2),
        )
    )
    console.print()


def _print_violations_by_kind(*, violations: list[HubLayeringViolation]) -> None:
    """Print the violations grouped by kind, each group headed by its remedy."""
    console = get_console()
    grouped: dict[str, list[HubLayeringViolation]] = {}
    for violation in violations:
        grouped.setdefault(violation.kind, []).append(violation)
    for kind_value in sorted(grouped):
        kind_violations = grouped[kind_value]
        kind = kind_violations[0].kind
        console.print(f"[bold]{escape(kind_value)}[/bold] ({len(kind_violations)}) — [dim]{escape(kind.remedy)}[/dim]")
        for violation in kind_violations:
            console.print(f"  [red]{escape(violation.relative_path)}:{violation.lineno}[/red]  [yellow]{escape(violation.detail)}[/yellow]")
    console.print("[dim]See docs/contribute/hub-layering.md[/dim]")
