from typing import Any, Literal

from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import LLMCompletionError
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMModelChoice, LLMSetting
from pipelex.cogt.models.model_deck_check import check_llm_choice_with_deck
from pipelex.cogt.templating.template_rendering import render_template
from pipelex.config import get_config
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.exceptions import PipeRunError, PipeValidationError
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.inputs.input_stuff_specs_factory import InputStuffSpecsFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.interpreter_hub import get_concept_library, get_native_concept
from pipelex.kernel.llm_ops import concrete_llm_model_handle, derive_structure_prompt, generate_object_content, resolve_llm_setting_for_object
from pipelex.kernel.memory_ops import store_result
from pipelex.kernel.templating_style_ops import resolve_templating_style
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_run.pipe_run_params import PipeRunParams, output_multiplicity_to_apply
from pipelex.runtime_hub import get_class_registry
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.validation_error_types import PipeValidationErrorType


class PipeStructureOutput(PipeOutput):
    pass


class PipeStructure(PipeOperator[PipeStructureOutput]):
    type: Literal["PipeStructure"] = "PipeStructure"
    llm_choice: LLMModelChoice | None = None
    text_input_name: str
    output_multiplicity: VariableMultiplicity | None = None

    @override
    def needed_inputs(self, *, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        needed_inputs = InputStuffSpecsFactory.make_empty()
        for input_name, stuff_spec in self.inputs.items:
            needed_inputs.add_stuff_spec(
                variable_name=input_name, concept=stuff_spec.concept, multiplicity=stuff_spec.multiplicity, presence=stuff_spec.presence
            )
        return needed_inputs

    @override
    def required_variables(self) -> set[str]:
        return {self.text_input_name}

    @override
    def validate_inputs_static(self):
        if self.llm_choice is not None and not isinstance(self.llm_choice, LLMSetting):
            check_llm_choice_with_deck(llm_choice=self.llm_choice)

    @override
    def validate_inputs_with_library(self):
        the_single_input = self.inputs.get_single_stuff_spec()
        text_concept = get_native_concept(native_concept=NativeConceptCode.TEXT)
        if not get_concept_library().is_compatible(
            tested_concept=the_single_input.concept,
            wanted_concept=text_concept,
            strict=False,
        ):
            msg = f"PipeStructure input must be Text-compatible (a concept that refines Text), but got '{the_single_input.concept.concept_ref}'."
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH,
                domain_code=self.domain_code,
                pipe_code=self.code,
                provided_concept_code=the_single_input.concept.concept_ref,
            )

    @override
    def validate_output_static(self):
        pass

    @override
    def validate_output_with_library(self):
        text_concept = get_native_concept(native_concept=NativeConceptCode.TEXT)
        if get_concept_library().is_compatible(
            tested_concept=self.output.concept,
            wanted_concept=text_concept,
            strict=False,
        ):
            msg = f"PipeStructure output must be a structured concept, not Text-compatible. Got '{self.output.concept.concept_ref}'."
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
                domain_code=self.domain_code,
                pipe_code=self.code,
                provided_concept_code=self.output.concept.concept_ref,
            )

    @override
    async def _live_run_operator_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeStructureOutput:
        text_str = working_memory.get_stuff_as_str(name=self.text_input_name)

        # Resolve list-vs-single from base + override.
        multiplicity_resolution = output_multiplicity_to_apply(
            base_multiplicity=self.output_multiplicity,
            override_multiplicity=pipe_run_params.output_multiplicity,
        )
        is_multiple_output = multiplicity_resolution.is_multiple_outputs_enabled
        fixed_nb_output = multiplicity_resolution.specific_output_count

        # LLM choice: explicit on the pipe → for_object override → for_object default. This pipe has
        # no text choice of its own, so the kernel's object chain reduces to exactly those three rungs.
        llm_setting_for_object: LLMSetting = resolve_llm_setting_for_object(llm_choice=self.llm_choice)

        # Render the structuring prompt template against the input text. Prompt *assembly* is not
        # shared with PipeLLM: this pipe has no template of its own and no memory-borne references —
        # it renders one configured template over one input string.
        # No authored style on this operator: the structuring prompt takes the runtime default, the
        # same one an LLM pipe that declares nothing gets.
        templating_style = resolve_templating_style(authored=None)
        llm_config = get_config().inference.llm
        structuring_template = llm_config.get_template(template_name="structuring_prompt")
        rendered_user_prompt = await render_template(
            template=structuring_template,
            category=TemplateCategory.LLM_PROMPT,
            context={"text": text_str},
            templating_style=templating_style,
        )

        content_class: type[StuffContent] = get_class_registry().get_required_subclass(
            name=self.output.concept.structure_class_name,
            base_class=StuffContent,
        )

        # Append the schema description, from the same kernel derivation PipeLLM's object path uses.
        output_structure_prompt = await derive_structure_prompt(output_class=content_class, templating_style=templating_style)
        if output_structure_prompt:
            rendered_user_prompt += output_structure_prompt

        llm_prompt = LLMPrompt(user_text=rendered_user_prompt)

        try:
            the_content = await generate_object_content(
                job_metadata=job_metadata,
                cogt_run_params=pipe_run_params.cogt_run_params,
                llm_prompt=llm_prompt,
                llm_setting=llm_setting_for_object,
                output_class=content_class,
                is_multiple_output=is_multiple_output,
                fixed_nb_output=fixed_nb_output,
            )
        except LLMCompletionError as exc:
            location = self._format_error_location(pipe_run_params=pipe_run_params)
            what_failed = "object list" if is_multiple_output else "single object"
            msg = f"Error generating {what_failed} in PipeStructure {location}: {exc}"
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code) from exc

        log.verbose(f"PipeStructure '{self.code}' produced {content_class.__name__} (list={is_multiple_output})")

        working_memory = store_result(
            memory=working_memory,
            concept=self.output.concept,
            content=the_content,
            result_name=output_name,
            result_code=pipe_run_params.final_stuff_code,
        )

        execution_data_dict: dict[str, Any] = {
            "resolved_model": concrete_llm_model_handle(llm_setting_for_object.model),
            "is_multiple_output": is_multiple_output,
            "rendered_user_prompt": rendered_user_prompt,
            "structuring_path": "structure",
        }
        self._register_execution_data(job_metadata=job_metadata, execution_data=execution_data_dict)

        return PipeStructureOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.run_metadata.pipeline_run_id,
        )

    def _format_error_location(self, pipe_run_params: PipeRunParams) -> str:
        return f"in pipe '{pipe_run_params.pipe_stack_str}'"

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
