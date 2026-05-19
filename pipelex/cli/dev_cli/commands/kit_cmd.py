"""CLI commands for kit asset management."""

from pathlib import Path

import typer
from posthog import tag
from typing_extensions import Annotated

from pipelex.base_exceptions import PipelexError
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

    config = get_config()
    preferred_targets: list[AgentTarget] = list(config.pipelex.kit_config.preferred_agent_targets)

    # The config validator guarantees CURSOR cannot coexist with other targets,
    # so a simple membership check is enough to pick the branch.
    if AgentTarget.CURSOR in preferred_targets:
        typer.echo("Updating Cursor rules...")
        update_cursor_rules(resolved_repo_root, loaded_kit_index, agent_set=agent_set)
    else:
        all_targets = loaded_kit_index.agent_rules.targets
        filtered_targets: dict[str, Target] = {}
        for target_key in preferred_targets:
            if target_key not in all_targets:
                msg = f"Target '{target_key}' not found in index.toml"
                raise PipelexCLIError(msg)
            filtered_targets[target_key] = all_targets[target_key]
        names = ", ".join(sorted(filtered_targets.keys()))
        typer.echo(f"Updating {names} rules...")
        update_single_file_agent_rules(
            repo_root=resolved_repo_root,
            kit_index=loaded_kit_index,
            agent_set=agent_set,
            targets=filtered_targets,
        )

    if cleanup:
        typer.echo("Cleaning up rules from other targets...")
        _cleanup_other_targets(
            repo_root=resolved_repo_root,
            kit_index=loaded_kit_index,
            preferred_targets=preferred_targets,
        )

    typer.echo("Kit sync completed successfully")


def _cleanup_other_targets(
    repo_root: Path,
    kit_index: KitIndex,
    preferred_targets: list[AgentTarget],
) -> None:
    """Remove Pipelex rules from all targets except the preferred ones.

    For Cursor: deletes .mdc files
    For single-file targets: deletes the files entirely
    """
    if AgentTarget.CURSOR not in preferred_targets:
        remove_cursor_rules(repo_root)

    all_targets = kit_index.agent_rules.targets
    targets_to_clean: dict[str, Target] = {target_key: target for target_key, target in all_targets.items() if target_key not in preferred_targets}

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

    except (PipelexError, OSError) as exc:
        msg = f"Failed to sync kit assets for agent rules: {exc}"
        raise PipelexCLIError(msg) from exc
    finally:
        Pipelex.teardown_if_needed()
