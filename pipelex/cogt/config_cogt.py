from pipelex.cogt.exceptions import LLMConfigError
from pipelex.cogt.img_gen.img_gen_job_components import ImgGenJobConfig, ImgGenJobParams, ImgGenJobParamsDefaults
from pipelex.cogt.llm.llm_job_components import LLMJobConfig
from pipelex.cogt.models.model_deck_config import ModelDeckConfig
from pipelex.plugins.fal.fal_config import FalConfig
from pipelex.system.configuration.config_model import ConfigModel


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


class Cogt(ConfigModel):
    model_deck_config: ModelDeckConfig
    llm_config: LLMConfig
    img_gen_config: ImgGenConfig
    extract_config: ExtractConfig
