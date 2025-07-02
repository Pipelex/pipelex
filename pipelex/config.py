from typing import Dict, List, Optional, cast

import shortuuid
from pydantic import Field, field_validator

from pipelex.cogt.config_cogt import Cogt
from pipelex.cogt.llm.llm_models.llm_prompting_target import LLMPromptingTarget
from pipelex.exceptions import PipelexConfigError, StaticValidationErrorType
from pipelex.hub import get_required_config
from pipelex.libraries.library_config import LibraryConfig
from pipelex.pipeline.track.tracker_config import TrackerConfig
from pipelex.tools.aws.aws_config import AwsConfig
from pipelex.tools.config.models import ConfigModel, ConfigRoot
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.templating.templating_models import PromptingStyle
from pipelex.types import StrEnum


class StaticValidationReaction(StrEnum):
    RAISE = "raise"
    LOG = "log"
    IGNORE = "ignore"


class StaticValidationConfig(ConfigModel):
    default_reaction: StaticValidationReaction = Field(strict=False)
    reactions: Dict[StaticValidationErrorType, StaticValidationReaction]

    @field_validator("reactions", mode="before")
    def validate_reactions(cls, value: Dict[str, str]) -> Dict[StaticValidationErrorType, StaticValidationReaction]:
        the_dict = cast(
            Dict[StaticValidationErrorType, StaticValidationReaction],
            ConfigModel.transform_dict_str_to_enum(
                input_dict=value,
                key_enum_cls=StaticValidationErrorType,
                value_enum_cls=StaticValidationReaction,
            ),
        )
        return the_dict


class PipeRunConfig(ConfigModel):
    pipe_stack_limit: int


class DryRunConfig(ConfigModel):
    apply_to_jinja2_rendering: bool
    text_gen_truncate_length: int
    nb_list_items: int
    nb_ocr_pages: int
    image_urls: List[str]
    allowed_to_fail_pipes: List[str] = Field(default_factory=list)

    @field_validator("image_urls", mode="before")
    def validate_image_urls(cls, value: List[str]) -> List[str]:
        if not value:
            raise PipelexConfigError("dry_run_config.image_urls must be a non-empty list")
        return value


class GenericTemplateNames(ConfigModel):
    structure_from_preliminary_text_user: str
    structure_from_preliminary_text_system: str


class StructureConfig(ConfigModel):
    is_default_text_then_structure: bool


class PromptingConfig(ConfigModel):
    default_prompting_style: PromptingStyle
    prompting_styles: Dict[str, PromptingStyle]

    def get_prompting_style(self, prompting_target: Optional[LLMPromptingTarget] = None) -> Optional[PromptingStyle]:
        if prompting_target:
            return self.prompting_styles.get(prompting_target, self.default_prompting_style)
        else:
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


class Pipelex(ConfigModel):
    extra_env_files: List[str]
    feature_config: FeatureConfig
    log_config: LogConfig
    aws_config: AwsConfig

    library_config: LibraryConfig
    static_validation_config: StaticValidationConfig
    generic_template_names: GenericTemplateNames
    tracker_config: TrackerConfig
    structure_config: StructureConfig
    prompting_config: PromptingConfig

    dry_run_config: DryRunConfig
    pipe_run_config: PipeRunConfig
    reporting_config: ReportingConfig


class PipelexConfig(ConfigRoot):
    session_id: str = shortuuid.uuid()
    cogt: Cogt
    pipelex: Pipelex


def get_config() -> PipelexConfig:
    singleton_config = get_required_config()
    if not isinstance(singleton_config, PipelexConfig):
        raise RuntimeError(f"Expected {PipelexConfig}, but got {type(singleton_config)}")
    return singleton_config
