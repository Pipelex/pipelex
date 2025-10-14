from pipelex.cogt.exceptions import LLMConfigError
from pipelex.cogt.img_gen.img_gen_job_components import ImgGenJobConfig, ImgGenJobParams, ImgGenJobParamsDefaults
from pipelex.cogt.llm.llm_job_components import LLMJobConfig
from pipelex.plugins.fal.fal_config import FalConfig
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.tools.misc.file_utils import find_files_in_dir


class ExtractConfig(ConfigModel):
    page_output_text_file_name: str
    default_page_views_dpi: int


class ImgGenConfig(ConfigModel):
    img_gen_job_config: ImgGenJobConfig
    img_gen_param_defaults: ImgGenJobParamsDefaults
    fal_config: FalConfig

    def make_default_img_gen_job_params(self) -> ImgGenJobParams:
        return self.img_gen_param_defaults.make_img_gen_job_params()


class InstructorConfig(ConfigModel):
    is_openai_structured_output_enabled: bool
    is_dump_kwargs_enabled: bool
    is_dump_response_enabled: bool
    is_dump_error_enabled: bool


class LLMConfig(ConfigModel):
    instructor_config: InstructorConfig
    llm_job_config: LLMJobConfig
    is_structure_prompt_enabled: bool
    default_max_images: int
    is_dump_text_prompts_enabled: bool
    is_dump_response_text_enabled: bool
    generic_templates: dict[str, str]

    def get_template(self, template_name: str) -> str:
        template = self.generic_templates.get(template_name)
        if not template:
            msg = f"Template '{template_name}' not found in generic_templates"
            raise LLMConfigError(msg)
        return template


class InferenceManagerConfig(ConfigModel):
    is_auto_setup_preset_llm: bool
    is_auto_setup_preset_img_gen: bool
    is_auto_setup_preset_extract: bool


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

    def get_model_deck_paths(self) -> list[str]:
        """Get all Model deck TOML file paths sorted alphabetically."""
        model_deck_paths = [
            str(path)
            for path in find_files_in_dir(
                dir_path=f"{self.inference_config_path}/deck",
                pattern="*.toml",
                is_recursive=True,
            )
        ]
        model_deck_paths.sort()
        return model_deck_paths


class Cogt(ConfigModel):
    inference_config: InferenceConfig
    inference_manager_config: InferenceManagerConfig
    llm_config: LLMConfig
    img_gen_config: ImgGenConfig
    extract_config: ExtractConfig
