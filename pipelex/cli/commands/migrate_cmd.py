"""``pipelex migrate`` — bring the configuration files on this machine up to the current schema.

The command a user is sent to when their configuration no longer matches the models the installed
pipelex carries. It walks the global `~/.pipelex/` and the project `.pipelex/`, replays each
surface's shipped ledger over every file it claims there, and rewrites the files that changed —
each backed up first.

**This command must run when nothing else does.** A broken configuration is the reason to reach for
it, so it needs the ledger, the applier and the filesystem, and nothing else: no boot, no model
deck, no credentials, no network. That is a property to preserve, not an accident — it is pinned by
a test that hands the command a configuration that cannot load.

Two passes, and they are not the same pass twice for the sake of it. The first is a dry run whose
report is what the user is shown and asked about; the second is the one that writes. Under
always-replay the two agree, and where they do not — because the user edited a file in between, or
another process did — the second is the authoritative one and the transaction refuses rather than
writing over work it never saw.

See `docs/migration-ledger.md`.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm

from pipelex.migration.run import config_directories_to_migrate, migrate_config_directories
from pipelex.runtime_hub import get_console
from pipelex.suggested_fix import WILDCARD_SEGMENT, DeleteKeyOp, DeleteTableOp, MoveKeyOp, RemapValueOp, RenameTableKeyOp

if TYPE_CHECKING:
    from pathlib import Path

    from pipelex.migration.plan import BlockedEntry, MigrationReport, UnexplainedPath
    from pipelex.suggested_fix import MigrationOp

_NOTHING_TO_DO = "Every configuration file on this machine is at the current schema."


def migrate_cmd(*, dry_run: bool = False, yes: bool = False) -> None:
    """Migrate the configuration files in the global and project configuration directories.

    Args:
        dry_run: Report what would change and write nothing.
        yes: Apply without the interactive confirmation.
    """
    console = get_console()
    if dry_run and yes:
        console.print("[red]✗[/red] --dry-run and --yes contradict each other: one refuses to write, the other authorizes it.")
        sys.exit(2)

    config_dirs = config_directories_to_migrate()
    if not config_dirs:
        console.print()
        console.print("[yellow]![/yellow] No configuration directory found. Run [cyan]pipelex init[/cyan] to create one.")
        console.print()
        return

    console.print()
    console.print("[bold]Configuration migration[/bold]")
    for directory in config_dirs:
        console.print(f"  [dim]{escape(str(directory))}[/dim]")

    rehearsal = migrate_config_directories(config_dirs=config_dirs, dry_run=True)
    _print_report(report=rehearsal, wrote=False)

    if rehearsal.is_clean:
        console.print(_panel(message=_NOTHING_TO_DO, style="green"))
        console.print()
        return

    if dry_run:
        console.print("[dim]Dry run — nothing was written.[/dim]")
        console.print()
        _exit_on_attention(report=rehearsal)
        return

    if not rehearsal.changed_plans:
        # Nothing this tool can do, and something for the user to do. Asking "apply these changes?"
        # when there are none to apply is a prompt with one honest answer.
        console.print(_panel(message="Nothing here can be migrated automatically — see the notes above.", style="yellow"))
        console.print()
        _exit_on_attention(report=rehearsal)
        return

    if not yes and not Confirm.ask(f"[bold]Migrate {len(rehearsal.changed_plans)} file(s)?[/bold]", default=True):
        console.print("[yellow]Migration cancelled — nothing was written.[/yellow]")
        console.print()
        return

    applied = apply_pending_migrations(config_dirs=config_dirs)
    written = len(applied.written_plans)
    if written:
        console.print(_panel(message=f"Migrated {written} file(s); a copy of each original is beside it.", style="green"))
    else:
        console.print(_panel(message="Nothing was written.", style="yellow"))
    console.print()
    _exit_on_attention(report=applied)


def apply_pending_migrations(*, config_dirs: list[Path]) -> MigrationReport:
    """Write what a migration would write, render what it did, and hand the report back.

    The second of this command's two passes on its own, with no exit code attached to it. A
    caller that has already shown the user a dry run and asked its own question reaches the same
    code rather than reimplementing it — `pipelex doctor --fix` is that caller, and its
    pending-migrations row *is* the dry run. Calling `migrate_cmd` there instead would end the
    doctor's own run: the command exits the process when something is left for a person, and the
    doctor still has rows to render and an exit code of its own to set.
    """
    applied = migrate_config_directories(config_dirs=config_dirs, dry_run=False)
    _print_written(report=applied)
    return applied


def _exit_on_attention(*, report: MigrationReport) -> None:
    """Leave a non-zero exit code behind when something needs a human.

    The exit code is presentation, not the verdict — `pipelex-agent migrate` carries the same
    verdict as a structured field. What it means here is narrow and worth keeping narrow: *this
    run left something a person has to look at*, never *this run failed*.
    """
    if report.needs_attention:
        sys.exit(1)


def _print_report(*, report: MigrationReport, wrote: bool) -> None:
    console = get_console()
    for plan in report.plans:
        if plan.is_clean:
            continue
        console.print()
        console.print(f"  [cyan]{escape(str(plan.file_path))}[/cyan] [dim]({plan.surface_id})[/dim]")
        if plan.blocked_reason is not None:
            console.print(f"    [red]✗[/red] {plan.blocked_reason}: {escape(plan.blocked_detail or '')}")
            continue
        for step in plan.steps:
            marker = "[green]✓[/green]" if wrote else "[green]→[/green]"
            console.print(f"    {marker} [dim]v{step.to_schema_version}[/dim] {escape(step.title)}")
            for op in step.applied_ops:
                console.print(f"        [dim]{escape(describe_op(op=op))}[/dim]")
        for blocked in plan.blocked:
            _print_blocked_entry(blocked=blocked)
        for unexplained in plan.unexplained:
            _print_unexplained(unexplained=unexplained)
    console.print()


def _print_written(*, report: MigrationReport) -> None:
    _print_report(report=report, wrote=True)
    console = get_console()
    for plan in report.written_plans:
        if plan.backup_path is not None:
            console.print(f"  [dim]backup: {escape(str(plan.backup_path))}[/dim]")


def _print_blocked_entry(*, blocked: BlockedEntry) -> None:
    console = get_console()
    console.print(f"    [yellow]![/yellow] [dim]v{blocked.to_schema_version}[/dim] {blocked.reason}: {escape(blocked.detail)}")
    for op in blocked.applied_ops:
        console.print(f"        [dim]applied: {escape(describe_op(op=op))}[/dim]")
    if blocked.guidance:
        for line in blocked.guidance.splitlines():
            console.print(f"        {escape(line)}")


def _print_unexplained(*, unexplained: UnexplainedPath) -> None:
    get_console().print(f"    [yellow]?[/yellow] [cyan]{escape(unexplained.path)}[/cyan] — {escape(unexplained.note)}")


def describe_op(*, op: MigrationOp) -> str:
    """One operation in words, from ledger-supplied material only.

    Every part of this sentence comes from the ledger — the operation's kind, its paths, and the
    spellings a remap names. Nothing read from the user's file appears, which is the same rule the
    plan models hold themselves to and the reason this is a rendering of the *operation* rather
    than a rendering of what the file used to say.
    """
    where = _table_in_words(table_path=op.table_path)
    match op:
        case DeleteKeyOp():
            return f"deleted '{op.key}' from {where}"
        case DeleteTableOp():
            return f"deleted the table {where}"
        case RenameTableKeyOp():
            return f"renamed '{op.key}' to '{op.new_key}' in {where}"
        case MoveKeyOp():
            return f"moved '{op.key}' from {where} to '{op.new_key}' in {_table_in_words(table_path=op.new_table_path)}"
        case RemapValueOp():
            renamings = ", ".join(f"'{before}' -> '{after}'" for before, after in sorted(op.mapping.items()))
            # `*` is the one key a remap may carry that names no key of its own: it means each key
            # of the addressed table, whose spellings only the user's document knows.
            subject = "every value" if op.key == WILDCARD_SEGMENT else f"the value of '{op.key}'"
            return f"rewrote {subject} in {where}: {renamings}"


def _table_in_words(*, table_path: list[str]) -> str:
    """A table path as a report names it, the empty one included."""
    return f"'{'.'.join(table_path)}'" if table_path else "the document root"


def _panel(*, message: str, style: str) -> Panel:
    return Panel(message, border_style=style, expand=False)
