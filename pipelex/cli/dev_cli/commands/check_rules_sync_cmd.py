"""Command to verify installed agent rules match kit templates."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from rich.panel import Panel

from pipelex.hub import get_console
from pipelex.kit.index_loader import load_index
from pipelex.kit.markers import find_span, replace_span, wrap
from pipelex.kit.single_file_agent_rules import build_merged_rules, insert_block_with_markers, unified_diff


def check_rules_sync_cmd(show_diff: bool = True, quiet: bool = False) -> None:
    """Verify that installed agent rules match kit templates.

    Args:
        show_diff: If True, display the differences when found
        quiet: If True, output only a single validation line (for use in Make targets)
    """
    console = get_console()
    kit_index = load_index()
    agent_set = "coding_standards"

    missing_targets: list[Path] = []
    mismatches: list[tuple[Path, str, str]] = []

    for target in kit_index.agent_rules.targets.values():
        # Check if this target has its own set override for the agent_set
        target_file_list: list[str] | None = None
        if target.sets and agent_set in target.sets:
            target_file_list = target.sets[agent_set]

        # Build merged rules for this specific target (with override if applicable)
        merged_rules = build_merged_rules(kit_index, agent_set=agent_set, file_list=target_file_list)

        target_path = Path(target.path)

        if not target_path.exists():
            missing_targets.append(target_path)
            continue

        current_content = target_path.read_text(encoding="utf-8")
        span = find_span(current_content, target.marker_begin, target.marker_end)

        if span:
            before_markers = current_content[: span[0]]
            after_markers = current_content[span[1] :]
            outside_content = before_markers + after_markers

            has_h1_outside = bool(re.search(r"^#\s+.+$", outside_content, flags=re.MULTILINE))

            if target.heading_1 and not has_h1_outside:
                content_with_heading = f"{target.heading_1}\n\n{merged_rules}"
                wrapped_block = wrap(target.marker_begin, target.marker_end, content_with_heading)
            else:
                wrapped_block = wrap(target.marker_begin, target.marker_end, merged_rules)

            expected_content = replace_span(current_content, span, wrapped_block)
        else:
            expected_content = insert_block_with_markers(
                current_content,
                merged_rules,
                target.heading_1,
                (target.marker_begin, target.marker_end),
            )

        if current_content != expected_content:
            mismatches.append((target_path, current_content, expected_content))

    if not missing_targets and not mismatches:
        if quiet:
            console.print("[green]✓ Agent rules sync check: PASSED[/green]")
        else:
            console.print()
            console.print("[bold]Checking agent rules synchronization...[/bold]")
            console.print("  Set: [cyan]coding_standards[/cyan]")
            console.print()
            success_panel = Panel(
                "[green]✓[/green] Agent rules are in sync!\n\n[dim]Installed targets match templates from pipelex/kit/agent_rules.[/dim]",
                title="[bold green]Agent Rules Sync Check: PASSED[/bold green]",
                border_style="green",
                padding=(1, 2),
            )
            console.print(success_panel)
            console.print()
    else:
        console.print()
        console.print("[bold]Checking agent rules synchronization...[/bold]")
        console.print("  Set: [cyan]coding_standards[/cyan]")
        console.print()
        error_panel = Panel(
            (
                "[red]✗[/red] Agent rules are [bold]NOT[/bold] in sync!\n\n"
                "[dim]Installed targets differ from templates in pipelex/kit/agent_rules.[/dim]"
            ),
            title="[bold red]Agent Rules Sync Check: FAILED[/bold red]",
            border_style="red",
            padding=(1, 2),
        )
        console.print(error_panel)
        console.print()

        if missing_targets:
            console.print("[bold yellow]Missing targets:[/bold yellow]")
            for missing_path in missing_targets:
                console.print(f"  • [cyan]{missing_path}[/cyan]")
            console.print()

        if mismatches:
            console.print("[bold yellow]Mismatched targets:[/bold yellow]")
            for mismatched_path, current_content, expected_content in mismatches:
                console.print(f"  • [cyan]{mismatched_path}[/cyan]")
                if show_diff:
                    diff_output = unified_diff(current_content, expected_content, str(mismatched_path))
                    if diff_output:
                        console.print()
                        console.print(diff_output)
                        console.print()

        console.print("[bold yellow]Recommended Actions:[/bold yellow]")
        console.print("  • Run [cyan]make rules[/cyan] to sync agent rules")
        console.print()
        sys.exit(1)
