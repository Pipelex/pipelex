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


def _is_variable_satisfied_by_inputs(variable_path: str, input_names: set[str]) -> bool:
    """Check if a variable path is satisfied by the declared inputs.

    A variable path is satisfied if:
    - It exactly matches an input name, OR
    - Its root (or any prefix) matches an input name (attribute access on an input)

    Args:
        variable_path: The full dotted variable path (e.g., 'page.text_and_images.text')
        input_names: Set of declared input names

    Returns:
        True if the variable path is satisfied by the inputs.
    """
    # Check for exact match
    if variable_path in input_names:
        return True

    # Check if any prefix of the path matches an input name
    parts = variable_path.split(".")
    for idx in range(1, len(parts)):
        prefix = ".".join(parts[:idx])
        if prefix in input_names:
            return True

    return False


def _is_input_used_by_variables(input_name: str, variable_paths: set[str]) -> bool:
    """Check if an input is used by any of the variable paths.

    An input is considered used if:
    - It exactly matches a variable path, OR
    - It is a prefix of any variable path (the input is accessed via attributes)

    Args:
        input_name: The declared input name
        variable_paths: Set of full dotted variable paths used in the template

    Returns:
        True if the input is used by any variable path.
    """
    for var_path in variable_paths:
        # Exact match
        if var_path == input_name:
            return True
        # Input is a prefix of the variable path
        if var_path.startswith(input_name + "."):
            return True
    return False


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
            var for var in required_variable_paths if not var.startswith("_") and var.split(".")[0] not in {"preliminary_text", "place_holder"}
        }

        input_names: set[str] = set(self.inputs.keys()) if self.inputs else set()

        # Find variables used in prompts but not satisfied by any input
        missing_inputs = {var_path for var_path in filtered_variable_paths if not _is_variable_satisfied_by_inputs(var_path, input_names)}

        # Find inputs declared but not used by any variable path
        unused_inputs = {input_name for input_name in input_names if not _is_input_used_by_variables(input_name, filtered_variable_paths)}

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
