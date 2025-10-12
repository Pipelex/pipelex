"""Index loader for kit configuration."""

from pipelex.kit.index_models import KitIndex
from pipelex.kit.paths import get_kit_root
from pipelex.tools.misc.toml_utils import load_toml_from_path


def load_index() -> KitIndex:
    """Load and validate the kit index.toml configuration.

    Returns:
        Validated KitIndex model

    Raises:
        TomlError: If TOML parsing fails
        ValidationError: If validation fails
    """
    index_path = get_kit_root() / "index.toml"
    data = load_toml_from_path(str(index_path))
    return KitIndex.model_validate(data)
