from typing import Any

from pydantic import ValidationError

from pipelex.cogt.exceptions import ModelDeckNotFoundError, ModelDeckValidationError
from pipelex.cogt.models.model_deck import ModelDeckBlueprint
from pipelex.tools.misc.json_utils import deep_update
from pipelex.tools.misc.toml_utils import load_toml_from_path
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error


def load_model_deck_blueprint(model_deck_paths: list[str]) -> ModelDeckBlueprint:
    full_deck_dict: dict[str, Any] = {}
    if not model_deck_paths:
        msg = "No Model deck paths found. Please run `pipelex init config` to create the set up the base deck."
        raise ModelDeckNotFoundError(msg)

    for deck_path in model_deck_paths:
        try:
            deck_dict = load_toml_from_path(path=deck_path)
        except FileNotFoundError as not_found_exc:
            msg = f"Could not find Model Deck file at '{deck_path}': {not_found_exc}"
            raise ModelDeckNotFoundError(msg) from not_found_exc
        deep_update(full_deck_dict, deck_dict)

    try:
        return ModelDeckBlueprint.model_validate(full_deck_dict)
    except ValidationError as exc:
        valiation_error_msg = format_pydantic_validation_error(exc)
        msg = f"Invalid Model Deck configuration in {model_deck_paths}: {valiation_error_msg}"
        raise ModelDeckValidationError(msg) from exc
