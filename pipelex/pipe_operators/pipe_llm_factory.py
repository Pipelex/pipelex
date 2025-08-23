from typing import List, Literal, Optional

from pydantic import model_validator
from typing_extensions import Self, override

from pipelex.cogt.llm.llm_models.llm_setting import LLMSettingChoices, LLMSettingOrPresetId
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NativeConceptEnum
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.pipe_input_spec import InputRequirementBlueprint
from pipelex.core.pipes.pipe_input_spec_factory import PipeInputSpecFactory
from pipelex.core.pipes.pipe_run_params import make_output_multiplicity
from pipelex.exceptions import PipeDefinitionError
from pipelex.hub import get_concept_provider, get_optional_domain
from pipelex.pipe_operators.pipe_jinja2_factory import PipeJinja2Blueprint, PipeJinja2Factory
from pipelex.pipe_operators.pipe_llm import PipeLLM, StructuringMethod
from pipelex.pipe_operators.pipe_llm_prompt import PipeLLMPrompt
from pipelex.tools.templating.jinja2_errors import Jinja2TemplateError
from pipelex.tools.templating.template_provider_abstract import TemplateNotFoundError
from pipelex.tools.typing.validation_utils import has_more_than_one_among_attributes_from_lists


class PipeLLMBlueprint(PipeBlueprint):
    type: Literal["PipeLLM"] = "PipeLLM"
    system_prompt_template: Optional[str] = None
    system_prompt_template_name: Optional[str] = None
    system_prompt_name: Optional[str] = None
    system_prompt: Optional[str] = None

    prompt_template: Optional[str] = None
    template_name: Optional[str] = None
    prompt_name: Optional[str] = None
    prompt: Optional[str] = None

    llm: Optional[LLMSettingOrPresetId] = None
    llm_to_structure: Optional[LLMSettingOrPresetId] = None

    structuring_method: Optional[StructuringMethod] = None
    prompt_template_to_structure: Optional[str] = None
    system_prompt_to_structure: Optional[str] = None

    nb_output: Optional[int] = None
    multiple_output: Optional[bool] = None

    @model_validator(mode="after")
    def validate_multiple_output(self) -> Self:
        if excess_attributes_list := has_more_than_one_among_attributes_from_lists(
            self,
            attributes_lists=[
                ["nb_output", "multiple_output"],
                ["system_prompt", "system_prompt_name", "system_prompt_template", "system_prompt_template_name"],
                ["prompt", "prompt_name", "prompt_template", "template_name"],
            ],
        ):
            raise PipeDefinitionError(f"PipeLLMBlueprint should have no more than one of {excess_attributes_list} among them")
        return self


