from __future__ import annotations

import asyncio
import difflib
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from posthog import tag
from rich.markup import escape

from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.commands.fix._diff_sandbox import mirror_bundle_for_preview
from pipelex.cli.error_handlers import (
    ErrorContext,
    display_validation_error_items,
    handle_model_availability_error,
    handle_model_choice_error,
    print_traceback_if_requested,
)
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import Pipelex
from pipelex.pipeline.fixes.fix_loop import fix_bundle_file
from pipelex.runtime_hub import get_console, get_telemetry_manager
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventProperty
from pipelex.tools.misc.package_utils import get_package_version
from pipelex.urls import URLs

if TYPE_CHECKING:
    from rich.console import Console

    from pipelex.base_exceptions import ValidationErrorItem
    from pipelex.cli.commands.fix._diff_sandbox import PreviewSandbox
    from pipelex.pipeline.fixes.fix_loop import FixBundleResult
    from pipelex.suggested_fix import SuggestedFix

COMMAND = "fix"


def _print_applied_fixes(*, console: Console, fixes: list[SuggestedFix], bundle_path: Path) -> None:
    """Numbered list naming every change made — descriptions only, ops stay machine-facing."""
    entry_resolved = bundle_path.resolve()
    for fix_index, fix in enumerate(fixes, 1):
        line = f"  {fix_index}. {escape(fix.description)} [dim]({escape(fix.fix_code)})[/dim]"
        if fix.source is not None and Path(fix.source).resolve() != entry_resolved:
            line += f" [dim]— {escape(fix.source)}[/dim]"
        console.print(line)


def _print_work_done(*, console: Console, result: FixBundleResult, bundle_path: Path, preview: bool = False) -> None:
    """The applied fixes, files written, and iteration count of one fix run."""
    console.print(f"[bold cyan]{'Fixes that would be applied:' if preview else 'Applied fixes:'}[/bold cyan]")
    _print_applied_fixes(console=console, fixes=result.fixes_applied, bundle_path=bundle_path)
    if result.files_written:
        console.print(f"\n[bold cyan]{'Files that would be written:' if preview else 'Files written:'}[/bold cyan]")
        for file_path in result.files_written:
            console.print(f"  - {escape(file_path)}")
    console.print(f"\n[bold cyan]Iterations:[/bold cyan] {result.iterations}")


