from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from pipelex.cogt.exceptions import ModelDeckNotFoundError, ModelDeckValidationError
from pipelex.cogt.models.model_deck import ModelDeckBlueprint
from pipelex.tools.misc.json_utils import deep_update
from pipelex.tools.misc.toml_utils import load_toml_from_path
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error


def load_model_deck_blueprint(model_deck_paths: list[str], *, base_deck_dict: Mapping[str, Any] | None = None) -> ModelDeckBlueprint:
    """Merge the model deck files, in order, over an optional base document, and validate the result.

    Args:
        model_deck_paths: The deck files, in the order they are merged: a later file overrides an earlier one.
        base_deck_dict: What the files are merged over, so any file overrides it: the model deck defaults the plugins
            declare (`PluginModelDeclarations.make_deck_base`). The merged document is validated as a whole, so a base
            entry meets the same checks as a file's.
    """
    full_deck_dict: dict[str, Any] = {}
    if base_deck_dict:
        deep_update(full_deck_dict, updates=base_deck_dict)
    if not model_deck_paths:
        msg = "No Model deck paths found. Please run `pipelex init config` to create the set up the base deck."
        raise ModelDeckNotFoundError(msg)

    for deck_path in model_deck_paths:
        try:
            deck_dict = load_toml_from_path(path=deck_path)
        except FileNotFoundError as not_found_exc:
            msg = f"Could not find Model Deck file at '{deck_path}': {not_found_exc}"
            raise ModelDeckNotFoundError(msg) from not_found_exc
        deep_update(full_deck_dict, updates=deck_dict)

    try:
        return ModelDeckBlueprint.model_validate(full_deck_dict)
    except ValidationError as exc:
        valiation_error_msg = format_pydantic_validation_error(exc)
        msg = f"Invalid Model Deck configuration in {model_deck_paths}: {valiation_error_msg}"
        raise ModelDeckValidationError(msg) from exc
