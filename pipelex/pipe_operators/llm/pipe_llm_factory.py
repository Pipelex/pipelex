from typing_extensions import override

from pipelex.cogt.llm.llm_prompt_spec import LLMPromptSpec
from pipelex.cogt.llm.llm_setting import LLMSettingChoices
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.core.pipes.input_requirement_blueprint import InputRequirementBlueprint
from pipelex.core.pipes.input_requirements_factory import InputRequirementsFactory
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.exceptions import PipeDefinitionError
from pipelex.hub import get_native_concept, get_optional_domain, get_required_concept
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_run.pipe_run_params import make_output_multiplicity
from pipelex.tools.templating.jinja2_blueprint import Jinja2Blueprint
from pipelex.tools.templating.jinja2_errors import Jinja2TemplateError


class PipeLLMFactory(PipeFactoryProtocol[PipeLLMBlueprint, PipeLLM]):
    @classmethod
    @override
    def make_from_blueprint(
        cls,
        domain: str,
        pipe_code: str,
        blueprint: PipeLLMBlueprint,
        concept_codes_from_the_same_domain: list[str] | None = None,
    ) -> PipeLLM:
        system_prompt_jinja2_blueprint: Jinja2Blueprint | None = None
        system_prompt: str | None = None
        if blueprint.system_prompt_template or blueprint.system_prompt_template_name:
            try:
                system_prompt_jinja2_blueprint = Jinja2Blueprint(
                    jinja2=blueprint.system_prompt_template,
                    jinja2_name=blueprint.system_prompt_template_name,
                )
            except Jinja2TemplateError as exc:
                error_msg = f"Jinja2 template error in system prompt for pipe '{pipe_code}' in domain '{domain}': {exc}."
                if blueprint.system_prompt_template:
                    error_msg += f"\nThe system prompt template is:\n{blueprint.system_prompt_template}"
                else:
                    error_msg += "The system prompt template is not provided."
                raise PipeDefinitionError(error_msg) from exc
        elif not blueprint.system_prompt and not blueprint.system_prompt_name:
            # really no system prompt provided, let's use the domain's default system prompt
            if domain_obj := get_optional_domain(domain=domain):
                system_prompt = domain_obj.system_prompt

        user_text_jinja2_blueprint: Jinja2Blueprint | None = None
        if blueprint.prompt_template or blueprint.template_name:
            try:
                user_text_jinja2_blueprint = Jinja2Blueprint(
                    jinja2=blueprint.prompt_template,
                    jinja2_name=blueprint.template_name,
                )
            except Jinja2TemplateError as exc:
                error_msg = f"Jinja2 syntax error in user prompt for pipe '{pipe_code}' in domain '{domain}': {exc}."
                if blueprint.prompt_template:
                    error_msg += f"\nThe prompt template is:\n{blueprint.prompt_template}"
                else:
                    error_msg += "The prompt template is not provided."
                raise PipeDefinitionError(error_msg) from exc

        user_images: list[str] = []
        if blueprint.inputs:
            for stuff_name, requirement in blueprint.inputs.items():
                if isinstance(requirement, str):
                    # if it's just a concept string, it's a concept, we make a basic input requirement from it
                    input_requirement_blueprint = InputRequirementBlueprint(concept=requirement)
                else:
                    input_requirement_blueprint = requirement

                concept_string = input_requirement_blueprint.concept
                domain_and_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_code(
                    domain=domain,
                    concept_string_or_code=concept_string,
                    concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
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

        llm_prompt_spec = LLMPromptSpec(
            system_prompt_jinja2_blueprint=system_prompt_jinja2_blueprint,
            system_prompt_verbatim_name=blueprint.system_prompt_name,
            system_prompt=blueprint.system_prompt or system_prompt,
            user_text_jinja2_blueprint=user_text_jinja2_blueprint,
            user_prompt_verbatim_name=blueprint.prompt_name,
            user_text=blueprint.prompt,
            user_images=user_images or None,
        )

        llm_choices = LLMSettingChoices(
            for_text=blueprint.llm,
            for_object=blueprint.llm_to_structure,
        )

        # output_multiplicity defaults to False for PipeLLM so unless it's run with explicit demand for multiple outputs,
        # we'll generate only one output
        output_multiplicity = make_output_multiplicity(
            nb_output=blueprint.nb_output,
            multiple_output=blueprint.multiple_output,
        )

        output_domain_and_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_code(
            domain=domain,
            concept_string_or_code=blueprint.output,
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )
        output_concept_domain, output_concept_code = output_domain_and_code.domain, output_domain_and_code.concept_code
        return PipeLLM(
            domain=domain,
            code=pipe_code,
            description=blueprint.description,
            inputs=InputRequirementsFactory.make_from_blueprint(
                domain=domain,
                blueprint=blueprint.inputs or {},
                concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
            ),
            output=get_required_concept(
                concept_string=ConceptFactory.make_concept_string_with_domain(domain=output_concept_domain, concept_code=output_concept_code),
            ),
            llm_prompt_spec=llm_prompt_spec,
            llm_choices=llm_choices,
            structuring_method=blueprint.structuring_method,
            prompt_template_to_structure=blueprint.prompt_template_to_structure,
            system_prompt_to_structure=blueprint.system_prompt_to_structure,
            output_multiplicity=output_multiplicity,
        )
