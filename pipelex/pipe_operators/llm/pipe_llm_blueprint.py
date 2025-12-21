from typing import Literal

from typing_extensions import override

from pipelex.cogt.llm.llm_setting import LLMModelChoice
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.tools.jinja2.jinja2_errors import Jinja2DetectVariablesError
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
    def validate_inputs(self):
        # Get all required variables from prompt and system_prompt
        required_variables: set[str] = set()

        if self.prompt:
            preprocessed_template = preprocess_template(self.prompt)
            try:
                required_variables.update(
                    detect_jinja2_required_variables(
                        template_category=TemplateCategory.LLM_PROMPT,
                        template_source=preprocessed_template,
                    )
                )
            except Jinja2DetectVariablesError as exc:
                msg = f"Could not detect required variables in prompt for PipeLLM: {exc}"
                raise ValueError(msg) from exc

        if self.system_prompt:
            preprocessed_system_template = preprocess_template(self.system_prompt)
            try:
                required_variables.update(
                    detect_jinja2_required_variables(
                        template_category=TemplateCategory.LLM_PROMPT,
                        template_source=preprocessed_system_template,
                    )
                )
            except Jinja2DetectVariablesError as exc:
                msg = f"Could not detect required variables in system prompt for PipeLLM: {exc}"
                raise ValueError(msg) from exc

        # Filter out internal variables that start with underscore and special variables
        # TODO: replace magic strings by StrEnum and also, make this check clearer and more readable
        filtered_required_variables = {
            var for var in required_variables if not var.startswith("_") and var not in {"preliminary_text", "place_holder"}
        }

        # Check that input_names and filtered_required_variables are equal
        input_names: set[str] = set(self.inputs.keys()) if self.inputs else set()

        # Variables used in prompts but not declared in inputs
        missing_inputs = filtered_required_variables - input_names
        # Variables declared in inputs but not used in prompts
        unused_inputs = input_names - filtered_required_variables

        if missing_inputs:
            missing_vars_str = ", ".join(sorted(missing_inputs))
            msg = f"Missing input variable(s): {missing_vars_str}. These variables are used in the prompt/system_prompt but not declared in inputs."
            raise ValueError(msg)

        if unused_inputs:
            unused_vars_str = ", ".join(sorted(unused_inputs))
            msg = f"Unused input variable(s): {unused_vars_str}. These variables are declared in inputs but not referenced in prompt/system_prompt."
            raise ValueError(msg)

    @override
    def validate_output(self):
        pass
