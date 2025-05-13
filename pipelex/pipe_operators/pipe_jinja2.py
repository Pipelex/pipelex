# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Any, ClassVar, Dict, Optional, Self, Set

import shortuuid
from jinja2 import TemplateSyntaxError
from pydantic import ConfigDict, model_validator
from typing_extensions import override

from pipelex import log
from pipelex.core.domain import SpecialDomain
from pipelex.core.pipe import (
    PipeAbstract,
    update_job_metadata_for_pipe,
)
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import PipeRunParams
from pipelex.core.stuff import Stuff
from pipelex.core.stuff_content import TextContent
from pipelex.core.working_memory import WorkingMemory
from pipelex.exceptions import PipeDefinitionError, PipeRunParamsError
from pipelex.hub import get_content_generator, get_template, get_template_provider
from pipelex.job_metadata import JobMetadata
from pipelex.tools.templating.jinja2_errors import Jinja2TemplateError
from pipelex.tools.templating.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.templating.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.templating.jinja2_template_category import Jinja2TemplateCategory
from pipelex.tools.templating.templating_models import PromptingStyle
from pipelex.tools.utils.validation_utils import has_exactly_one_among_attributes_from_list


class PipeJinja2Output(PipeOutput):
    @property
    def rendered_text(self) -> str:
        return self.main_stuff_as_text.text


class PipeJinja2(PipeAbstract):
    model_config = ConfigDict(extra="forbid", strict=False)

    adhoc_pipe_code: ClassVar[str] = "jinja2_render"
    output_concept_code: str = f"{SpecialDomain.NATIVE}.Text"

    jinja2_name: Optional[str] = None
    jinja2: Optional[str] = None
    prompting_style: Optional[PromptingStyle] = None
    template_category: Jinja2TemplateCategory = Jinja2TemplateCategory.LLM_PROMPT

    @model_validator(mode="after")
    def validate_jinja2(self) -> Self:
        if not has_exactly_one_among_attributes_from_list(self, attributes_list=["jinja2_name", "jinja2"]):
            raise PipeDefinitionError("PipeJinja2 should have exactly one of jinja2_name or jinja2")
        if self.jinja2:
            try:
                check_jinja2_parsing(jinja2_template_source=self.jinja2, template_category=self.template_category)
            except TemplateSyntaxError as exc:
                raise Jinja2TemplateError(f"Could not parse Jinja2 template included in PipeJinja2: {exc}") from exc
        return self

    @override
    def validate_with_libraries(self):
        if self.jinja2_name:
            the_template = get_template(template_name=self.jinja2_name)
            log.debug(f"Validated jinja2 template '{self.jinja2_name}':\n{the_template}")

    @property
    def desc(self) -> str:
        if self.jinja2:
            return f"Jinja2 included template, prompting style {self.prompting_style}"
        elif jinja2_name := self.jinja2_name:
            return f"Jinja2 template '{jinja2_name}', prompting style {self.prompting_style}"
        else:
            return "Jinja2 template not defined"

    @override
    def required_variables(self) -> Set[str]:
        required_variables = detect_jinja2_required_variables(
            template_category=self.template_category,
            template_provider=get_template_provider(),
            jinja2_name=self.jinja2_name,
            jinja2=self.jinja2,
        )
        return required_variables

    @override
    @update_job_metadata_for_pipe
    async def run_pipe(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        pipe_code: str,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeJinja2Output:
        if pipe_run_params.is_multiple_output_required:
            raise PipeRunParamsError(
                f"PipeJinja2 does not suppport multiple outputs, got output_multiplicity = {pipe_run_params.output_multiplicity}"
            )
        if not self.output_concept_code:
            raise PipeRunParamsError("PipeJinja2 must have an output_concept_code")

        context: Dict[str, Any] = working_memory.generate_stuff_artefact_dict()
        if pipe_run_params:
            context.update(**pipe_run_params.params)

        jinja2_text = await get_content_generator().make_jinja2_text(
            context=context,
            jinja2_name=self.jinja2_name,
            jinja2=self.jinja2,
            prompting_style=self.prompting_style,
            template_category=self.template_category,
        )
        log.verbose(f"Jinja2 rendered text:\n{jinja2_text}")
        assert isinstance(jinja2_text, str)
        the_content = TextContent(text=jinja2_text)

        output_stuff = Stuff(
            concept_code=self.output_concept_code,
            content=the_content,
            stuff_name=output_name,
            stuff_code=shortuuid.uuid()[:5],
        )

        working_memory.set_new_main_stuff(
            stuff=output_stuff,
            name=output_name,
        )

        pipe_output = PipeJinja2Output(
            working_memory=working_memory,
        )

        return pipe_output
