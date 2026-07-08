from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from posthog import tag
from rich.markup import escape

from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import (
    ErrorContext,
    display_validation_error_items,
    handle_model_availability_error,
    handle_model_choice_error,
    print_traceback_if_requested,
)
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.hub import get_console, get_telemetry_manager
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import Pipelex
from pipelex.pipeline.fixes.fix_loop import fix_bundle_file
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventProperty
from pipelex.tools.misc.package_utils import get_package_version
from pipelex.urls import URLs

if TYPE_CHECKING:
    from rich.console import Console

    from pipelex.pipeline.fixes.fix_loop import FixBundleResult
    from pipelex.suggested_fix import SuggestedFix

COMMAND = "fix"


def _print_applied_fixes(console: Console, *, fixes: list[SuggestedFix], bundle_path: Path) -> None:
    """Numbered list naming every change made — descriptions only, ops stay machine-facing."""
    entry_resolved = bundle_path.resolve()
    for fix_index, fix in enumerate(fixes, 1):
        line = f"  {fix_index}. {escape(fix.description)} [dim]({escape(fix.fix_code)})[/dim]"
        if fix.source is not None and Path(fix.source).resolve() != entry_resolved:
            line += f" [dim]— {escape(fix.source)}[/dim]"
        console.print(line)


def _print_work_done(console: Console, *, result: FixBundleResult, bundle_path: Path) -> None:
    """The applied fixes, files written, and iteration count of one fix run."""
    console.print("[bold cyan]Applied fixes:[/bold cyan]")
    _print_applied_fixes(console, fixes=result.fixes_applied, bundle_path=bundle_path)
    if result.files_written:
        console.print("\n[bold cyan]Files written:[/bold cyan]")
        for file_path in result.files_written:
            console.print(f"  - {escape(file_path)}")
    console.print(f"\n[bold cyan]Iterations:[/bold cyan] {result.iterations}")


def _render_fix_result(console: Console, *, result: FixBundleResult, bundle_path: Path, allow_signatures: bool) -> None:
    """Render a ``FixBundleResult`` for humans and exit per the 0/1 verdict policy.

    Valid (fixed or already valid) exits 0; valid-but-not-runnable without
    ``--allow-signatures`` and still-invalid exit 1. No-verdict outcomes never reach here —
    they are handled by :func:`execute_fix`'s exception arms (exit 2).
    """
    if result.is_valid:
        console.print()
        if result.fixes_applied:
            console.print("[bold green]✅ Bundle fixed — valid[/bold green]\n")
        else:
            console.print("[bold green]✅ Bundle already valid[/bold green]\n")
        console.print(f"[bold cyan]Bundle:[/bold cyan] [yellow]{escape(str(bundle_path))}[/yellow]")
        if result.fixes_applied:
            console.print()
            _print_work_done(console, result=result, bundle_path=bundle_path)
        console.print()

        if result.pending_signatures:
            pending = ", ".join(result.pending_signatures)
            if allow_signatures:
                console.print(f"[dim]Pending PipeSignature placeholder(s): {escape(pending)}[/dim]\n")
            else:
                # Mirrors the validate/agent-fix runnability gate: valid is not runnable.
                console.print(
                    f"[bold red]Bundle is valid but NOT yet runnable — unimplemented PipeSignature placeholder(s): {escape(pending)}[/bold red]"
                )
                console.print("[bold green]💡 Tip:[/bold green] Implement them, or re-run with --allow-signatures to accept placeholders.\n")
                raise typer.Exit(1)
        return

    console.print()
    console.print("[bold red]❌ Bundle could not be fully fixed[/bold red]\n")
    console.print(f"[bold cyan]Bundle:[/bold cyan] [yellow]{escape(str(bundle_path))}[/yellow]\n")

    # Partial progress is normal: name what WAS applied before the remaining errors.
    if result.fixes_applied:
        _print_work_done(console, result=result, bundle_path=bundle_path)
        console.print()

    if result.bail_reason:
        console.print(f"[bold yellow]Stopped:[/bold yellow] {escape(result.bail_reason)}\n")

    if result.remaining_errors:
        console.print("[bold cyan]Remaining errors:[/bold cyan]\n")
        display_validation_error_items(console, items=result.remaining_errors)

    console.print(
        "[bold green]💡 Tip:[/bold green] Review the remaining errors above — they have no deterministic safe fix, so they need a manual edit."
    )
    console.print(f"[dim]Learn more: {URLs.documentation}[/dim]")
    console.print(f"[dim]Join our Discord for help: {URLs.discord}[/dim]\n")
    raise typer.Exit(1)


def execute_fix(
    bundle_path: Path,
    *,
    library_dirs: list[Path] | None,
    allow_signatures: bool = False,
    max_iterations: int | None = None,
    select_codes: tuple[str, ...] | None = None,
    ignore_codes: tuple[str, ...] | None = None,
) -> None:
    """Synchronous entry point wrapping the fix loop with Pipelex setup/teardown.

    Boots with the same profile ``validate`` uses (no inference, real model specs), runs
    ``fix_bundle_file``, renders the verdict for humans, and tears down in ``finally``.
    Exit codes are presentation: 0 = valid, 1 = negative verdict (still invalid, or valid but
    not runnable without ``--allow-signatures``), 2 = no verdict (bad target, boot failure,
    unexpected exception).
    """
    make_pipelex_for_cli(context=ErrorContext.FIX, needs_inference=False, needs_model_specs=True)

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
            tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} bundle")

            result = asyncio.run(
                fix_bundle_file(
                    bundle_path,
                    library_dirs=library_dirs,
                    allow_signatures=allow_signatures,
                    max_iterations=max_iterations,
                    select_codes=select_codes,
                    ignore_codes=ignore_codes,
                )
            )
            _render_fix_result(get_console(), result=result, bundle_path=bundle_path, allow_signatures=allow_signatures)
    except FileNotFoundError as exc:
        print_traceback_if_requested(get_console())
        typer.secho(f"Failed to fix: bundle file not found: '{bundle_path}'", fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc
    except PipeOperatorModelChoiceError as exc:
        handle_model_choice_error(exc, context=ErrorContext.FIX, exit_code=2)
    except PipeOperatorModelAvailabilityError as exc:
        handle_model_availability_error(exc, context=ErrorContext.FIX, exit_code=2)
    except typer.Exit:
        raise
    except Exception as exc:
        # Human CLI command boundary: an unexpected failure produced no verdict — exit 2.
        print_traceback_if_requested(get_console())
        typer.secho(f"Failed to fix: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc
    finally:
        Pipelex.teardown_if_needed()
