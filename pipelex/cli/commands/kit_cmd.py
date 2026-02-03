"""CLI commands for kit asset management."""

from pathlib import Path

import typer
from posthog import tag
from typing_extensions import Annotated

from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import ErrorContext
from pipelex.cli.exceptions import PipelexCLIError
from pipelex.config import get_config
from pipelex.hub import get_telemetry_manager
from pipelex.kit.cursor_rules import remove_cursor_rules, update_cursor_rules
from pipelex.kit.index_loader import load_index
from pipelex.kit.index_models import KitIndex, Target
from pipelex.kit.single_file_agent_rules import remove_from_targets, update_single_file_agent_rules
from pipelex.pipelex import Pipelex
from pipelex.system.configuration.configs import AgentTarget
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventProperty
from pipelex.tools.misc.package_utils import get_package_version

COMMAND = "kit"
SUB_COMMAND_RULES = "rules"

kit_app = typer.Typer(no_args_is_help=True)


def _sync_agent_rules(
    repo_root: Path | None,
    agent_set: str | None,
    cleanup: bool,
    kit_index: KitIndex | None = None,
) -> None:
    resolved_repo_root = repo_root if repo_root is not None else Path()
    loaded_kit_index = load_index() if kit_index is None else kit_index
    agent_set = agent_set or loaded_kit_index.agent_rules.default_set

    # Get preferred agent target from config
    config = get_config()
    preferred_target = config.pipelex.kit_config.preferred_agent_target

    match preferred_target:
        case AgentTarget.CURSOR:
            typer.echo("Updating Cursor rules...")
            update_cursor_rules(resolved_repo_root, loaded_kit_index, agent_set=agent_set)
        case AgentTarget.AGENTS | AgentTarget.CLAUDE:
            typer.echo(f"Updating {preferred_target} rules...")
            all_targets = loaded_kit_index.agent_rules.targets
            if preferred_target in all_targets:
                filtered_targets: dict[str, Target] = {preferred_target: all_targets[preferred_target]}
                update_single_file_agent_rules(
                    repo_root=resolved_repo_root,
                    kit_index=loaded_kit_index,
                    agent_set=agent_set,
                    targets=filtered_targets,
                )
            else:
                msg = f"Target '{preferred_target}' not found in index.toml"
                raise PipelexCLIError(msg)

    # Cleanup: remove rules from other targets
    if cleanup:
        typer.echo("Cleaning up rules from other targets...")
        _cleanup_other_targets(
            repo_root=resolved_repo_root,
            kit_index=loaded_kit_index,
            preferred_target=preferred_target,
        )

    typer.echo("Kit sync completed successfully")


def _cleanup_other_targets(
    repo_root: Path,
    kit_index: KitIndex,
    preferred_target: AgentTarget,
) -> None:
    """Remove Pipelex rules from all targets except the preferred one.

    For Cursor: deletes .mdc files
    For single-file targets: deletes the files entirely
    """
    # If preferred target is NOT cursor, remove cursor rules
    match preferred_target:
        case AgentTarget.CURSOR:
            pass  # Don't remove cursor rules since it's the preferred target
        case AgentTarget.AGENTS | AgentTarget.CLAUDE:
            # Remove cursor rules
            remove_cursor_rules(repo_root)

    # For single-file targets, delete files for all except the preferred one
    all_targets = kit_index.agent_rules.targets
    targets_to_clean: dict[str, Target] = {}

    for target_key, target in all_targets.items():
        # Skip the preferred target
        if target_key == preferred_target:
            continue
        targets_to_clean[target_key] = target

    if targets_to_clean:
        remove_from_targets(
            repo_root=repo_root,
            targets=targets_to_clean,
        )


@kit_app.command("rules", help="Install agent rules for the preferred agent target (configured in pipelex.toml)")
def agent_rules(
    repo_root: Annotated[Path | None, typer.Option("--repo-root", dir_okay=True, writable=True, help="Repository root directory")] = None,
    agent_set: Annotated[str | None, typer.Option("--set", help="Agent rule set to sync (use 'pipelex' for Pipelex repo)")] = None,
    cleanup: Annotated[bool, typer.Option("--cleanup", help="Delete Pipelex rules files from other agent targets")] = False,
) -> None:
    try:
        make_pipelex_for_cli(context=ErrorContext.KIT)
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
            tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} {SUB_COMMAND_RULES}")
            _sync_agent_rules(
                repo_root=repo_root,
                agent_set=agent_set,
                cleanup=cleanup,
            )

    except Exception as exc:
        msg = f"Failed to sync kit assets for agent rules: {exc}"
        raise PipelexCLIError(msg) from exc
    finally:
        Pipelex.teardown_if_needed()
