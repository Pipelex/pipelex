# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

import os
from typing import Dict, List, Optional, cast

from pydantic import Field, field_validator

from pipelex.cogt.anthropic.anthropic_config import AnthropicConfig
from pipelex.cogt.bedrock.bedrock_config import BedrockConfig
from pipelex.cogt.imgg.imgg_handle import ImggHandle
from pipelex.cogt.imgg.imgg_job_components import ImggJobConfig, ImggJobParams, ImggJobParamsDefaults
from pipelex.cogt.llm.llm_job_components import LLMJobConfig
from pipelex.cogt.llm.llm_models.llm_platform import LLMPlatform
from pipelex.cogt.mistral.mistral_config import MistralConfig
from pipelex.cogt.ocr.ocr_config import OCRConfig
from pipelex.cogt.openai.azure_openai_config import AzureOpenAIConfig
from pipelex.cogt.openai.openai_config import OpenAIOpenAIConfig
from pipelex.cogt.openai.perplexity_config import PerplexityConfig
from pipelex.cogt.openai.vertexai_config import VertexAIConfig
from pipelex.tools.config.manager import config_manager
from pipelex.tools.config.models import ConfigModel


class CogtReportConfig(ConfigModel):
    is_log_costs_to_console: bool
    is_generate_cost_report_file_enabled: bool
    cost_report_dir_path: str
    cost_report_base_name: str
    cost_report_extension: str
    cost_report_unit_scale: float


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
    llm_integrations_path: str
    preferred_platforms: Dict[str, LLMPlatform]

    anthropic_config: AnthropicConfig
    azure_openai_config: AzureOpenAIConfig
    bedrock_config: BedrockConfig
    vertexai_config: VertexAIConfig
    mistral_config: MistralConfig
    openai_openai_config: OpenAIOpenAIConfig
    perplexity_config: PerplexityConfig

    instructor_config: InstructorConfig
    llm_job_config: LLMJobConfig

    default_max_images: int

    @property
    def llm_model_libraries_dir_path(self) -> str:
        return os.path.abspath(os.path.join(config_manager.pipelex_root_dir, self.llm_integrations_path))

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


class Cogt(ConfigModel):
    inference_manager_config: InferenceManagerConfig
    cogt_report_config: CogtReportConfig
    llm_config: LLMConfig
    imgg_config: ImggConfig
    ocr_config: OCRConfig
