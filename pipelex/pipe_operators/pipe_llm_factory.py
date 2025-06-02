from typing import Any, Dict, List, Optional

from pydantic import model_validator
from typing_extensions import Self, override

from pipelex.cogt.llm.llm_models.llm_deck import LLMSettingChoices
from pipelex.cogt.llm.llm_models.llm_setting import LLMSettingOrPresetId
from pipelex.core.pipe_blueprint import PipeBlueprint, PipeSpecificFactoryProtocol
from pipelex.core.pipe_run_params import make_output_multiplicity
from pipelex.exceptions import PipeDefinitionError
from pipelex.hub import get_optional_domain
from pipelex.pipe_operators.pipe_jinja2 import PipeJinja2
from pipelex.pipe_operators.pipe_jinja2_factory import PipeJinja2Factory
from pipelex.pipe_operators.pipe_llm import PipeLLM, StructuringMethod
from pipelex.pipe_operators.pipe_llm_prompt import PipeLLMPrompt
from pipelex.tools.templating.jinja2_errors import Jinja2TemplateError
from pipelex.tools.typing.validation_utils import has_more_than_one_among_attributes_from_lists


class PipeLLMBlueprint(PipeBlueprint):
    system_prompt_template: Optional[str] = None
    system_prompt_template_name: Optional[str] = None
    system_prompt_name: Optional[str] = None
    system_prompt: Optional[str] = None

    prompt_template: Optional[str] = None
    template_name: Optional[str] = None
    prompt_name: Optional[str] = None
    prompt: Optional[str] = None

    images: Optional[List[str]] = None

    llm: Optional[LLMSettingOrPresetId] = None
    llm_to_structure: Optional[LLMSettingOrPresetId] = None
    llm_to_structure_direct: Optional[LLMSettingOrPresetId] = None
    llm_to_structure_list: Optional[LLMSettingOrPresetId] = None
    llm_to_structure_list_direct: Optional[LLMSettingOrPresetId] = None

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


class PipeLLMFactory(PipeSpecificFactoryProtocol[PipeLLMBlueprint, PipeLLM]):
    @classmethod
    @override
    def make_pipe_from_blueprint(
        cls,
        domain_code: str,
        pipe_code: str,
        pipe_blueprint: PipeLLMBlueprint,
    ) -> PipeLLM:
        system_prompt_pipe_jinja2: Optional[PipeJinja2] = None
        system_prompt: Optional[str] = None
        if pipe_blueprint.system_prompt_template or pipe_blueprint.system_prompt_template_name:
            try:
                system_prompt_pipe_jinja2 = PipeJinja2(
                    code="adhoc_for_system_prompt",
                    domain=domain_code,
                    jinja2=pipe_blueprint.system_prompt_template,
                    jinja2_name=pipe_blueprint.system_prompt_template_name,
                )
            except Jinja2TemplateError as exc:
                error_msg = f"Jinja2 template error in system prompt for pipe '{pipe_code}' in domain '{domain_code}': {exc}."
                if pipe_blueprint.system_prompt_template:
                    error_msg += f"\nThe system prompt template is:\n{pipe_blueprint.system_prompt_template}"
                else:
                    error_msg += "The system prompt template is not provided."
                raise PipeDefinitionError(error_msg) from exc
        elif not pipe_blueprint.system_prompt and not pipe_blueprint.system_prompt_name:
            # really no system prompt provided, let's use the domain's default system prompt
            if domain := get_optional_domain(domain_code=domain_code):
                system_prompt = domain.system_prompt

        user_pipe_jinja2: Optional[PipeJinja2] = None
        if pipe_blueprint.prompt_template or pipe_blueprint.template_name:
            try:
                user_pipe_jinja2 = PipeJinja2Factory.make_pipe_jinja2_from_template_str(
                    domain_code=domain_code,
                    template_str=pipe_blueprint.prompt_template,
                    template_name=pipe_blueprint.template_name,
                )
            except Jinja2TemplateError as exc:
                error_msg = f"Jinja2 syntax error in user prompt for pipe '{pipe_code}' in domain '{domain_code}': {exc}."
                if pipe_blueprint.prompt_template:
                    error_msg += f"\nThe prompt template is:\n{pipe_blueprint.prompt_template}"
                else:
                    error_msg += "The prompt template is not provided."
                raise PipeDefinitionError(error_msg) from exc
        elif pipe_blueprint.prompt is None and pipe_blueprint.prompt_name is None:
            # no jinja2 provided, no verbatim name, no fixed text, let's use the pipe code as jinja2 name
            user_pipe_jinja2 = PipeJinja2(
                code="adhoc_for_user_prompt",
                domain=domain_code,
                jinja2_name=pipe_code,
            )

        pipe_llm_prompt = PipeLLMPrompt(
            code="adhoc_for_pipe_llm_prompt",
            domain=domain_code,
            system_prompt_pipe_jinja2=system_prompt_pipe_jinja2,
            system_prompt_verbatim_name=pipe_blueprint.system_prompt_name,
            system_prompt=pipe_blueprint.system_prompt or system_prompt,
            user_pipe_jinja2=user_pipe_jinja2,
            user_prompt_verbatim_name=pipe_blueprint.prompt_name,
            user_text=pipe_blueprint.prompt,
            user_images=pipe_blueprint.images,
        )

        llm_settings = LLMSettingChoices(
            for_text=pipe_blueprint.llm,
            for_object=pipe_blueprint.llm_to_structure,
            for_object_direct=pipe_blueprint.llm_to_structure_direct,
            for_object_list=pipe_blueprint.llm_to_structure_list,
            for_object_list_direct=pipe_blueprint.llm_to_structure_list_direct,
        )

        # output_multiplicity defaults to False for PipeLLM so unless it's run with explicit demand for multiple outputs,
        # we'll generate only one output
        output_multiplicity = make_output_multiplicity(
            nb_output=pipe_blueprint.nb_output,
            multiple_output=pipe_blueprint.multiple_output,
        )
        return PipeLLM(
            domain=domain_code,
            code=pipe_code,
            definition=pipe_blueprint.definition,
            input_concept_code=pipe_blueprint.input,
            output_concept_code=pipe_blueprint.output,
            pipe_llm_prompt=pipe_llm_prompt,
            llm_choices=llm_settings,
            structuring_method=pipe_blueprint.structuring_method,
            prompt_template_to_structure=pipe_blueprint.prompt_template_to_structure,
            system_prompt_to_structure=pipe_blueprint.system_prompt_to_structure,
            output_multiplicity=output_multiplicity,
        )

    @classmethod
    @override
    def make_pipe_from_details_dict(
        cls,
        domain_code: str,
        pipe_code: str,
        details_dict: Dict[str, Any],
    ) -> PipeLLM:
        pipe_blueprint = PipeLLMBlueprint.model_validate(details_dict)
        return cls.make_pipe_from_blueprint(
            domain_code=domain_code,
            pipe_code=pipe_code,
            pipe_blueprint=pipe_blueprint,
        )
