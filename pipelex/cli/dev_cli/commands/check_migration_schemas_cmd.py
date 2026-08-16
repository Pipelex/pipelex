"""Command to verify that every configuration surface has accounted for its schema changes.

This is the golden half of the migration gate, and it asks two questions of every surface. Coverage
reads the checked-in ledgers and golden chains, recomputes each surface's fingerprint, and fails
when a schema change would leave a user's file broken with nothing written down about how to repair
it. The transform goldens then *do* the migration each entry describes, from one frozen reference
document to the next, and fail when what the operations produce is not the shape the new version
actually has.

Both live in `make check` and deliberately **not** in `make agent-check`: they are golden checks,
and in the loop agents run constantly a fail-regenerate-fail cycle with no single right answer is
how a gate goes permanently green while catching nothing.
"""

import sys
from collections.abc import Sequence

from rich.markup import escape

from pipelex.migration.coverage import CoverageIssue, check_registry
from pipelex.migration.exceptions import MigrationError
from pipelex.migration.surfaces import build_config_surface_registry, packaged_migration_dir
from pipelex.migration.transform_check import TransformIssue, check_transforms
from pipelex.runtime_hub import get_console


def check_migration_schemas_cmd(*, quiet: bool = False) -> None:
    """Verify that every configuration surface's schema changes are accounted for.

    Args:
        quiet: If True, keep the success output to a single line (for Make targets / CI). Quiet
            only trims success output: a failure always lists every issue, because the Make
            targets invoke the check quietly and a red gate has to say what to do.
    """
    console = get_console()

    if not quiet:
        console.print()
        console.print("[bold]Checking migration schema coverage...[/bold]")
        console.print()

    registry = build_config_surface_registry()
    migration_dir = packaged_migration_dir()
    issues: list[CoverageIssue | TransformIssue] = []
    try:
        issues.extend(check_registry(registry=registry, migration_dir=migration_dir))
        issues.extend(check_transforms(registry=registry, migration_dir=migration_dir))
    except MigrationError as exc:
        # An error is always loud — quiet only trims success output, never failures.
        console.print(f"[red]✗ Migration schema check: FAILED[/red] - {escape(str(exc))}")
        sys.exit(1)

    if not issues:
        surface_count = len(registry.surfaces)
        console.print(f"[green]✓ Migration schema check: PASSED[/green] - {surface_count} surfaces accounted for")
        return

    _print_issues(issues=issues)
    sys.exit(1)


def _print_issues(*, issues: Sequence[CoverageIssue | TransformIssue]) -> None:
    console = get_console()
    console.print(f"[red]✗ Migration schema check: FAILED[/red] - {len(issues)} issues")
    console.print()
    for issue in issues:
        # Messages quote ledger text and path lists, both of which can look like Rich markup.
        console.print(f"  [yellow]{escape(issue.surface_id)}[/yellow] [dim]({issue.kind})[/dim]")
        console.print(f"    {escape(issue.message)}")
        console.print()
