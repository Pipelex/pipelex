from typing import Any, Literal

from pydantic import Field
from typing_extensions import override

from pipelex import log
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, ImgGenSize
from pipelex.cogt.img_gen.img_gen_param_support import ImgGenParamSupport
from pipelex.cogt.img_gen.img_gen_setting import ImgGenModelChoice, ImgGenSetting, ImgGenSettingValueError
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck_check import check_img_gen_choice_with_deck
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.exceptions import WorkingMemoryStuffNotFoundError
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
from pipelex.core.stuffs.exceptions import StuffContentTypeError
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.interpreter_hub import get_concept_library, get_native_concept
from pipelex.kernel.exceptions import PromptContentError
from pipelex.kernel.img_gen_ops import build_img_gen_job_params, resolve_img_gen_setting, run_img_gen
from pipelex.kernel.templating_style_ops import resolve_templating_style
from pipelex.pipe_machinery.template_guard_lint import lint_optional_input_guards
from pipelex.pipe_operators.img_gen.exceptions import PipeImgGenFactoryError, PipeImgGenRunError
from pipelex.pipe_operators.img_gen.img_gen_prompt_blueprint import ImgGenPromptBlueprint
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_run.exceptions import PipeRunParamsError
from pipelex.pipe_run.pipe_run_params import PipeRunParams, output_multiplicity_to_apply
from pipelex.runtime_hub import get_class_registry, get_model_deck
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.misc.image_utils import ImageFormat
from pipelex.validation_error_types import PipeValidationErrorType


class PipeImgGenOutput(PipeOutput):
    pass