class PipeLLMFactory(PipeFactoryProtocol[PipeLLMBlueprint, PipeLLM]):
    @classmethod
    @override
    def make_from_blueprint(
        cls,
        domain: str,
        pipe_code: str,
        pipe_blueprint: PipeLLMBlueprint,
        concept_codes_from_the_same_domain: Optional[List[str]] = None,
    ) -> PipeLLM:
        system_prompt_pipe_jinja2 = None
        system_prompt: Optional[str] = None
        if pipe_blueprint.system_prompt_template or pipe_blueprint.system_prompt_template_name:
            try:
                system_prompt_jinja2_blueprint = PipeJinja2Blueprint(
                    definition="System prompt template for LLM",
                    jinja2=pipe_blueprint.system_prompt_template,
                    jinja2_name=pipe_blueprint.system_prompt_template_name,
                    output=NativeConceptEnum.LLM_PROMPT.value,
                )

                system_prompt_pipe_jinja2 = PipeJinja2Factory.make_from_blueprint(
                    domain=domain,
                    pipe_code="adhoc_for_system_prompt",
                    pipe_blueprint=system_prompt_jinja2_blueprint,
                    concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
                )
            except Jinja2TemplateError as exc:
                error_msg = f"Jinja2 template error in system prompt for pipe '{pipe_code}' in domain '{domain}': {exc}."
                if pipe_blueprint.system_prompt_template:
                    error_msg += f"\nThe system prompt template is:\n{pipe_blueprint.system_prompt_template}"
                else:
                    error_msg += "The system prompt template is not provided."
                raise PipeDefinitionError(error_msg) from exc
        elif not pipe_blueprint.system_prompt and not pipe_blueprint.system_prompt_name:
            # really no system prompt provided, let's use the domain's default system prompt
            if domain_obj := get_optional_domain(domain=domain):
                system_prompt = domain_obj.system_prompt

        user_pipe_jinja2 = None
        if pipe_blueprint.prompt_template or pipe_blueprint.template_name:
            try:
                user_pipe_jinja2 = PipeJinja2Factory.make_pipe_jinja2_from_template_str(
                    domain=domain,
                    template_str=pipe_blueprint.prompt_template,
                    template_name=pipe_blueprint.template_name,
                    inputs=PipeInputSpecFactory.make_from_blueprint(
                        domain=domain, blueprint=pipe_blueprint.inputs or {}, concept_codes_from_the_same_domain=concept_codes_from_the_same_domain
                    ),
                )
            except Jinja2TemplateError as exc:
                error_msg = f"Jinja2 syntax error in user prompt for pipe '{pipe_code}' in domain '{domain}': {exc}."
                if pipe_blueprint.prompt_template:
                    error_msg += f"\nThe prompt template is:\n{pipe_blueprint.prompt_template}"
                else:
                    error_msg += "The prompt template is not provided."
                raise PipeDefinitionError(error_msg) from exc
        elif pipe_blueprint.prompt is None and pipe_blueprint.prompt_name is None:
            # no jinja2 provided, no verbatim name, no fixed text, let's try and use the pipe code as jinja2 name
            try:
                user_prompt_jinja2_blueprint = PipeJinja2Blueprint(
                    definition="User prompt template for LLM",
                    jinja2_name=pipe_code,
                    output=NativeConceptEnum.LLM_PROMPT.value,
                )

                user_pipe_jinja2 = PipeJinja2Factory.make_from_blueprint(
                    domain=domain,
                    pipe_code="adhoc_for_user_prompt",
                    pipe_blueprint=user_prompt_jinja2_blueprint,
                )
            except TemplateNotFoundError as exc:
                error_msg = f"Jinja2 template not found for pipe '{pipe_code}' in domain '{domain}': {exc}."
                raise PipeDefinitionError(error_msg) from exc

        user_images: List[str] = []
        if pipe_blueprint.inputs:
            for stuff_name, requirement in pipe_blueprint.inputs.items():
                if isinstance(requirement, str):
                    requirement = InputRequirementBlueprint(concept_string_or_concept_code=requirement)
                concept_string_or_concept_code = requirement.concept_string_or_concept_code
                concept_domain, concept_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_concept_code(
                    domain=domain,
                    concept_string_or_concept_code=concept_string_or_concept_code,
                    concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
                )
                concept = get_concept_provider().get_required_concept(
                    concept_string=ConceptFactory.construct_concept_string_with_domain(domain=concept_domain, concept_code=concept_code)
                )

                if get_concept_provider().is_image_concept(concept=concept):
                    user_images.append(stuff_name)

        pipe_llm_prompt = PipeLLMPrompt(
            code="adhoc_for_pipe_llm_prompt",
            domain=domain,
            inputs=PipeInputSpecFactory.make_from_blueprint(
                domain=domain, blueprint=pipe_blueprint.inputs or {}, concept_codes_from_the_same_domain=concept_codes_from_the_same_domain
            ),
            system_prompt_pipe_jinja2=system_prompt_pipe_jinja2,
            system_prompt_verbatim_name=pipe_blueprint.system_prompt_name,
            system_prompt=pipe_blueprint.system_prompt or system_prompt,
            user_pipe_jinja2=user_pipe_jinja2,
            user_prompt_verbatim_name=pipe_blueprint.prompt_name,
            user_text=pipe_blueprint.prompt,
            user_images=user_images or None,
        )

        llm_choices = LLMSettingChoices(
            for_text=pipe_blueprint.llm,
            for_object=pipe_blueprint.llm_to_structure,
        )

        # output_multiplicity defaults to False for PipeLLM so unless it's run with explicit demand for multiple outputs,
        # we'll generate only one output
        output_multiplicity = make_output_multiplicity(
            nb_output=pipe_blueprint.nb_output,
            multiple_output=pipe_blueprint.multiple_output,
        )

        output_concept_domain, output_concept_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_concept_code(
            domain=domain,
            concept_string_or_concept_code=pipe_blueprint.output,
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )
        return PipeLLM(
            domain=domain,
            code=pipe_code,
            definition=pipe_blueprint.definition,
            inputs=PipeInputSpecFactory.make_from_blueprint(
                domain=domain, blueprint=pipe_blueprint.inputs or {}, concept_codes_from_the_same_domain=concept_codes_from_the_same_domain
            ),
            output=get_concept_provider().get_required_concept(
                concept_string=ConceptFactory.construct_concept_string_with_domain(domain=output_concept_domain, concept_code=output_concept_code)
            ),
            pipe_llm_prompt=pipe_llm_prompt,
            llm_choices=llm_choices,
            structuring_method=pipe_blueprint.structuring_method,
            prompt_template_to_structure=pipe_blueprint.prompt_template_to_structure,
            system_prompt_to_structure=pipe_blueprint.system_prompt_to_structure,
            output_multiplicity=output_multiplicity,
        )
