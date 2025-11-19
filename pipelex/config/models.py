from typing import cast

from pydantic import Field, field_validator

from pipelex.core.bundles.exceptions import PipeValidationErrorType
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.types import StrEnum


class ConfigPaths:
    DEFAULT_CONFIG_DIR_PATH = "./.pipelex"
    INFERENCE_DIR_NAME = "inference"
    INFERENCE_DIR_PATH = f"{DEFAULT_CONFIG_DIR_PATH}/{INFERENCE_DIR_NAME}"
    BACKENDS_FILE_NAME = "backends.toml"
    BACKENDS_FILE_PATH = f"{INFERENCE_DIR_PATH}/{BACKENDS_FILE_NAME}"
    BACKENDS_DIR_NAME = "backends"
    BACKENDS_DIR_PATH = f"{INFERENCE_DIR_PATH}/{BACKENDS_DIR_NAME}"
    ROUTING_PROFILES_FILE_NAME = "routing_profiles.toml"
    ROUTING_PROFILES_FILE_PATH = f"{INFERENCE_DIR_PATH}/{ROUTING_PROFILES_FILE_NAME}"
    MODEL_DECKS_DIR_NAME = "deck"
    MODEL_DECKS_DIR_PATH = f"{INFERENCE_DIR_PATH}/{MODEL_DECKS_DIR_NAME}"
    BASE_DECK_FILE_NAME = "base_deck.toml"
    BASE_DECK_FILE_PATH = f"{MODEL_DECKS_DIR_PATH}/{BASE_DECK_FILE_NAME}"
    OVERRIDES_DECK_FILE_NAME = "overrides.toml"
    OVERRIDES_DECK_FILE_PATH = f"{MODEL_DECKS_DIR_PATH}/{OVERRIDES_DECK_FILE_NAME}"


class ValidationErrorReaction(StrEnum):
    RAISE = "raise"
    LOG = "log"
    IGNORE = "ignore"


class ValidationErrorConfig(ConfigModel):
    default_reaction: ValidationErrorReaction = Field(strict=False)
    reactions: dict[PipeValidationErrorType, ValidationErrorReaction]

    @field_validator("reactions", mode="before")
    @classmethod
    def validate_reactions(cls, value: dict[str, str]) -> dict[PipeValidationErrorType, ValidationErrorReaction]:
        return cast(
            "dict[PipeValidationErrorType, ValidationErrorReaction]",
            ConfigModel.transform_dict_str_to_enum(
                input_dict=value,
                key_enum_cls=PipeValidationErrorType,
                value_enum_cls=ValidationErrorReaction,
            ),
        )
