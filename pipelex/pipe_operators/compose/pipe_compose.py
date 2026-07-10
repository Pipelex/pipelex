from typing import Any, Literal

from pydantic import Field
from typing_extensions import override

from pipelex import log
from pipelex.cogt.content_generation.dry_run_factory import DryRunFactory
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.template_rendering import render_template
from pipelex.cogt.templating.templating_style import TemplatingStyle
from pipelex.config import get_config
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.exceptions import PipeValidationError, PipeValidationErrorType
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.inputs.input_stuff_specs_factory import InputStuffSpecsFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.hub import get_class_registry, get_concept_library, get_native_concept
from pipelex.pipe_operators.compose.construct_blueprint import ConstructBlueprint
from pipelex.pipe_operators.compose.exceptions import PipeComposeError, StructuredContentComposerValueError
from pipelex.pipe_operators.compose.structured_content_composer import StructuredContentComposer
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.jinja2.exceptions import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.misc.string_utils import get_root_from_dotted_path


class PipeComposeOutput(PipeOutput):
    pass


class PipeCompose(PipeOperator[PipeComposeOutput]):
    type: Literal["PipeCompose"] = "PipeCompose"

    # Template mode fields (used when template is provided)
    template: str | None = None
    templating_style: TemplatingStyle | None = None
    category: TemplateCategory = Field(default=TemplateCategory.BASIC, strict=False)
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
            if not root.startswith("_") and root != "place_holder":
                roots.add(root)
        return roots

    @override
    # TODO: this needs testing!!!
    def needed_inputs(self, *, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
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

        # In template mode, output must be Text-compatible or Html-compatible
        concept_library = get_concept_library()
        is_text_compatible = concept_library.is_compatible(
            tested_concept=self.output.concept,
            wanted_concept=get_native_concept(native_concept=NativeConceptCode.TEXT),
            strict=True,
        )
        is_html_compatible = concept_library.is_compatible(
            tested_concept=self.output.concept,
            wanted_concept=get_native_concept(native_concept=NativeConceptCode.HTML),
            strict=True,
        )
        if not (is_text_compatible or is_html_compatible):
            msg = (
                f"The output of a PipeCompose in template mode must be strictly compatible with the Text or Html concept. "
                f"In the pipe '{self.code}' the output is '{self.output.concept.concept_ref}'. "
                "Make sure this concept refines the native Text or Html concept, or use construct mode for StructuredContent."
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
                domain_code=self.domain_code,
                pipe_code=self.code,
                provided_concept_code=self.output.concept.concept_ref,
                required_concept_codes=[NativeConceptCode.TEXT.concept_ref, NativeConceptCode.HTML.concept_ref],
            )

    @override
    async def _live_run_operator_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeComposeOutput:
        if self.is_construct_mode:
            return await self._run_construct_mode(
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=pipe_run_params,
                output_name=output_name,
            )
        else:
            return await self._run_template_mode(
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=pipe_run_params,
                output_name=output_name,
            )

    async def _run_template_mode(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None,
    ) -> PipeComposeOutput:
        """Run PipeCompose in template mode (produces Text or Html output)."""
        if self.template is None:
            msg = "Template is required for template mode"
            raise ValueError(msg)

        context: dict[str, Any] = working_memory.generate_context()
        if pipe_run_params:
            context.update(**pipe_run_params.params)
        if self.extra_context:
            context.update(**self.extra_context)

        rendered_template_text = await render_template(
            template=self.template,
            category=self.category,
            context=context,
            templating_style=self.templating_style,
        )
        log.verbose(f"Template rendered text:\n{rendered_template_text}")
        assert isinstance(rendered_template_text, str)

        # Get the structure class from the registry (might be a subclass of TextContent or HtmlContent)
        structure_class = get_class_registry().get_required_subclass(
            name=self.output.concept.structure_class_name,
            base_class=StuffContent,
        )

        # Construct content based on the structure class type
        if issubclass(structure_class, HtmlContent):
            the_content = structure_class(inner_html=rendered_template_text, css_class="")
        else:
            the_content = structure_class(text=rendered_template_text)

        output_stuff = StuffFactory.make_stuff(concept=self.output.concept, content=the_content, name=output_name)

        working_memory.set_new_main_stuff(
            stuff=output_stuff,
            name=output_name,
        )

        # Capture execution data for the graph tracer
        execution_data_dict: dict[str, Any] = {
            "compose_mode": "template",
            "rendered_text": rendered_template_text,
        }
        self._register_execution_data(job_metadata=job_metadata, execution_data=execution_data_dict)

        return PipeComposeOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )

    async def _run_construct_mode(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None,
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
        composer = StructuredContentComposer(
            construct_blueprint=self.construct_blueprint,
            working_memory=working_memory,
            output_class=output_class,
            runtime_params=pipe_run_params.params if pipe_run_params else None,
            extra_context=self.extra_context,
            pipe_run_params=pipe_run_params,
        )
        try:
            the_content = await composer.compose()
        except PipeComposeError as exc:
            msg = f"In pipe '{self.code}' (output: {self.output.concept.code}): {exc.message}"
            raise PipeComposeError(msg) from exc
        log.verbose(f"Composed structured content: {the_content}")

        output_stuff = StuffFactory.make_stuff(concept=self.output.concept, content=the_content, name=output_name)

        working_memory.set_new_main_stuff(
            stuff=output_stuff,
            name=output_name,
        )

        execution_data_dict: dict[str, Any] = {
            "compose_mode": "construct",
            "fields": composer.field_resolutions,
        }
        self._register_execution_data(job_metadata=job_metadata, execution_data=execution_data_dict)

        return PipeComposeOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )

    @override
    async def _dry_run_operator_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeComposeOutput:
        if self.is_construct_mode:
            try:
                return await self._live_run_operator_pipe(
                    job_metadata=job_metadata,
                    working_memory=working_memory,
                    pipe_run_params=pipe_run_params,
                    output_name=output_name,
                )
            except PipeComposeError as exc:
                # Construct mode can fail with mock data (e.g., description-only concepts
                # produce empty classes without the fields that dotted paths reference).
                # Only fall back for value errors from the composer (e.g., unresolvable dotted paths),
                # not for type incompatibility or validation errors which are legitimate failures.
                if not isinstance(exc.__cause__, StructuredContentComposerValueError):
                    raise
                # Only swallow the error when running with mock inputs (e.g., graph generation).
                # With real inputs (e.g., pipelex validate), unresolvable paths are real bugs.
                if not get_config().pipelex.pipeline_execution_config.is_mock_inputs:
                    raise
                return self._make_mock_construct_output(
                    job_metadata=job_metadata,
                    working_memory=working_memory,
                    output_name=output_name,
                )
        else:
            return await self._live_run_operator_pipe(
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=pipe_run_params,
                output_name=output_name,
            )

    def _make_mock_construct_output(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        output_name: str | None,
    ) -> PipeComposeOutput:
        """Create a mock output for construct mode when composition fails during dry run."""
        output_class = get_class_registry().get_required_subclass(
            name=self.output.concept.structure_class_name,
            base_class=StuffContent,
        )
        factory = DryRunFactory.make_dry_run_factory(output_class)
        the_content = factory.build()
        output_stuff = StuffFactory.make_stuff(concept=self.output.concept, content=the_content, name=output_name)
        working_memory.set_new_main_stuff(stuff=output_stuff, name=output_name)
        return PipeComposeOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )

    @override
    async def _validate_before_run(
        self, *, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        pass

    @override
    async def _validate_after_run(
        self, *, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        pass
