from typing import Literal

from pydantic import model_validator
from typing_extensions import override

from pipelex.cogt.llm.llm_setting import LLMModelChoice
from pipelex.cogt.templating.exceptions import TemplateSigilSyntaxError
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.core.pipes.validation import is_input_used_by_variables, is_variable_satisfied_by_inputs
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.tools.jinja2.exceptions import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.misc.string_utils import get_root_from_dotted_path
from pipelex.types import Self, StrEnum


class StructuringMethod(StrEnum):
    DIRECT = "direct"
    PRELIMINARY_TEXT = "preliminary_text"

    @property
    def is_preliminary_text(self) -> bool:
        match self:
            case StructuringMethod.PRELIMINARY_TEXT:
                return True
            case StructuringMethod.DIRECT:
                return False


class PipeLLMBlueprint(PipeBlueprint):
    type: Literal["PipeLLM"] = "PipeLLM"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"

    model: LLMModelChoice | None = None
    model_to_structure: LLMModelChoice | None = None

    system_prompt: str | None = None
    prompt: str | None = None

    structuring_method: StructuringMethod | None = None

    @model_validator(mode="after")
    def validate_preliminary_text_output(self) -> Self:
        # Same string-level guard the elaborator runs — surfaced at authoring time so
        # ValidationError is raised before bundle elaboration runs.
        if self.structuring_method is None or not self.structuring_method.is_preliminary_text:
            return self
        output_parse_result = parse_concept_with_multiplicity(self.output)
        if QualifiedRef.parse(output_parse_result.concept_ref_or_code).local_code == NativeConceptCode.TEXT:
            msg = (
                f"PipeLLM with `structuring_method = preliminary_text` cannot have output `{self.output}`. "
                "The output must be a structured concept, not Text."
            )
            raise ValueError(msg)
        return self

    @override
    def validate_inputs(self):
        # Get all required variable paths from prompt and system_prompt (full dotted paths)
        required_variable_paths: set[str] = set()

        declared_inputs: set[str] = set(self.inputs.keys()) if self.inputs else set()

        if self.prompt:
            try:
                preprocessed_template = preprocess_template(self.prompt, declared_inputs=declared_inputs)
            except TemplateSigilSyntaxError as exc:
                msg = f"Template sigil error in PipeLLM prompt: {exc}"
                raise ValueError(msg) from exc
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
            try:
                preprocessed_system_template = preprocess_template(self.system_prompt, declared_inputs=declared_inputs)
            except TemplateSigilSyntaxError as exc:
                msg = f"Template sigil error in PipeLLM system_prompt: {exc}"
                raise ValueError(msg) from exc
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
            var for var in required_variable_paths if not var.startswith("_") and get_root_from_dotted_path(var) != "place_holder"
        }

        # Find variables used in prompts but not satisfied by any input
        missing_inputs = {var_path for var_path in filtered_variable_paths if not is_variable_satisfied_by_inputs(var_path, declared_inputs)}

        # Find inputs declared but not used by any variable path
        unused_inputs = {input_name for input_name in declared_inputs if not is_input_used_by_variables(input_name, filtered_variable_paths)}

        if missing_inputs:
            missing_vars_str = ", ".join(sorted(missing_inputs))
            msg = (
                f"Missing input variable(s): {missing_vars_str}. These variables are used in the prompt or system_prompt but not declared in inputs."
            )
            raise ValueError(msg)

        if unused_inputs:
            unused_vars_str = ", ".join(sorted(unused_inputs))
            msg = (
                f"Unused input variable(s): '{unused_vars_str}'. "
                "These variables are declared in inputs but not referenced in the prompt or system_prompt."
            )
            raise ValueError(msg)

    @override
    def validate_output(self):
        pass
