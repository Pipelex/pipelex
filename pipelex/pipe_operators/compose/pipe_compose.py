from typing import Any, Literal

from typing_extensions import override

from pipelex import log
from pipelex.cogt.content_generation.content_generator_dry import ContentGeneratorDry
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.templating_style import TemplatingStyle
from pipelex.config import get_config
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.exceptions import PipeValidationError, PipeValidationErrorType
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.inputs.input_stuff_specs_factory import InputStuffSpecsFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.hub import get_class_registry, get_concept_library, get_content_generator, get_native_concept
from pipelex.pipe_operators.compose.construct_blueprint import ConstructBlueprint
from pipelex.pipe_operators.compose.structured_content_composer import StructuredContentComposer
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.jinja2.jinja2_errors import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.misc.string_utils import get_root_from_dotted_path


class PipeComposeOutput(PipeOutput):
    pass


class PipeCompose(PipeOperator[PipeComposeOutput]):
    type: Literal["PipeCompose"] = "PipeCompose"

    # Template mode fields (used when template is provided)
    template: str | None = None
    templating_style: TemplatingStyle | None = None
    category: TemplateCategory = TemplateCategory.BASIC
    extra_context: dict[str, Any] | None = None

    # Construct mode field (used when construct is provided)
    construct_blueprint: ConstructBlueprint | None = None

    @property
    def is_construct_mode(self) -> bool:
        """Return True if this pipe uses construct mode instead of template mode."""
        return self.construct_blueprint is not None

    @property
    def desc(self) -> str:
        if self.is_construct_mode:
            return f"PipeCompose in construct mode for StructuredContent output of type '{self.output.concept.structure_class_name}'"
        else:
            return f"PipeCompose in template mode with Jinja2 template, prompting style {self.templating_style}, category {self.category}"

    @override
    def required_variables(self) -> set[str]:
        if self.construct_blueprint is not None:
            return self.construct_blueprint.get_required_variables()
        else:
            return self._required_variables_for_template()

    def _required_variables_for_template(self) -> set[str]:
        """Get required variables for template mode."""
        if self.template is None:
            return set()

        try:
            full_paths = detect_jinja2_required_variables(
                template_category=self.category,
                template_source=self.template,
            )
        except Jinja2DetectVariablesError as exc:
            msg = f"Error detecting required variables for PipeCompose: {exc}"
            raise ValueError(msg) from exc
        roots: set[str] = set()
        for path in full_paths:
            root = get_root_from_dotted_path(path)
            if not root.startswith("_") and root not in {"preliminary_text", "place_holder"}:
                roots.add(root)
        return roots

    @override
    # TODO: this needs testing!!!
    def needed_inputs(self, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        needed_inputs = InputStuffSpecsFactory.make_empty()
        for input_name, stuff_spec in self.inputs.root.items():
            needed_inputs.add_stuff_spec(variable_name=input_name, concept=stuff_spec.concept, multiplicity=stuff_spec.multiplicity)
        return needed_inputs

    @override
    def validate_inputs_static(self):
        pass

    @override
    def validate_inputs_with_library(self):
        pass

    @override
    def validate_output_static(self):
        pass

    @override
    def validate_output_with_library(self):
        # In construct mode, output can be any StructuredContent (not just Text)
        if self.is_construct_mode:
            return

        # In template mode, output must be Text-compatible
        if not get_concept_library().is_compatible(
            tested_concept=self.output.concept,
            wanted_concept=get_native_concept(native_concept=NativeConceptCode.TEXT),
            strict=True,
        ):
            msg = (
                f"The output of a PipeCompose in template mode must be strictly compatible with the Text concept. "
                f"In the pipe '{self.code}' the output is '{self.output.concept.concept_ref}'. "
                "Make sure this concept refines the native Text concept, or use construct mode for StructuredContent."
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
                domain_code=self.domain_code,
                pipe_code=self.code,
                provided_concept_code=self.output.concept.concept_ref,
                required_concept_codes=[NativeConceptCode.TEXT.concept_ref],
            )

    @override
    async def _live_run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        content_generator: ContentGeneratorProtocol | None = None,
    ) -> PipeComposeOutput:
        content_generator = content_generator or get_content_generator()

        if self.is_construct_mode:
            return await self._run_construct_mode(
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=pipe_run_params,
                output_name=output_name,
                content_generator=content_generator,
            )
        else:
            return await self._run_template_mode(
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=pipe_run_params,
                output_name=output_name,
                content_generator=content_generator,
            )

    async def _run_template_mode(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None,
        content_generator: ContentGeneratorProtocol,
    ) -> PipeComposeOutput:
        """Run PipeCompose in template mode (produces Text output)."""
        if self.template is None:
            msg = "Template is required for template mode"
            raise ValueError(msg)

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

        # Get the structure class from the registry (might be a subclass of TextContent)
        structure_class = get_class_registry().get_required_subclass(
            name=self.output.concept.structure_class_name,
            base_class=StuffContent,
        )
        the_content = structure_class(text=jinja2_text)

        output_stuff = StuffFactory.make_stuff(concept=self.output.concept, content=the_content, name=output_name)

        working_memory.set_new_main_stuff(
            stuff=output_stuff,
            name=output_name,
        )

        return PipeComposeOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )

    async def _run_construct_mode(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None,
        content_generator: ContentGeneratorProtocol,
    ) -> PipeComposeOutput:
        """Run PipeCompose in construct mode (produces StructuredContent output)."""
        if self.construct_blueprint is None:
            msg = "Construct blueprint is required for construct mode"
            raise ValueError(msg)

        # Get the output class from the registry
        output_class = get_class_registry().get_required_subclass(
            name=self.output.concept.structure_class_name,
            base_class=StuffContent,
        )

        # Create composer and compose the structured content
        # Pass runtime params, extra context, and content generator for template fields (consistent with _run_template_mode)
        composer = StructuredContentComposer(
            construct_blueprint=self.construct_blueprint,
            working_memory=working_memory,
            output_class=output_class,
            runtime_params=pipe_run_params.params if pipe_run_params else None,
            extra_context=self.extra_context,
            content_generator=content_generator,
        )
        the_content = await composer.compose()
        log.verbose(f"Composed structured content: {the_content}")

        output_stuff = StuffFactory.make_stuff(concept=self.output.concept, content=the_content, name=output_name)

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
            log.verbose(f"PipeCompose: using dry run operator pipe for jinja2 rendering: {self.code}")
            content_generator_used = ContentGeneratorDry()
        else:
            log.verbose(f"PipeCompose: using regular operator pipe for jinja2 rendering (dry run not applied to jinja2): {self.code}")
            content_generator_used = get_content_generator()

        return await self._live_run_operator_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
            output_name=output_name,
            content_generator=content_generator_used,
        )

    @override
    async def _validate_before_run(
        self, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        pass

    @override
    async def _validate_after_run(
        self, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        pass