def _render_fix_result(*, console: Console, result: FixBundleResult, bundle_path: Path, allow_signatures: bool, preview: bool = False) -> None:
    """Render a ``FixBundleResult`` for humans and exit per the 0/1 verdict policy.

    Valid (fixed or already valid) exits 0; valid-but-not-runnable without
    ``--allow-signatures`` and still-invalid exit 1. No-verdict outcomes never reach here —
    they are handled by :func:`execute_fix`'s exception arms (exit 2). ``preview`` swaps the
    labels to would-be phrasing (``--diff`` writes nothing) while keeping the same verdicts
    and exit codes, so ``--diff`` answers "would it converge?".
    """
    if result.is_valid:
        console.print()
        if result.fixes_applied:
            if preview:
                console.print("[bold green]✅ Fix preview — these fixes would make the bundle valid[/bold green]\n")
            else:
                console.print("[bold green]✅ Bundle fixed — valid[/bold green]\n")
        else:
            console.print("[bold green]✅ Bundle already valid[/bold green]\n")
        console.print(f"[bold cyan]Bundle:[/bold cyan] [yellow]{escape(str(bundle_path))}[/yellow]")
        if result.fixes_applied:
            console.print()
            _print_work_done(console=console, result=result, bundle_path=bundle_path, preview=preview)
        console.print()

        if result.pending_signatures:
            pending = ", ".join(result.pending_signatures)
            if allow_signatures:
                console.print(f"[dim]Pending PipeSignature placeholder(s): {escape(pending)}[/dim]\n")
            else:
                # Mirrors the validate/agent-fix runnability gate: valid is not runnable. Under
                # --diff nothing was written, so the phrasing stays conditional (would-be).
                if preview:
                    console.print(
                        f"[bold red]Fix preview — the bundle would be valid but still NOT runnable: "
                        f"unimplemented PipeSignature placeholder(s): {escape(pending)}[/bold red]"
                    )
                else:
                    console.print(
                        f"[bold red]Bundle is valid but NOT yet runnable — unimplemented PipeSignature placeholder(s): {escape(pending)}[/bold red]"
                    )
                console.print("[bold green]💡 Tip:[/bold green] Implement them, or re-run with --allow-signatures to accept placeholders.\n")
                raise typer.Exit(1)
        return

    console.print()
    if preview:
        console.print("[bold red]❌ Fix preview — the bundle would still be invalid[/bold red]\n")
    else:
        console.print("[bold red]❌ Bundle could not be fully fixed[/bold red]\n")
    console.print(f"[bold cyan]Bundle:[/bold cyan] [yellow]{escape(str(bundle_path))}[/yellow]\n")

    # Partial progress is normal: name what WAS applied before the remaining errors.
    if result.fixes_applied:
        _print_work_done(console=console, result=result, bundle_path=bundle_path, preview=preview)
        console.print()

    if result.bail_reason:
        console.print(f"[bold yellow]Stopped:[/bold yellow] {escape(result.bail_reason)}\n")

    if result.remaining_errors:
        console.print("[bold cyan]Remaining errors:[/bold cyan]\n")
        display_validation_error_items(console=console, items=result.remaining_errors)

    # A remaining error can still carry a 💡 suggested-fix line — dropped by --select/--ignore,
    # left outside the write scope, or unconverged when the loop bailed. Claiming "no safe fix"
    # there contradicts the line just printed, so only say it when nothing fixable remains.
    if any(item.suggested_fix is not None for item in result.remaining_errors):
        console.print(
            "[bold green]💡 Tip:[/bold green] Some remaining errors above still show a suggested fix that was not applied — "
            "they were skipped by --select/--ignore, fell outside the write scope, or the loop stopped early (see the reason above). "
            "Adjust those flags (or pass -L) and re-run, or fix the rest manually."
        )
    else:
        console.print(
            "[bold green]💡 Tip:[/bold green] Review the remaining errors above — they have no deterministic safe fix, so they need a manual edit."
        )
    console.print(f"[dim]Learn more: {URLs.documentation}[/dim]")
    console.print(f"[dim]Join our Discord for help: {URLs.discord}[/dim]\n")
    raise typer.Exit(1)


def _remap_validation_error_to_original(item: ValidationErrorItem, *, sandbox: PreviewSandbox) -> ValidationErrorItem:
    """Remap only the diagnostic values proven to carry mirrored filesystem paths."""
    updates: dict[str, object] = {}
    source = item.source
    remapped_source: str | None = None
    if source is not None:
        remapped_source = sandbox.to_original(source)
        updates["source"] = remapped_source
        if source and remapped_source != source and source in item.message:
            updates["message"] = item.message.replace(source, remapped_source)

    field_path = item.field_path
    if field_path is not None:
        if source is not None and field_path == source:
            updates["field_path"] = remapped_source
        elif Path(field_path).is_absolute():
            resolved_field_path = str(Path(field_path).resolve())
            remapped_field_path = sandbox.to_original(field_path)
            if remapped_field_path != resolved_field_path:
                updates["field_path"] = remapped_field_path

    return item.model_copy(update=updates) if updates else item


def _remap_result_to_originals(result: FixBundleResult, *, sandbox: PreviewSandbox) -> FixBundleResult:
    """Rebuild a sandbox-run result with every file path mapped back to the original it mirrors."""
    return result.model_copy(
        update={
            "fixes_applied": [
                fix.model_copy(update={"source": sandbox.to_original(fix.source)}) if fix.source is not None else fix for fix in result.fixes_applied
            ],
            "files_written": [sandbox.to_original(file_path) for file_path in result.files_written],
            "remaining_errors": [_remap_validation_error_to_original(item, sandbox=sandbox) for item in result.remaining_errors],
        }
    )


