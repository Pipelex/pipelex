from typing import Dict, List, Optional, cast

from pydantic import Field, field_validator

from pipelex.cogt.imgg.imgg_handle import ImggHandle
from pipelex.cogt.imgg.imgg_job_components import ImggJobConfig, ImggJobParams, ImggJobParamsDefaults
from pipelex.cogt.llm.llm_job_components import LLMJobConfig
from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatform
from pipelex.tools.config.models import ConfigModel


class CogtReportConfig(ConfigModel):
    is_log_costs_to_console: bool
    is_generate_cost_report_file_enabled: bool
    cost_report_dir_path: str
    cost_report_base_name: str
    cost_report_extension: str
    cost_report_unit_scale: float


class OcrConfig(ConfigModel):
    ocr_handles: List[str]
    page_output_text_file_name: str


class ImggConfig(ConfigModel):
    default_imgg_handle: ImggHandle = Field(strict=False)
    imgg_job_config: ImggJobConfig
    imgg_param_defaults: ImggJobParamsDefaults
    imgg_handles: List[str]

    def make_default_imgg_job_params(self) -> ImggJobParams:
        return self.imgg_param_defaults.make_imgg_job_params()


class InstructorConfig(ConfigModel):
    is_openai_structured_output_enabled: bool


class LLMConfig(ConfigModel):
    preferred_platforms: Dict[str, LLMPlatform]
    instructor_config: InstructorConfig
    llm_job_config: LLMJobConfig

    default_max_images: int

    @field_validator("preferred_platforms", mode="before")
    def validate_preferred_platforms_enums(cls, value: Dict[str, str]) -> Dict[str, LLMPlatform]:
        """
        Transform what we got for preferred_platforms (Dict[str, str]) into what the field requires: Dict[str, LLMPlatform]
        """
        the_dict = cast(
            Dict[str, LLMPlatform],
            ConfigModel.transform_dict_str_to_enum(
                input_dict=value,
                value_enum_cls=LLMPlatform,
            ),
        )
        return the_dict

    def get_preferred_platform(self, llm_name: str) -> Optional[LLMPlatform]:
        return self.preferred_platforms.get(llm_name)


class InferenceManagerConfig(ConfigModel):
    is_auto_setup_preset_llm: bool
    is_auto_setup_preset_imgg: bool
    is_auto_setup_preset_ocr: bool


class Cogt(ConfigModel):
    inference_manager_config: InferenceManagerConfig
    cogt_report_config: CogtReportConfig
    llm_config: LLMConfig
    imgg_config: ImggConfig
    ocr_config: OcrConfig
