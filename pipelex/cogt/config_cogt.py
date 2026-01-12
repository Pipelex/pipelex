from pydantic import Field, field_validator

from pipelex.cogt.exceptions import LLMConfigError
from pipelex.cogt.img_gen.img_gen_job_components import ImgGenJobConfig, ImgGenJobParams, ImgGenJobParamsDefaults, Quality
from pipelex.cogt.llm.llm_job_components import LLMJobConfig
from pipelex.cogt.models.model_deck_config import ModelDeckConfig
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.system.exceptions import ConfigValidationError


class ExtractConfig(ConfigModel):
    default_page_views_dpi: int


QualityToStepsMap = dict[str, int]


class ImgGenConfig(ConfigModel):
    img_gen_job_config: ImgGenJobConfig
    img_gen_param_defaults: ImgGenJobParamsDefaults
    quality_to_steps_maps: dict[str, QualityToStepsMap]

    def make_default_img_gen_job_params(self) -> ImgGenJobParams:
        return self.img_gen_param_defaults.make_img_gen_job_params()

    def get_num_inference_steps(self, model_name: str, quality: Quality) -> int:
        quality_to_steps_map = self.quality_to_steps_maps.get(model_name)
        if not quality_to_steps_map:
            msg = f"No quality-to-steps map found for model '{model_name}'"
            raise ConfigValidationError(msg)
        num_inference_steps = quality_to_steps_map.get(quality.value)
        if num_inference_steps is None:
            msg = f"No number of inference steps found for quality '{quality.value}' and model '{model_name}'"
            raise ConfigValidationError(msg)
        return num_inference_steps

    @field_validator("quality_to_steps_maps")
    @classmethod
    def validate_quality_mapping(cls, value: dict[str, QualityToStepsMap]) -> dict[str, QualityToStepsMap]:
        valid_qualities = {quality.value for quality in Quality}
        missing_qualities: set[str]
        invalid_qualities: set[str]
        for model_name, quality_to_steps_map in value.items():
            missing_qualities = valid_qualities - set(quality_to_steps_map.keys())
            invalid_qualities = set(quality_to_steps_map.keys()) - valid_qualities

            if missing_qualities and invalid_qualities:
                msg = f"Missing ({missing_qualities}) and invalid ({invalid_qualities}) quality levels in mapping for model '{model_name}'"
                raise ConfigValidationError(msg)
            if missing_qualities:
                msg = f"Missing quality levels in mapping: {missing_qualities} for model '{model_name}'"
                raise ConfigValidationError(msg)
            if invalid_qualities:
                msg = f"Invalid quality levels in mapping: {invalid_qualities} for model '{model_name}'"
                raise ConfigValidationError(msg)
        return value


class InstructorConfig(ConfigModel):
    is_dump_kwargs_enabled: bool
    is_dump_response_enabled: bool
    is_dump_error_enabled: bool


class AnthropicConfig(ConfigModel):
    structured_output_timeout_seconds: int


class LLMConfig(ConfigModel):
    instructor_config: InstructorConfig
    anthropic_config: AnthropicConfig
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


class TenacityConfig(ConfigModel):
    max_retries: int = Field(..., ge=1, le=100, description="Maximum number of retry attempts before giving up")
    wait_multiplier: float = Field(..., ge=0.1, le=10, description="Multiplier applied to the wait time between retries (in seconds)")
    wait_max: float = Field(..., ge=0.1, le=20, description="Maximum wait time between retries (in seconds)")
    wait_exp_base: float = Field(..., ge=1.1, le=10, description="Base for exponential backoff calculation")


class GatewayTestConfig(ConfigModel):
    config_id_substitutions: dict[str, str]


class Cogt(ConfigModel):
    model_deck_config: ModelDeckConfig
    tenacity_config: TenacityConfig
    llm_config: LLMConfig
    img_gen_config: ImgGenConfig
    extract_config: ExtractConfig
    gateway_test_config: GatewayTestConfig
