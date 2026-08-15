"""Command to verify installed agent rules match kit templates."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from rich.markup import escape
from rich.panel import Panel

from pipelex.kit.index_loader import load_index
from pipelex.kit.single_file_agent_rules import build_merged_rules, unified_diff
from pipelex.runtime_hub import get_console
from pipelex.system.configuration.configs import AgentTarget
from pipelex.tools.misc.toml_utils import load_toml_from_path

if TYPE_CHECKING:
    from pipelex.kit.index_models import Target

_DEFAULT_TARGETS: list[AgentTarget] = [AgentTarget.CLAUDE, AgentTarget.AGENTS]


def _get_preferred_targets_from_toml() -> list[AgentTarget]:
    """Read preferred_agent_targets directly from pipelex.toml without initializing Pipelex."""
    pipelex_toml = Path("pipelex/pipelex.toml")
    if not pipelex_toml.exists():
        return _DEFAULT_TARGETS

    config = load_toml_from_path(str(pipelex_toml))

    try:
        raw_targets = config["kit"]["preferred_agent_targets"]
        parsed_targets = [AgentTarget(item) for item in raw_targets]
    except (KeyError, ValueError, TypeError):
        return _DEFAULT_TARGETS
    return parsed_targets or _DEFAULT_TARGETS


def check_rules_sync_cmd(*, show_diff: bool = True, quiet: bool = False) -> None:
    """Verify that installed agent rules match kit templates.

    Args:
        show_diff: If True, display the differences when found
        quiet: If True, output only a single validation line (for use in Make targets)
    """
    console = get_console()
    kit_index = load_index()
    agent_set = "all"

    # Get preferred agent targets from config (without initializing Pipelex)
    preferred_targets = _get_preferred_targets_from_toml()

    # Cursor is exclusive of the single-file targets per config validator.
    if preferred_targets == [AgentTarget.CURSOR]:
        if quiet:
            console.print("[green]✓ Agent rules sync check: PASSED[/green] (Cursor target - skipped)")
        else:
            console.print("[dim]Cursor target selected - sync check not applicable[/dim]")
        return
    if AgentTarget.CURSOR in preferred_targets:
        console.print("[red]Invalid config: preferred_agent_targets cannot mix 'cursor' with other targets[/red]")
        sys.exit(1)

    targets_to_check: dict[str, Target] = {}
    for target_key in preferred_targets:
        if target_key not in kit_index.agent_rules.targets:
            console.print(f"[red]Target '{escape(target_key)}' not found in index.toml[/red]")
            sys.exit(1)
        targets_to_check[target_key] = kit_index.agent_rules.targets[target_key]

    missing_targets: list[Path] = []
    mismatches: list[tuple[Path, str, str]] = []

    for target in targets_to_check.values():
        # Check if this target has its own set override for the agent_set
        target_file_list: list[str] | None = None
        if target.sets and agent_set in target.sets:
            target_file_list = target.sets[agent_set]

        # Build merged rules for this specific target (with override if applicable)
        merged_rules = build_merged_rules(kit_index=kit_index, agent_set=agent_set, file_list=target_file_list)

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
