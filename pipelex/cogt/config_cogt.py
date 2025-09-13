from typing import List

from pydantic import Field

from pipelex.cogt.imgg.imgg_handle import ImggHandle
from pipelex.cogt.imgg.imgg_job_components import ImggJobConfig, ImggJobParams, ImggJobParamsDefaults
from pipelex.cogt.llm.llm_job_components import LLMJobConfig
from pipelex.tools.config.config_model import ConfigModel


class OcrConfig(ConfigModel):
    ocr_handles: List[str]
    page_output_text_file_name: str
    default_page_views_dpi: int


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
    instructor_config: InstructorConfig
    llm_job_config: LLMJobConfig

    default_max_images: int


class InferenceManagerConfig(ConfigModel):
    is_auto_setup_preset_llm: bool
    is_auto_setup_preset_imgg: bool
    is_auto_setup_preset_ocr: bool


class Cogt(ConfigModel):
    inference_manager_config: InferenceManagerConfig
    llm_config: LLMConfig
    imgg_config: ImggConfig
    ocr_config: OcrConfig
