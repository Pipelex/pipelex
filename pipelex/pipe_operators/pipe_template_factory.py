from typing import Literal, Optional

from typing_extensions import override

from pipelex.config import get_config
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.pipe_input_spec import PipeInputSpec
from pipelex.exceptions import PipeDefinitionError
from pipelex.pipe_operators.pipe_template import PipeTemplate
from pipelex.tools.templating.template_category import TemplateCategory
from pipelex.tools.templating.template_parsing import check_template_parsing
from pipelex.tools.templating.template_preprocessor import preprocess_template
from pipelex.tools.templating.templating_models import PromptingStyle


class PipeTemplateBlueprint(PipeBlueprint):
    type: Literal["PipeTemplate"] = "PipeTemplate"
    template_name: Optional[str] = None
    template: Optional[str] = None
    prompting_style: Optional[PromptingStyle] = None
    template_category: TemplateCategory = TemplateCategory.LLM_PROMPT


class PipeTemplateFactory(PipeFactoryProtocol[PipeTemplateBlueprint, PipeTemplate]):
    @classmethod
    @override
    def make_pipe_from_blueprint(
        cls,
        domain_code: str,
        pipe_code: str,
        pipe_blueprint: PipeTemplateBlueprint,
    ) -> PipeTemplate:
        preprocessed_template: Optional[str] = None
        if pipe_blueprint.template:
            preprocessed_template = preprocess_template(pipe_blueprint.template)
            check_template_parsing(
                template_source=preprocessed_template,
                template_category=pipe_blueprint.template_category,
            )
        else:
            preprocessed_template = None
        return PipeTemplate(
            domain=domain_code,
            code=pipe_code,
            definition=pipe_blueprint.definition,
            inputs=PipeInputSpec.make_from_blueprint(domain=domain_code, blueprint=pipe_blueprint.inputs or {}),
            output_concept_code=pipe_blueprint.output,
            template_name=pipe_blueprint.template_name,
            template=preprocessed_template,
            prompting_style=pipe_blueprint.prompting_style,
            template_category=pipe_blueprint.template_category,
        )

    @classmethod
    def make_pipe_template_from_template_str(
        cls,
        domain_code: str,
        inputs: Optional[PipeInputSpec] = None,
        template_str: Optional[str] = None,
        template_name: Optional[str] = None,
    ) -> PipeTemplate:
        if template_str:
            preprocessed_template = preprocess_template(template_str)
            check_template_parsing(
                template_source=preprocessed_template,
                template_category=TemplateCategory.LLM_PROMPT,
            )
            return PipeTemplate(
                domain=domain_code,
                code="adhoc_pipe_template_from_template_str",
                template=preprocessed_template,
                inputs=inputs or PipeInputSpec.make_empty(),
            )
        elif template_name:
            return PipeTemplate(
                domain=domain_code,
                code="adhoc_pipe_template_from_template_name",
                template_name=template_name,
                inputs=inputs or PipeInputSpec.make_empty(),
            )
        else:
            raise PipeDefinitionError("Either template_str or template_name must be provided to make_pipe_template_from_template_str")

    @classmethod
    def make_pipe_template_to_structure(
        cls,
        domain_code: str,
        prompt_template_to_structure: Optional[str],
    ) -> PipeTemplate:
        template_name = prompt_template_to_structure or get_config().pipelex.generic_template_names.structure_from_preliminary_text_user
        prompting_style = PromptingStyle.make_default_prompting_style()
        return PipeTemplate(
            domain=domain_code,
            code="adhoc_pipe_template_to_structure",
            template_name=template_name,
            prompting_style=prompting_style,
        )