def _print_preview_diffs(*, console: Console, result: FixBundleResult, sandbox: PreviewSandbox) -> None:
    """Unified diff (original vs sandbox copy) per file the preview run wrote.

    Must run while the sandbox still exists — it reads the mutated copies off disk.
    """
    console.print("\n[bold cyan]Preview (--diff): no files were written. Proposed changes:[/bold cyan]\n")
    for written_path in result.files_written:
        original_path = Path(sandbox.to_original(written_path))
        original_lines = original_path.read_text(encoding="utf-8").splitlines()
        updated_lines = Path(written_path).read_text(encoding="utf-8").splitlines()
        diff_lines = difflib.unified_diff(
            original_lines,
            updated_lines,
            fromfile=str(original_path),
            tofile=f"{original_path} (fixed)",
            lineterm="",
        )
        for diff_line in diff_lines:
            if diff_line.startswith(("+++", "---")):
                console.print(f"[bold]{escape(diff_line)}[/bold]")
            elif diff_line.startswith("@@"):
                console.print(f"[cyan]{escape(diff_line)}[/cyan]")
            elif diff_line.startswith("+"):
                console.print(f"[green]{escape(diff_line)}[/green]")
            elif diff_line.startswith("-"):
                console.print(f"[red]{escape(diff_line)}[/red]")
            else:
                console.print(escape(diff_line))
        console.print()


def _run_fix_preview(
    *,
    console: Console,
    bundle_path: Path,
    library_dirs: list[Path] | None,
    allow_signatures: bool,
    max_iterations: int | None,
    select_codes: tuple[str, ...] | None,
    ignore_codes: tuple[str, ...] | None,
) -> None:
    """Run the real loop against a temp-copy sandbox (D5.6), render diffs, keep the verdict."""
    with tempfile.TemporaryDirectory(prefix="pipelex-fix-preview-") as sandbox_root:
        sandbox = mirror_bundle_for_preview(bundle_path, library_dirs=library_dirs, sandbox_root=Path(sandbox_root))
        result = asyncio.run(
            fix_bundle_file(
                sandbox.entry_path,
                library_dirs=sandbox.library_dirs,
                writable_library_dirs=sandbox.writable_library_dirs,
                allow_signatures=allow_signatures,
                max_iterations=max_iterations,
                select_codes=select_codes,
                ignore_codes=ignore_codes,
            )
        )
        if result.files_written:
            _print_preview_diffs(console=console, result=result, sandbox=sandbox)
        display_result = _remap_result_to_originals(result, sandbox=sandbox)
        _render_fix_result(console=console, result=display_result, bundle_path=bundle_path, allow_signatures=allow_signatures, preview=True)


def execute_fix(
    bundle_path: Path,
    *,
    library_dirs: list[Path] | None,
    allow_signatures: bool = False,
    max_iterations: int | None = None,
    select_codes: tuple[str, ...] | None = None,
    ignore_codes: tuple[str, ...] | None = None,
    diff: bool = False,
) -> None:
    """Synchronous entry point wrapping the fix loop with Pipelex setup/teardown.

    Boots with the same profile ``validate`` uses (no inference, real model specs), runs
    ``fix_bundle_file``, renders the verdict for humans, and tears down in ``finally``.
    Exit codes are presentation: 0 = valid, 1 = negative verdict (still invalid, or valid but
    not runnable without ``--allow-signatures``), 2 = no verdict (bad target, boot failure,
    unexpected exception). ``diff`` previews instead of writing: the same loop runs against a
    temp-copy sandbox and a unified diff is rendered per would-be-written file, with the same
    verdict semantics.
    """
    try:
        make_pipelex_for_cli(context=ErrorContext.FIX, needs_inference=False, needs_model_specs=True)
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
            tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} bundle")

            if diff:
                _run_fix_preview(
                    console=get_console(),
                    bundle_path=bundle_path,
                    library_dirs=library_dirs,
                    allow_signatures=allow_signatures,
                    max_iterations=max_iterations,
                    select_codes=select_codes,
                    ignore_codes=ignore_codes,
                )
                return

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
            _render_fix_result(console=get_console(), result=result, bundle_path=bundle_path, allow_signatures=allow_signatures)
    except FileNotFoundError as exc:
        print_traceback_if_requested(console=get_console())
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
        print_traceback_if_requested(console=get_console())
        typer.secho(f"Failed to fix: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc
    finally:
        Pipelex.teardown_if_needed()
