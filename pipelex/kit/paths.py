from importlib.abc import Traversable
from importlib.resources import files


def get_kit_root() -> Traversable:
    """Get the root directory of the kit package.

    Returns:
        Traversable object pointing to pipelex.kit package
    """
    return files("pipelex.kit")


def get_agents_dir() -> Traversable:
    """Get the agents directory within the kit package.

    Returns:
        Traversable object pointing to pipelex.kit/agent_rules
    """
    return get_kit_root() / "agent_rules"


def get_configs_dir() -> Traversable:
    """Get the configs directory within the kit package.

    Returns:
        Traversable object pointing to pipelex.kit/configs
    """
    return get_kit_root() / "configs"


def get_migrations_dir() -> Traversable:
    """Get the migrations directory within the kit package.

    Returns:
        Traversable object pointing to pipelex.kit/migrations
    """
    return get_kit_root() / "migrations"
