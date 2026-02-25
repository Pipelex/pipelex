"""Command to verify installed agent rules match kit templates."""

from __future__ import annotations

import sys
from pathlib import Path

from rich.markup import escape
from rich.panel import Panel

from pipelex.hub import get_console
from pipelex.kit.index_loader import load_index
from pipelex.kit.single_file_agent_rules import build_merged_rules, unified_diff
from pipelex.system.configuration.configs import AgentTarget
from pipelex.tools.misc.toml_utils import load_toml_from_path


def _get_preferred_target_from_toml() -> AgentTarget:
    """Read preferred_agent_target directly from pipelex.toml without initializing Pipelex."""
    pipelex_toml = Path("pipelex/pipelex.toml")
    if not pipelex_toml.exists():
        return AgentTarget.CLAUDE  # Default fallback

    config = load_toml_from_path(str(pipelex_toml))

    try:
        target_str = config["pipelex"]["kit_config"]["preferred_agent_target"]
        return AgentTarget(target_str)
    except (KeyError, ValueError):
        return AgentTarget.CLAUDE  # Default fallback


def check_rules_sync_cmd(show_diff: bool = True, quiet: bool = False) -> None:
    """Verify that installed agent rules match kit templates.

    Args:
        show_diff: If True, display the differences when found
        quiet: If True, output only a single validation line (for use in Make targets)
    """
    console = get_console()
    kit_index = load_index()
    agent_set = "all"

    # Get preferred agent target from config (without initializing Pipelex)
    preferred_target = _get_preferred_target_from_toml()

    # Only check single-file targets (not Cursor)
    match preferred_target:
        case AgentTarget.CURSOR:
            # Cursor rules use a different mechanism, skip for now
            if quiet:
                console.print("[green]✓ Agent rules sync check: PASSED[/green] (Cursor target - skipped)")
            else:
                console.print("[dim]Cursor target selected - sync check not applicable[/dim]")
            return
        case AgentTarget.AGENTS | AgentTarget.CLAUDE:
            target_key = preferred_target
            if target_key not in kit_index.agent_rules.targets:
                console.print(f"[red]Target '{escape(preferred_target)}' not found in index.toml[/red]")
                sys.exit(1)
            targets_to_check = {target_key: kit_index.agent_rules.targets[target_key]}

    missing_targets: list[Path] = []
    mismatches: list[tuple[Path, str, str]] = []

    for target in targets_to_check.values():
        # Check if this target has its own set override for the agent_set
        target_file_list: list[str] | None = None
        if target.sets and agent_set in target.sets:
            target_file_list = target.sets[agent_set]

        # Build merged rules for this specific target (with override if applicable)
        merged_rules = build_merged_rules(kit_index, agent_set=agent_set, file_list=target_file_list)

        # Expected content is heading + merged rules
        expected_content = f"# Pipelex Coding Rules\n\n{merged_rules}"

        target_path = Path(target.path)

        if not target_path.exists():
            missing_targets.append(target_path)
            continue

        try:
            current_content = target_path.read_text(encoding="utf-8")
        except OSError:
            # Handle race condition where file is deleted after exists() check
            # or other filesystem errors (permissions, etc.)
            missing_targets.append(target_path)
            continue

        if current_content != expected_content:
            mismatches.append((target_path, current_content, expected_content))

    if not missing_targets and not mismatches:
        if quiet:
            console.print("[green]✓ Agent rules sync check: PASSED[/green]")
        else:
            console.print()
            console.print("[bold]Checking agent rules synchronization...[/bold]")
            console.print("  Set: [cyan]all[/cyan]")
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
        console.print("  Set: [cyan]all[/cyan]")
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
