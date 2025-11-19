from typing import Literal

from typing_extensions import override

from pipelex.cogt.llm.llm_setting import LLMModelChoice
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.types import StrEnum


class StructuringMethod(StrEnum):
    DIRECT = "direct"
    PRELIMINARY_TEXT = "preliminary_text"


class PipeLLMBlueprint(PipeBlueprint):
    type: Literal["PipeLLM"] = "PipeLLM"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"

    model: LLMModelChoice | None = None
    model_to_structure: LLMModelChoice | None = None

    system_prompt: str | None = None
    prompt: str | None = None

    structuring_method: StructuringMethod | None = None

    @override
    def _validate_inputs(self):
        # Get all required variables from prompt and system_prompt
        required_variables: set[str] = set()

        if self.prompt:
            preprocessed_template = preprocess_template(self.prompt)
            required_variables.update(
                detect_jinja2_required_variables(
                    template_category=TemplateCategory.LLM_PROMPT,
                    template_source=preprocessed_template,
                )
            )

        if self.system_prompt:
            preprocessed_system_template = preprocess_template(self.system_prompt)
            required_variables.update(
                detect_jinja2_required_variables(
                    template_category=TemplateCategory.LLM_PROMPT,
                    template_source=preprocessed_system_template,
                )
            )

        # Filter out internal variables that start with underscore and special variables
        required_variables = {var for var in required_variables if not var.startswith("_") and var not in ("preliminary_text", "place_holder")}

        # Check that all required variables are in inputs
        input_names: set[str] = set(self.inputs.keys()) if self.inputs else set()
        missing_variables: set[str] = required_variables - input_names

        if missing_variables:
            missing_vars_str = ", ".join(sorted(missing_variables))
            msg = (
                f"Missing input variable(s) in prompt template: {missing_vars_str}. "
                "These variables are used in the prompt but not declared in inputs."
            )
            raise ValueError(msg)

    @override
    def _validate_output(self):
        pass