class PipeImgGen(PipeOperator[PipeImgGenOutput]):
    type: Literal["PipeImgGen"] = "PipeImgGen"
    img_gen_prompt_blueprint: ImgGenPromptBlueprint
    img_gen_choice: ImgGenModelChoice | None = None

    # One-time settings (not in ImgGenSetting)
    aspect_ratio: AspectRatio | None = Field(default=None, strict=False)
    size: ImgGenSize | None = None
    is_raw: bool | None = None
    seed: int | Literal["auto"] | None = None
    background: Background | None = Field(default=None, strict=False)
    output_format: ImageFormat | None = Field(default=None, strict=False)
    output_multiplicity: VariableMultiplicity

    @override
    def needed_inputs(self, *, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        """Needed inputs are the inputs needed to run the pipe, specified in the inputs attribute of the pipe"""
        return self.inputs

    @override
    def required_variables(self) -> set[str]:
        """Required variables are the variables that are used in the prompt template"""
        return self.img_gen_prompt_blueprint.required_variables()

    @override
    def validate_inputs_static(self):
        if self.img_gen_choice:
            check_img_gen_choice_with_deck(img_gen_choice=self.img_gen_choice)
            self._validate_param_support_against_model_rules()

        # Guard-lint (D7): every reference to a declared-optional input must be guarded.
        for template_blueprint, template_label in [
            (self.img_gen_prompt_blueprint.prompt_blueprint, "prompt"),
            (self.img_gen_prompt_blueprint.negative_prompt_blueprint, "negative_prompt"),
        ]:
            if template_blueprint is None:
                continue
            lint_optional_input_guards(
                pipe_code=self.code,
                domain_code=self.domain_code,
                inputs=self.inputs,
                template_source=template_blueprint.template,
                template_category=template_blueprint.category,
                template_label=template_label,
            )

    def _validate_param_support_against_model_rules(self) -> None:
        """If `img_gen_choice` resolves to a concrete inference model with rules,
        validate that explicitly-set blueprint params are accepted by those rules.

        Skipped silently when the choice is a preset/alias/waterfall whose target
        cannot be resolved at static-validation time, or when the resolved spec
        has no rules attached.
        """
        if self.img_gen_choice is None:
            return
        model_deck = get_model_deck()
        try:
            img_gen_setting = model_deck.get_img_gen_setting(self.img_gen_choice)
        except ImgGenSettingValueError:
            return
        spec = model_deck.get_optional_inference_model(
            model_handle=img_gen_setting.model,
            model_type=ModelType.IMG_GEN,
        )
        if spec is None or spec.rules is None:
            return
        unsupported = ImgGenParamSupport.check_blueprint_params(
            rules=spec.rules,
            aspect_ratio=self.aspect_ratio,
            size=self.size,
            background=self.background,
            output_format=self.output_format,
            model_name=img_gen_setting.model,
        )
        if unsupported:
            joined = "; ".join(unsupported)
            msg = f"PipeImgGen '{self.code}' uses parameter values not supported by model '{img_gen_setting.model}': {joined}"
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.UNKNOWN_VALIDATION_ERROR,
                domain_code=self.domain_code,
                pipe_code=self.code,
            )

    @override
    def validate_inputs_with_library(self):
        pass

    @override
    def validate_output_static(self):
        pass

    @override
    def validate_output_with_library(self):
        if not get_concept_library().is_compatible(
            tested_concept=self.output.concept,
            wanted_concept=get_native_concept(native_concept=NativeConceptCode.IMAGE),
            strict=True,
        ):
            msg = (
                f"The output of a PipeImgGen must be compatible with the Image concept. "
                f"In the pipe '{self.code}' the output is '{self.output.concept.concept_ref}'"
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
                domain_code=self.domain_code,
                pipe_code=self.code,
                provided_concept_code=self.output.concept.concept_ref,
                required_concept_codes=[NativeConceptCode.IMAGE.concept_ref],
            )

    @override
    async def _live_run_operator_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeImgGenOutput:
        multiplicity_resolution = output_multiplicity_to_apply(
            base_multiplicity=self.output_multiplicity or False,
            override_multiplicity=pipe_run_params.output_multiplicity,
        )
        applied_output_multiplicity = multiplicity_resolution.resolved_multiplicity

        # The deck chain is kernel semantics; the setting is resolved per run into a local and never
        # cached onto `self`, for the reason `pipe_llm.py` states about its own settings.
        img_gen_setting: ImgGenSetting = resolve_img_gen_setting(img_gen_choice=self.img_gen_choice)

        # Get max_prompt_images from model spec for validation
        model_spec = get_model_deck().get_optional_inference_model(model_handle=img_gen_setting.model, model_type=ModelType.IMG_GEN)
        max_prompt_images = model_spec.max_prompt_images if model_spec else None

        try:
            img_gen_prompt = await self.img_gen_prompt_blueprint.make_img_gen_prompt(
                context_provider=working_memory,
                # No authored style on this operator: an image prompt takes the runtime default, the
                # same one an LLM pipe that declares nothing gets.
                templating_style=resolve_templating_style(authored=None),
                extra_params=pipe_run_params.params,
                max_prompt_images=max_prompt_images,
            )
        except WorkingMemoryStuffNotFoundError as stuff_not_found_error:
            msg = f"While runnning the PipeImgGen '{self.code}' some inputs could not be found in the working_memory: {stuff_not_found_error}"
            raise PipeImgGenRunError(message=msg) from stuff_not_found_error
        except StuffContentTypeError as stuff_content_type_error:
            msg = f"While runnning the PipeImgGen '{self.code}' some inputs are not of the right type: {stuff_content_type_error}"
            raise PipeImgGenRunError(message=msg) from stuff_content_type_error
        except PromptContentError as blueprint_error:
            msg = f"While running the PipeImgGen '{self.code}' image extraction failed: {blueprint_error}"
            raise PipeImgGenRunError(message=msg) from blueprint_error
        except PipeImgGenFactoryError as factory_error:
            msg = f"While running the PipeImgGen '{self.code}' prompt construction failed: {factory_error}"
            raise PipeImgGenRunError(message=msg) from factory_error

        # The three-provenance composition (setting / step field / configured default) is kernel semantics.
        img_gen_job_params = build_img_gen_job_params(
            img_gen_setting=img_gen_setting,
            aspect_ratio=self.aspect_ratio,
            size=self.size,
            is_raw=self.is_raw,
            seed=self.seed,
            background=self.background,
            output_format=self.output_format,
        )
        log.verbose(f"Using img_gen handle: {img_gen_setting.model}")

        nb_images: int
        if applied_output_multiplicity is True:
            # Only a RESOLVED "model decides" is unguessable — a forced-single resolution (False),
            # e.g. from an override of 1, is one image even when the pipe declares `Image[]`.
            msg = "Cannot guess how many images to generate if multiplicity is just True."
            msg += f" Got PipeImgGen.output_multiplicity = {self.output_multiplicity},"
            msg += f" and pipe_run_params.output_multiplicity = {pipe_run_params.output_multiplicity}."
            raise PipeRunParamsError(msg)
        if isinstance(applied_output_multiplicity, bool) or applied_output_multiplicity is None:
            nb_images = 1
        else:
            nb_images = applied_output_multiplicity

        # Resolved here rather than inside the kernel: turning a concept into a class is a library's
        # business, and handing the class over is what spares the kernel a registry read.
        image_content_subclass = get_class_registry().get_required_subclass(
            name=self.output.concept.structure_class_name,
            base_class=ImageContent,
        )
        img_gen_result = await run_img_gen(
            memory=working_memory,
            img_gen_prompt=img_gen_prompt,
            img_gen_setting=img_gen_setting,
            img_gen_job_params=img_gen_job_params,
            concept=self.output.concept,
            output_class=image_content_subclass,
            job_metadata=job_metadata,
            cogt_run_params=pipe_run_params.cogt_run_params,
            nb_images=nb_images,
            result_name=output_name,
        )
        working_memory = img_gen_result.memory
        log.verbose(img_gen_result.content, title=f"output stuff content of PipeImg {self.code}")

        # Capture execution data for the graph tracer
        execution_data_dict: dict[str, Any] = {
            "resolved_model": img_gen_setting.model,
            "rendered_prompt": img_gen_prompt.positive_text,
            "rendered_negative_prompt": img_gen_prompt.negative_text,
            "aspect_ratio": str(img_gen_job_params.aspect_ratio) if img_gen_job_params.aspect_ratio else None,
            "nb_images": nb_images,
        }

        self._register_execution_data(job_metadata=job_metadata, execution_data=execution_data_dict)
        return PipeImgGenOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.run_metadata.pipeline_run_id,
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
