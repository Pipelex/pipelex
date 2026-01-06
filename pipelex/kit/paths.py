from importlib.resources import files

from pipelex.types import Traversable

# Git-ignored config files that should not be synced between .pipelex and kit/configs.
# These are personal override files that differ per developer/environment:
# - pipelex_service.toml: Contains terms_accepted (False for new users, True for devs)
# - pipelex_override.toml: Personal config overrides
# - telemetry_override.toml: Personal telemetry settings
GIT_IGNORED_CONFIG_FILES: frozenset[str] = frozenset(
    {
        "pipelex_service.toml",
        "pipelex_override.toml",
        "telemetry_override.toml",
        "pipelex_gateway_models.md",  # Auto-generated from remote config
    }
)

# Directories that should not be synced between .pipelex and kit/configs.
# These are runtime directories created locally:
# - storage: Local storage directory for runtime data
GIT_IGNORED_CONFIG_DIRS: frozenset[str] = frozenset(
    {
        "storage",
    }
)


def get_kit_root() -> Traversable:
    """Get the root directory of the kit package.

    Returns:
        Traversable object pointing to pipelex.kit package
    """
    return files("pipelex.kit")


def get_kit_agents_dir() -> Traversable:
    """Get the agents directory within the kit package.

    Returns:
        Traversable object pointing to pipelex.kit/agent_rules
    """
    return get_kit_root() / "agent_rules"


def get_kit_configs_dir() -> Traversable:
    """Get the configs directory within the kit package.

    Returns:
        Traversable object pointing to pipelex.kit/configs
    """
    return get_kit_root() / "configs"


def get_kit_migrations_dir() -> Traversable:
    """Get the migrations directory within the kit package.

    Returns:
        Traversable object pointing to pipelex.kit/migrations
    """
    return get_kit_root() / "migrations"
