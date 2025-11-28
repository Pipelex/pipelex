from typing import Any

from pydantic import ValidationError
from typing_extensions import override

from pipelex.cogt.llm.llm_setting import LLMSettingChoices
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.inputs.input_requirements import InputRequirements
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.variable_multiplicity import make_variable_multiplicity, parse_concept_with_multiplicity
from pipelex.hub import get_native_concept, get_optional_domain, get_required_concept
from pipelex.pipe_operators.llm.exceptions import PipeLLMFactoryError
from pipelex.pipe_operators.llm.llm_prompt_blueprint import LLMPromptBlueprint
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.tools.jinja2.jinja2_errors import Jinja2TemplateSyntaxError


class PipeLLMFactory(PipeFactoryProtocol[PipeLLMBlueprint, PipeLLM]):
    @classmethod
    @override
    def make(
        cls,
        pipe_category: Any,
        pipe_type: str,
        pipe_code: str,
        domain_code: str,
        description: str | None,
        inputs: InputRequirements,
        output: Concept,
        blueprint: PipeLLMBlueprint,
    ) -> PipeLLM:
        system_prompt = blueprint.system_prompt
        if not system_prompt and (domain_obj := get_optional_domain(domain=domain_code)):
            system_prompt = domain_obj.system_prompt

        system_prompt_jinja2_blueprint: TemplateBlueprint | None = None
        if system_prompt:
            try:
                system_prompt_jinja2_blueprint = TemplateBlueprint(
                    template=system_prompt,
                    category=TemplateCategory.LLM_PROMPT,
                )
            except ValidationError as exc:
                error_msg = (
                    f"Template syntax error in system prompt for pipe '{pipe_code}'"
                    f"in domain '{domain_code}': {exc}. Template source:\n{blueprint.system_prompt}"
                )
                raise PipeLLMFactoryError(error_msg) from exc

        user_text_jinja2_blueprint: TemplateBlueprint | None = None
        if blueprint.prompt:
            try:
                user_text_jinja2_blueprint = TemplateBlueprint(
                    template=blueprint.prompt,
                    category=TemplateCategory.LLM_PROMPT,
                )
            except Jinja2TemplateSyntaxError as exc:
                error_msg = (
                    f"Template syntax error in user prompt for pipe '{pipe_code}' in domain '{domain_code}': "
                    f"{exc}. Template source:\n{blueprint.prompt}"
                )
                raise PipeLLMFactoryError(error_msg) from exc

        user_images: list[str] = []
        if blueprint.inputs:
            for stuff_name, requirement_str in blueprint.inputs.items():
                # Parse to strip multiplicity brackets
                input_parse_result = parse_concept_with_multiplicity(requirement_str)

                domain_and_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_code(
                    domain=domain_code,
                    concept_string_or_code=input_parse_result.concept,
                )
                concept = get_required_concept(
                    concept_string=ConceptFactory.make_concept_string_with_domain(
                        domain=domain_and_code.domain,
                        concept_code=domain_and_code.concept_code,
                    ),
                )

                if Concept.are_concept_compatible(concept_1=concept, concept_2=get_native_concept(NativeConceptCode.IMAGE), strict=True):
                    user_images.append(stuff_name)
                elif Concept.are_concept_compatible(concept_1=concept, concept_2=get_native_concept(NativeConceptCode.IMAGE), strict=False):
                    # Get image field paths relative to the concept
                    image_field_paths = concept.search_for_nested_image_fields_in_structure_class()
                    # Prefix each path with the stuff_name to make them absolute
                    for field_path in image_field_paths:
                        user_images.append(f"{stuff_name}.{field_path}")

        llm_prompt_spec = LLMPromptBlueprint(
            system_prompt_blueprint=system_prompt_jinja2_blueprint,
            prompt_blueprint=user_text_jinja2_blueprint,
            user_images=user_images or None,
        )

        llm_choices = LLMSettingChoices(
            for_text=blueprint.model,
            for_object=blueprint.model_to_structure,
        )

        # Parse output for multiplicity (may have brackets like "Text[]" or "Text[3]")
        output_parse_result = parse_concept_with_multiplicity(blueprint.output)

        # Convert bracket notation to output_multiplicity
        output_multiplicity = make_variable_multiplicity(
            nb_items=output_parse_result.multiplicity if isinstance(output_parse_result.multiplicity, int) else None,
            multiple_items=output_parse_result.multiplicity if isinstance(output_parse_result.multiplicity, bool) else None,
        )

        return PipeLLM(
            domain=domain_code,
            code=pipe_code,
            description=description,
            inputs=inputs,
            output=output,
            llm_prompt_spec=llm_prompt_spec,
            llm_choices=llm_choices,
            structuring_method=blueprint.structuring_method,
            output_multiplicity=output_multiplicity,
        )
