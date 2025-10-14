from typing import Any, Literal

from pydantic import ConfigDict, model_validator
from typing_extensions import override

from pipelex import log
from pipelex.cogt.content_generation.content_generator_dry import ContentGeneratorDry
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.templating_style import TemplatingStyle
from pipelex.config import get_config
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.input_requirements import InputRequirements
from pipelex.core.pipes.input_requirements_factory import InputRequirementsFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.exceptions import PipeDefinitionError, PipeRunParamsError
from pipelex.hub import get_content_generator
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_run.pipe_run_params import PipeRunMode, PipeRunParams
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.jinja2.jinja2_errors import Jinja2TemplateSyntaxError
from pipelex.tools.jinja2.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.types import Self


class PipeComposeOutput(PipeOutput):
    pass


class PipeCompose(PipeOperator[PipeComposeOutput]):
    type: Literal["PipeCompose"] = "PipeCompose"
    model_config = ConfigDict(extra="forbid", strict=False)

    output: Concept = ConceptFactory.make_native_concept(
        native_concept_code=NativeConceptCode.TEXT,
    )

    template: str
    templating_style: TemplatingStyle | None = None
    category: TemplateCategory = TemplateCategory.BASIC
    extra_context: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_template(self) -> Self:
        try:
            check_jinja2_parsing(template_source=self.template, template_category=self.category)
        except Jinja2TemplateSyntaxError as exc:
            msg = f"Could not parse template for PipeCompose '{self.code}: {exc}"
            raise PipeDefinitionError(msg) from exc
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
                msg = f"Required variable '{required_variable_name}' is not in the inputs of pipe {self.code}"
                raise PipeDefinitionError(msg)
        return self

    @override
    def validate_output(self):
        pass

    @override
    def validate_with_libraries(self):
        pass

    @override
    def needed_inputs(self, visited_pipes: set[str] | None = None) -> InputRequirements:
        needed_inputs = InputRequirementsFactory.make_empty()
        for input_name, requirement in self.inputs.root.items():
            needed_inputs.add_requirement(variable_name=input_name, concept=requirement.concept)
        return needed_inputs

    @property
    def desc(self) -> str:
        return f"Jinja2 included template, prompting style {self.templating_style}"

    @override
    def required_variables(self) -> set[str]:
        required_variables = detect_jinja2_required_variables(
            template_category=self.category,
            template_source=self.template,
        )
        return {
            variable_name
            for variable_name in required_variables
            if not variable_name.startswith("_") and variable_name not in ("preliminary_text", "place_holder")
        }

    @override
    async def _run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        content_generator: ContentGeneratorProtocol | None = None,
    ) -> PipeComposeOutput:
        content_generator = content_generator or get_content_generator()
        if pipe_run_params.is_multiple_output_required:
            msg = f"PipeCompose does not suppport multiple outputs, got output_multiplicity = {pipe_run_params.output_multiplicity}"
            raise PipeRunParamsError(msg)

        context: dict[str, Any] = working_memory.generate_context()
        if pipe_run_params:
            context.update(**pipe_run_params.params)
        if self.extra_context:
            context.update(**self.extra_context)

        jinja2_text = await content_generator.make_templated_text(
            context=context,
            template=self.template,
            templating_style=self.templating_style,
            template_category=self.category,
        )
        log.verbose(f"Jinja2 rendered text:\n{jinja2_text}")
        assert isinstance(jinja2_text, str)
        the_content = TextContent(text=jinja2_text)

        output_stuff = StuffFactory.make_stuff(concept=self.output, content=the_content, name=output_name)

        working_memory.set_new_main_stuff(
            stuff=output_stuff,
            name=output_name,
        )

        return PipeComposeOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )

    @override
    async def _dry_run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeComposeOutput:
        content_generator_used: ContentGeneratorProtocol
        if get_config().pipelex.dry_run_config.apply_to_jinja2_rendering:
            log.debug(f"PipeCompose: using dry run operator pipe for jinja2 rendering: {self.code}")
            content_generator_used = ContentGeneratorDry()
        else:
            log.debug(f"PipeCompose: using regular operator pipe for jinja2 rendering (dry run not applied to jinja2): {self.code}")
            content_generator_used = get_content_generator()

        return await self._run_operator_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params or PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
            output_name=output_name,
            content_generator=content_generator_used,
        )
