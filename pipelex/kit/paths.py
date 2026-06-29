from importlib.resources import files

from pipelex.types import Traversable

# Git-ignored config files that should not be synced between .pipelex and kit/configs.
# These are personal override files that differ per developer/environment:
# - pipelex_service.toml: Contains terms_accepted (False for new users, True for devs)
# - pipelex_override.toml: Personal config overrides
# - telemetry_override.toml: Personal telemetry settings
# - telemetry.project.toml: Kit-internal commented-out template used by project init
#   only; must never be propagated into ~/.pipelex/ or a project's .pipelex/ as-is
GIT_IGNORED_CONFIG_FILES: frozenset[str] = frozenset(
    {
        ".DS_Store",
        "pipelex_service.toml",
        "pipelex_override.toml",
        "telemetry_override.toml",
        "telemetry.project.toml",
        "pipelex_gateway_models.md",  # Auto-generated from remote config
        "pipelex_gateway_models_plain.md",  # Auto-generated from remote config
        # Custom deck files differ intentionally: kit templates have waterfalls
        # commented out, while .pipelex/ has them active for tests
        "x_custom_llm_deck.toml",
        "x_custom_extract_deck.toml",
    }
)

# Files excluded from config sync checks but still copied during `pipelex init config`.
# Extends GIT_IGNORED_CONFIG_FILES with `telemetry.toml`: the kit's `telemetry.toml`
# holds the active global template, while the pipelex repo's `.pipelex/telemetry.toml`
# dogfoods the commented-out project template. The two files intentionally differ.
CONFIG_SYNC_EXCLUDED_FILES: frozenset[str] = GIT_IGNORED_CONFIG_FILES | {"telemetry.toml"}

# Directories that should not be synced between .pipelex and kit/configs.
# These are runtime directories created locally:
# - storage: Local storage directory for runtime data
# - traces: Local directory for execution traces
GIT_IGNORED_CONFIG_DIRS: frozenset[str] = frozenset(
    {
        "storage",
        "traces",
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
