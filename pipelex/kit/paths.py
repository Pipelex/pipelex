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
        "pipelex_gateway_models_plain.md",  # Auto-generated from remote config
        # Custom deck files differ intentionally: kit templates have waterfalls
        # commented out, while .pipelex/ has them active for tests
        "x_custom_llm_deck.toml",
        "x_custom_extract_deck.toml",
    }
)

# Files excluded from config sync checks but still copied during `pipelex init config`.
# Currently equals GIT_IGNORED_CONFIG_FILES; kept as a separate variable so that
# additional auto-generated or environment-specific files can be excluded independently.
CONFIG_SYNC_EXCLUDED_FILES: frozenset[str] = GIT_IGNORED_CONFIG_FILES

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
