from typing import cast

import shortuuid
from pydantic import Field, field_validator

from pipelex.cogt.config_cogt import Cogt
from pipelex.cogt.model_backends.prompting_target import PromptingTarget
from pipelex.cogt.templating.templating_style import TemplatingStyle
from pipelex.exceptions import PipelexConfigError, StaticValidationErrorType
from pipelex.hub import get_required_config
from pipelex.language.plx_config import PlxConfig
from pipelex.pipeline.track.tracker_config import TrackerConfig
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.system.configuration.config_root import ConfigRoot
from pipelex.tools.aws.aws_config import AwsConfig
from pipelex.tools.log.log_config import LogConfig
from pipelex.types import StrEnum


class StaticValidationReaction(StrEnum):
    RAISE = "raise"
    LOG = "log"
    IGNORE = "ignore"


class StaticValidationConfig(ConfigModel):
    default_reaction: StaticValidationReaction = Field(strict=False)
    reactions: dict[StaticValidationErrorType, StaticValidationReaction]

    @field_validator("reactions", mode="before")
    @classmethod
    def validate_reactions(cls, value: dict[str, str]) -> dict[StaticValidationErrorType, StaticValidationReaction]:
        return cast(
            "dict[StaticValidationErrorType, StaticValidationReaction]",
            ConfigModel.transform_dict_str_to_enum(
                input_dict=value,
                key_enum_cls=StaticValidationErrorType,
                value_enum_cls=StaticValidationReaction,
            ),
        )


class PipeRunConfig(ConfigModel):
    pipe_stack_limit: int


class DryRunConfig(ConfigModel):
    apply_to_jinja2_rendering: bool
    text_gen_truncate_length: int
    nb_list_items: int
    nb_extract_pages: int
    image_urls: list[str]
    allowed_to_fail_pipes: list[str] = Field(default_factory=list)

    @field_validator("image_urls", mode="before")
    @classmethod
    def validate_image_urls(cls, value: list[str]) -> list[str]:
        if not value:
            msg = "dry_run_config.image_urls must be a non-empty list"
            raise PipelexConfigError(msg)
        return value


class StructureConfig(ConfigModel):
    is_default_text_then_structure: bool


class PromptingConfig(ConfigModel):
    default_prompting_style: TemplatingStyle
    prompting_styles: dict[str, TemplatingStyle]

    def get_prompting_style(self, prompting_target: PromptingTarget | None = None) -> TemplatingStyle | None:
        if prompting_target:
            return self.prompting_styles.get(prompting_target, self.default_prompting_style)
        return None


class FeatureConfig(ConfigModel):
    is_pipeline_tracking_enabled: bool
    is_activity_tracking_enabled: bool
    is_reporting_enabled: bool


class ReportingConfig(ConfigModel):
    is_log_costs_to_console: bool
    is_generate_cost_report_file_enabled: bool
    cost_report_dir_path: str
    cost_report_base_name: str
    cost_report_extension: str
    cost_report_unit_scale: float


class ObserverConfig(ConfigModel):
    observer_dir: str


class ScanConfig(ConfigModel):
    excluded_dirs: frozenset[str]

    @field_validator("excluded_dirs", mode="before")
    @classmethod
    def validate_excluded_dirs(cls, value: list[str] | frozenset[str]) -> frozenset[str]:
        if isinstance(value, frozenset):
            return value
        return frozenset(value)


class Pipelex(ConfigModel):
    feature_config: FeatureConfig
    log_config: LogConfig
    aws_config: AwsConfig

    static_validation_config: StaticValidationConfig
    tracker_config: TrackerConfig
    structure_config: StructureConfig
    prompting_config: PromptingConfig
    plx_config: PlxConfig

    dry_run_config: DryRunConfig
    pipe_run_config: PipeRunConfig
    reporting_config: ReportingConfig
    observer_config: ObserverConfig
    scan_config: ScanConfig


class MigrationConfig(ConfigModel):
    migration_maps: dict[str, dict[str, str]]

    def text_in_renaming_keys(self, category: str, text: str) -> list[tuple[str, str]]:
        renaming_map = self.migration_maps.get(category)
        if not renaming_map:
            return []
        return [(key, value) for key, value in renaming_map.items() if text in key]

    def text_in_renaming_values(self, category: str, text: str) -> list[tuple[str, str]]:
        renaming_map = self.migration_maps.get(category)
        if not renaming_map:
            return []
        return [(key, value) for key, value in renaming_map.items() if text in value]


class PipelexConfig(ConfigRoot):
    session_id: str = shortuuid.uuid()
    cogt: Cogt
    pipelex: Pipelex
    migration: MigrationConfig


def get_config() -> PipelexConfig:
    singleton_config = get_required_config()
    if not isinstance(singleton_config, PipelexConfig):
        msg = f"Expected {PipelexConfig}, but got {type(singleton_config)}"
        raise TypeError(msg)
    return singleton_config
