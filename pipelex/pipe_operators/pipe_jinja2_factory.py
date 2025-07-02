from typing import Any, Dict, Optional

from typing_extensions import override

from pipelex.config import get_config
from pipelex.core.pipe_blueprint import PipeBlueprint, PipeSpecificFactoryProtocol
from pipelex.core.pipe_input_spec import PipeInputSpec
from pipelex.exceptions import PipeDefinitionError
from pipelex.pipe_operators.pipe_jinja2 import PipeJinja2
from pipelex.tools.templating.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.templating.jinja2_template_category import Jinja2TemplateCategory
from pipelex.tools.templating.template_preprocessor import preprocess_template
from pipelex.tools.templating.templating_models import PromptingStyle


class PipeJinja2Blueprint(PipeBlueprint):
    jinja2_name: Optional[str] = None
    jinja2: Optional[str] = None
    prompting_style: Optional[PromptingStyle] = None
    template_category: Jinja2TemplateCategory = Jinja2TemplateCategory.LLM_PROMPT


class PipeJinja2Factory(PipeSpecificFactoryProtocol[PipeJinja2Blueprint, PipeJinja2]):
    @classmethod
    @override
    def make_pipe_from_blueprint(
        cls,
        domain_code: str,
        pipe_code: str,
        pipe_blueprint: PipeJinja2Blueprint,
    ) -> PipeJinja2:
        preprocessed_template: Optional[str] = None
        if pipe_blueprint.jinja2:
            preprocessed_template = preprocess_template(pipe_blueprint.jinja2)
            check_jinja2_parsing(
                jinja2_template_source=preprocessed_template,
                template_category=pipe_blueprint.template_category,
            )
        else:
            preprocessed_template = None
        return PipeJinja2(
            domain=domain_code,
            code=pipe_code,
            definition=pipe_blueprint.definition,
            inputs=PipeInputSpec(root=pipe_blueprint.inputs or {}),
            output_concept_code=pipe_blueprint.output,
            jinja2_name=pipe_blueprint.jinja2_name,
            jinja2=preprocessed_template,
            prompting_style=pipe_blueprint.prompting_style,
            template_category=pipe_blueprint.template_category,
        )

    @classmethod
    @override
    def make_pipe_from_details_dict(
        cls,
        domain_code: str,
        pipe_code: str,
        details_dict: Dict[str, Any],
    ) -> PipeJinja2:
        pipe_blueprint = PipeJinja2Blueprint.model_validate(details_dict)
        return cls.make_pipe_from_blueprint(
            domain_code=domain_code,
            pipe_code=pipe_code,
            pipe_blueprint=pipe_blueprint,
        )

    @classmethod
    def make_pipe_jinja2_from_template_str(
        cls,
        domain_code: str,
        inputs: Optional[PipeInputSpec] = None,
        template_str: Optional[str] = None,
        template_name: Optional[str] = None,
    ) -> PipeJinja2:
        if template_str:
            preprocessed_template = preprocess_template(template_str)
            check_jinja2_parsing(
                jinja2_template_source=preprocessed_template,
                template_category=Jinja2TemplateCategory.LLM_PROMPT,
            )
            return PipeJinja2(
                domain=domain_code,
                code="adhoc_pipe_jinja2_from_template_str",
                jinja2=preprocessed_template,
                inputs=inputs or PipeInputSpec.make_empty(),
            )
        elif template_name:
            return PipeJinja2(
                domain=domain_code,
                code="adhoc_pipe_jinja2_from_template_name",
                jinja2_name=template_name,
                inputs=inputs or PipeInputSpec.make_empty(),
            )
        else:
            raise PipeDefinitionError("Either template_str or template_name must be provided to make_pipe_jinja2_from_template_str")

    @classmethod
    def make_pipe_jinja2_to_structure(
        cls,
        domain_code: str,
        prompt_template_to_structure: Optional[str],
    ) -> PipeJinja2:
        jinja2_name = prompt_template_to_structure or get_config().pipelex.generic_template_names.structure_from_preliminary_text_user
        prompting_style = PromptingStyle.make_default_prompting_style()
        return PipeJinja2(
            domain=domain_code,
            code="adhoc_pipe_jinja2_to_structure",
            jinja2_name=jinja2_name,
            prompting_style=prompting_style,
        )
