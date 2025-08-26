from typing import Any, ClassVar, Dict, Optional, Set

from jinja2 import TemplateSyntaxError
from pydantic import ConfigDict, model_validator
from typing_extensions import Self, override

from pipelex import log
from pipelex.cogt.content_generation.content_generator_dry import ContentGeneratorDry
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol
from pipelex.config import get_config
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NATIVE_CONCEPTS_DATA, NativeConceptEnum
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_input_spec import PipeInputSpec
from pipelex.core.pipes.pipe_input_spec_factory import PipeInputSpecFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.pipe_run_params import PipeRunMode, PipeRunParams
from pipelex.core.pipes.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.core.stuffs.stuff_content import TextContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.exceptions import PipeDefinitionError, PipeRunParamsError
from pipelex.hub import get_content_generator, get_template, get_template_provider
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.templating.jinja2_errors import Jinja2TemplateError
from pipelex.tools.templating.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.templating.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.templating.jinja2_template_category import Jinja2TemplateCategory
from pipelex.tools.templating.templating_models import PromptingStyle
from pipelex.tools.typing.validation_utils import has_exactly_one_among_attributes_from_list


class PipeJinja2Output(PipeOutput):
    @property
    def rendered_text(self) -> str:
        return self.main_stuff_as_text.text


class PipeJinja2(PipeOperator):
    model_config = ConfigDict(extra="forbid", strict=False)

    adhoc_pipe_code: ClassVar[str] = "jinja2_render"
    output: Concept = ConceptFactory.make_native_concept(
        native_concept_data=NATIVE_CONCEPTS_DATA[NativeConceptEnum.TEXT],
    )

    jinja2_name: Optional[str] = None
    jinja2: Optional[str] = None
    prompting_style: Optional[PromptingStyle] = None
    template_category: Jinja2TemplateCategory = Jinja2TemplateCategory.LLM_PROMPT
    extra_context: Optional[Dict[str, Any]] = None

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

    @model_validator(mode="after")
    def validate_inputs(self) -> Self:
        self._validate_required_variables()
        return self

    def _validate_required_variables(self) -> Self:
        """This method checks that all required variables are in the inputs"""
        required_variables = self.required_variables()
        for required_variable_name in required_variables:
            if required_variable_name not in self.inputs.variables:
                raise PipeDefinitionError(f"Required variable '{required_variable_name}' is not in the inputs of pipe {self.code}")
        return self

    @override
    def validate_output(self):
        pass

    @override
    def validate_with_libraries(self):
        if self.jinja2_name:
            the_template = get_template(template_name=self.jinja2_name)
            log.debug(f"Validated jinja2 template '{self.jinja2_name}':\n{the_template}")

    @override
    def needed_inputs(self) -> PipeInputSpec:
        needed_inputs = PipeInputSpecFactory.make_empty()
        for input_name, requirement in self.inputs.root.items():
            needed_inputs.add_requirement(variable_name=input_name, concept=requirement.concept)
        return needed_inputs

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
        return {
            variable_name
            for variable_name in required_variables
            if not variable_name.startswith("_") and variable_name != "preliminary_text" and variable_name != "place_holder"
        }

    @override
    async def _run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
        content_generator: Optional[ContentGeneratorProtocol] = None,
    ) -> PipeJinja2Output:
        content_generator = content_generator or get_content_generator()
        if pipe_run_params.is_multiple_output_required:
            raise PipeRunParamsError(
                f"PipeJinja2 does not suppport multiple outputs, got output_multiplicity = {pipe_run_params.output_multiplicity}"
            )

        context: Dict[str, Any] = working_memory.generate_context()
        if pipe_run_params:
            context.update(**pipe_run_params.params)
        if self.extra_context:
            context.update(**self.extra_context)

        jinja2_text = await content_generator.make_jinja2_text(
            context=context,
            jinja2_name=self.jinja2_name,
            jinja2=self.jinja2,
            prompting_style=self.prompting_style,
            template_category=self.template_category,
        )
        log.verbose(f"Jinja2 rendered text:\n{jinja2_text}")
        assert isinstance(jinja2_text, str)
        the_content = TextContent(text=jinja2_text)

        output_stuff = StuffFactory.make_stuff(concept=self.output, content=the_content, name=output_name)

        working_memory.set_new_main_stuff(
            stuff=output_stuff,
            name=output_name,
        )

        pipe_output = PipeJinja2Output(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )

        return pipe_output

    @override
    async def _dry_run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeOutput:
        content_generator_used: ContentGeneratorProtocol
        if get_config().pipelex.dry_run_config.apply_to_jinja2_rendering:
            log.debug(f"PipeJinja2: using dry run operator pipe for jinja2 rendering: {self.code}")
            content_generator_used = ContentGeneratorDry()
        else:
            log.debug(f"PipeJinja2: using regular operator pipe for jinja2 rendering (dry run not applied to jinja2): {self.code}")
            content_generator_used = get_content_generator()

        pipe_output = await self._run_operator_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params or PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
            output_name=output_name,
            content_generator=content_generator_used,
        )
        return pipe_output
