from typing import List

from pydantic import Field

from pipelex.cogt.imgg.imgg_handle import ImggHandle
from pipelex.cogt.imgg.imgg_job_components import ImggJobConfig, ImggJobParams, ImggJobParamsDefaults
from pipelex.cogt.llm.llm_job_components import LLMJobConfig
from pipelex.plugins.fal.fal_config import FalConfig
from pipelex.tools.config.config_model import ConfigModel
from pipelex.tools.misc.file_utils import find_files_in_dir


class OcrConfig(ConfigModel):
    ocr_handles: List[str]
    page_output_text_file_name: str
    default_page_views_dpi: int


class ImggConfig(ConfigModel):
    default_imgg_handle: ImggHandle = Field(strict=False)
    imgg_job_config: ImggJobConfig
    imgg_param_defaults: ImggJobParamsDefaults
    imgg_handles: List[str]
    fal_config: FalConfig

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


class InferenceConfig(ConfigModel):
    inference_config_path: str

    @property
    def routing_profile_library_path(self) -> str:
        return f"{self.inference_config_path}/routing_profiles.toml"

    @property
    def backends_library_path(self) -> str:
        return f"{self.inference_config_path}/backends.toml"

    def model_specs_path(self, backend_name: str) -> str:
        return f"{self.inference_config_path}/backends/{backend_name}.toml"

    def get_llm_deck_paths(self) -> List[str]:
        """Get all LLM deck TOML file paths sorted alphabetically."""
        llm_deck_paths = [
            str(path)
            for path in find_files_in_dir(
                dir_path=f"{self.inference_config_path}/deck",
                pattern="*.toml",
                is_recursive=True,
            )
        ]
        llm_deck_paths.sort()
        return llm_deck_paths


class Cogt(ConfigModel):
    inference_config: InferenceConfig
    inference_manager_config: InferenceManagerConfig
    llm_config: LLMConfig
    imgg_config: ImggConfig
    ocr_config: OcrConfig
