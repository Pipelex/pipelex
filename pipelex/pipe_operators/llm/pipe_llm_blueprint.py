from typing import Literal

from typing_extensions import override

from pipelex.cogt.llm.llm_setting import LLMModelChoice
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.core.pipes.validation import is_input_used_by_variables, is_variable_satisfied_by_inputs
from pipelex.tools.jinja2.jinja2_errors import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.misc.string_utils import get_root_from_dotted_path
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
        # Get all required variable paths from prompt and system_prompt (full dotted paths)
        required_variable_paths: set[str] = set()

        if self.prompt:
            preprocessed_template = preprocess_template(self.prompt)
            try:
                required_variable_paths.update(
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
                required_variable_paths.update(
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
        filtered_variable_paths = {
            var
            for var in required_variable_paths
            if not var.startswith("_") and get_root_from_dotted_path(var) not in {"preliminary_text", "place_holder"}
        }

        input_names: set[str] = set(self.inputs.keys()) if self.inputs else set()

        # Find variables used in prompts but not satisfied by any input
        missing_inputs = {var_path for var_path in filtered_variable_paths if not is_variable_satisfied_by_inputs(var_path, input_names)}

        # Find inputs declared but not used by any variable path
        unused_inputs = {input_name for input_name in input_names if not is_input_used_by_variables(input_name, filtered_variable_paths)}

        if missing_inputs:
            missing_vars_str = ", ".join(sorted(missing_inputs))
            msg = (
                f"Missing input variable(s): {missing_vars_str}. These variables are used in the prompt or system_prompt but not declared in inputs."
            )
            raise ValueError(msg)

        if unused_inputs:
            unused_vars_str = ", ".join(sorted(unused_inputs))
            msg = (
                f"Unused input variable(s): {unused_vars_str}. "
                "These variables are declared in inputs but not referenced in the prompt or system_prompt."
            )
            raise ValueError(msg)

    @override
    def validate_output(self):
        pass
