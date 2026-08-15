from pydantic import Field, field_validator

from pipelex.base_exceptions import PipelexConfigError
from pipelex.cogt.exceptions import LLMConfigError
from pipelex.cogt.img_gen.img_gen_job_components import ImgGenJobConfig, ImgGenJobParams, ImgGenJobParamsDefaults, Quality
from pipelex.cogt.llm.llm_job_components import ReasoningEffort
from pipelex.cogt.models.model_deck_config import ModelDeckConfig
from pipelex.providers.anthropic.anthropic_config import AnthropicConfig
from pipelex.providers.google.google_config import GoogleConfig
from pipelex.providers.mistral.mistral_config import MistralConfig
from pipelex.providers.openai.openai_config import OpenAIConfig
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.system.exceptions import ConfigValidationError
from pipelex.tools.templating.templating_style import TemplatingStyle


class ExtractConfig(ConfigModel):
    default_page_views_dpi: int


class TemplatingConfig(ConfigModel):
    """How a pipe's inputs are rendered into its prompt, by default.

    Under ``inference`` because its one reader is the kernel's prompt-rendering seam
    (``pipelex/kernel/templating_style_ops.py``).
    """

    default_templating_style: TemplatingStyle


class DryRunConfig(ConfigModel):
    """The shape of the mock outputs a dry run substitutes for real inference.

    Four of its five fields configure mock inference outputs, which is why it sits under
    ``inference``; ``allowed_to_fail_pipes`` is read by the interpreter, a downward read
    the layer rule permits.
    """

    text_gen_truncate_length: int
    nb_list_items: int
    nb_extract_pages: int
    image_urls: list[str]
    allowed_to_fail_pipes: list[str] = Field(default_factory=list)

    @field_validator("image_urls", mode="before")
    @classmethod
    def validate_image_urls(cls, value: list[str]) -> list[str]:
        if not value:
            msg = "inference.dry_run.image_urls must be a non-empty list"
            raise PipelexConfigError(msg)
        return value


QualityToStepsMap = dict[str, int]


class ImgGenConfig(ConfigModel):
    img_gen_job: ImgGenJobConfig
    img_gen_param_defaults: ImgGenJobParamsDefaults
    quality_to_steps_maps: dict[str, QualityToStepsMap]

    def make_default_img_gen_job_params(self) -> ImgGenJobParams:
        return self.img_gen_param_defaults.make_img_gen_job_params()

    def get_num_inference_steps(self, model_name: str, *, quality: Quality) -> int:
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


EffortToBudgetMap = dict[str, int]


class LLMConfig(ConfigModel):
    instructor: InstructorConfig
    openai: OpenAIConfig
    anthropic: AnthropicConfig
    google: GoogleConfig
    mistral: MistralConfig
    # instructor's schema re-ask budget: the total number of attempts (initial + re-asks) allowed
    # when a structured-output call fails schema validation. Distinct from inference.transport_max_retries,
    # which is the transport-level retry count, measured as retries beyond the initial attempt.
    schema_reask_max_attempts: int = Field(ge=1, le=10)
    is_structure_prompt_enabled: bool
    default_max_images: int
    is_dump_text_prompts_enabled: bool
    is_dump_response_text_enabled: bool
    generic_templates: dict[str, str]
    effort_to_budget_maps: dict[str, EffortToBudgetMap]

    def get_template(self, template_name: str) -> str:
        template = self.generic_templates.get(template_name)
        if not template:
            msg = f"Template '{template_name}' not found in generic_templates"
            raise LLMConfigError(msg)
        return template

    def get_reasoning_budget(self, *, family: str, effort: ReasoningEffort) -> int:
        effort_to_budget_map = self.effort_to_budget_maps.get(family)
        if not effort_to_budget_map:
            msg = f"No effort-to-budget map found for reasoning family '{family}'"
            raise ConfigValidationError(msg)
        budget = effort_to_budget_map.get(effort)
        if budget is None:
            msg = f"No budget found for reasoning effort '{effort}' and reasoning family '{family}'"
            raise ConfigValidationError(msg)
        return budget

    @field_validator("effort_to_budget_maps")
    @classmethod
    def validate_effort_to_budget_mapping(cls, value: dict[str, EffortToBudgetMap]) -> dict[str, EffortToBudgetMap]:
        valid_efforts = {effort.value for effort in ReasoningEffort}
        missing_efforts: set[str]
        invalid_efforts: set[str]
        for target_name, effort_to_budget_map in value.items():
            missing_efforts = valid_efforts - set(effort_to_budget_map.keys())
            invalid_efforts = set(effort_to_budget_map.keys()) - valid_efforts

            if missing_efforts and invalid_efforts:
                msg = f"Missing ({missing_efforts}) and invalid ({invalid_efforts}) reasoning effort levels in mapping for target '{target_name}'"
                raise ConfigValidationError(msg)
            if missing_efforts:
                msg = f"Missing reasoning effort levels in mapping: {missing_efforts} for target '{target_name}'"
                raise ConfigValidationError(msg)
            if invalid_efforts:
                msg = f"Invalid reasoning effort levels in mapping: {invalid_efforts} for target '{target_name}'"
                raise ConfigValidationError(msg)
        return value


class GatewayTestConfig(ConfigModel):
    config_id_substitutions: dict[str, str]


class InferenceConfig(ConfigModel):
    # Tier 1 transport retry: the number of times an inference SDK client retries a transient
    # transport failure (connection error, 408/409/429/5xx, honoring Retry-After) on top of the
    # initial attempt. Wired explicitly into every SDK client factory so the retry posture is a
    # deliberate, uniform policy rather than a silently-inherited SDK default. Distinct from
    # llm.schema_reask_max_attempts, which is instructor's schema re-ask count — a different concern.
    transport_max_retries: int = Field(ge=0, le=10)
    model_deck: ModelDeckConfig
    llm: LLMConfig
    img_gen: ImgGenConfig
    extract: ExtractConfig
    gateway_test: GatewayTestConfig
    templating: TemplatingConfig
    dry_run: DryRunConfig
