from typing import cast

from pydantic import Field, field_validator

from pipelex.config.config_model import ConfigModel
from pipelex.exceptions import PipelexConfigError, StaticValidationErrorType
from pipelex.types import StrEnum


class StaticValidationReaction(StrEnum):
    RAISE = "raise"
    LOG = "log"
    IGNORE = "ignore"


class StaticValidationConfig(ConfigModel):
    default_reaction: StaticValidationReaction = Field(strict=False)
    reactions: dict[StaticValidationErrorType, StaticValidationReaction]

    @field_validator("reactions", mode="before")
    @staticmethod
    def validate_reactions(value: dict[str, str]) -> dict[StaticValidationErrorType, StaticValidationReaction]:
        return cast(
            "dict[StaticValidationErrorType, StaticValidationReaction]",
            ConfigModel.transform_dict_str_to_enum(
                input_dict=value,
                key_enum_cls=StaticValidationErrorType,
                value_enum_cls=StaticValidationReaction,
            ),
        )


class DryRunConfig(ConfigModel):
    apply_to_jinja2_rendering: bool
    text_gen_truncate_length: int
    nb_list_items: int
    nb_ocr_pages: int
    image_urls: list[str]
    allowed_to_fail_pipes: list[str] = Field(default_factory=list)

    @field_validator("image_urls", mode="before")
    @classmethod
    def validate_image_urls(cls, value: list[str]) -> list[str]:
        if not value:
            msg = "dry_run_config.image_urls must be a non-empty list"
            raise PipelexConfigError(msg)
        return value
