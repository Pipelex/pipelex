from typing import Any

from pydantic import ValidationError
from typing_extensions import override

from pipelex.cogt.llm.llm_setting import LLMSettingChoices
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.pipes.variable_multiplicity import make_variable_multiplicity, parse_concept_with_multiplicity
from pipelex.hub import get_optional_domain
from pipelex.pipe_operators.llm.exceptions import PipeLLMFactoryError
from pipelex.pipe_operators.llm.llm_prompt_blueprint import LLMPromptBlueprint
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_operators.llm.template_document_analyzer import TemplateDocumentAnalyzer
from pipelex.pipe_operators.llm.template_image_analyzer import TemplateImageAnalyzer
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
        description: str,
        inputs: InputStuffSpecs,
        output: StuffSpec,
        blueprint: PipeLLMBlueprint,
    ) -> PipeLLM:
        system_prompt = blueprint.system_prompt
        if not system_prompt and (domain_obj := get_optional_domain(domain_code=domain_code)):
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

        # Analyze template for image references
        user_image_references = None
        if blueprint.prompt and blueprint.inputs:
            user_image_references = (
                TemplateImageAnalyzer.analyze_template_for_images(
                    template_source=blueprint.prompt,
                    input_specs=blueprint.inputs,
                    domain_code=domain_code,
                )
                or None
            )

        # Analyze template for document references
        user_document_references = None
        if blueprint.prompt and blueprint.inputs:
            user_document_references = (
                TemplateDocumentAnalyzer.analyze_template_for_documents(
                    template_source=blueprint.prompt,
                    input_specs=blueprint.inputs,
                    domain_code=domain_code,
                )
                or None
            )

        # Analyze system prompt for image references
        system_image_references = None
        if blueprint.system_prompt and blueprint.inputs:
            system_image_references = (
                TemplateImageAnalyzer.analyze_template_for_images(
                    template_source=blueprint.system_prompt,
                    input_specs=blueprint.inputs,
                    domain_code=domain_code,
                )
                or None
            )

        # Analyze system prompt for document references
        system_document_references = None
        if blueprint.system_prompt and blueprint.inputs:
            system_document_references = (
                TemplateDocumentAnalyzer.analyze_template_for_documents(
                    template_source=blueprint.system_prompt,
                    input_specs=blueprint.inputs,
                    domain_code=domain_code,
                )
                or None
            )

        llm_prompt_spec = LLMPromptBlueprint(
            system_prompt_blueprint=system_prompt_jinja2_blueprint,
            prompt_blueprint=user_text_jinja2_blueprint,
            user_image_references=user_image_references,
            user_document_references=user_document_references,
            system_image_references=system_image_references,
            system_document_references=system_document_references,
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
            domain_code=domain_code,
            code=pipe_code,
            description=description,
            inputs=inputs,
            output=output,
            llm_prompt_spec=llm_prompt_spec,
            llm_choices=llm_choices,
            structuring_method=blueprint.structuring_method,
            output_multiplicity=output_multiplicity,
        )
