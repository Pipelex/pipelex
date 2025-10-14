from pydantic import ValidationError

from pipelex.exceptions import PipelexException
from pipelex.kit.index_models import KitIndex
from pipelex.kit.paths import get_kit_root
from pipelex.tools.misc.toml_utils import load_toml_from_path
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error


class KitIndexLoadingError(PipelexException):
    pass


def load_index() -> KitIndex:
    """Load and validate the kit index.toml configuration.

    Returns:
        Validated KitIndex model

    Raises:
        TomlError: If TOML parsing fails
        KitIndexLoadingError: If validation fails
    """
    index_path = get_kit_root() / "index.toml"
    data = load_toml_from_path(str(index_path))
    try:
        return KitIndex.model_validate(data)
    except ValidationError as exc:
        msg = f"Validation error in kit index at '{index_path}': {format_pydantic_validation_error(exc)}"
        raise KitIndexLoadingError(message=msg) from exc
