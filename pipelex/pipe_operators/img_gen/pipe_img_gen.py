from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field
from typing_extensions import override

from pipelex import log
from pipelex.cogt.content_generation.content_generator_dry import ContentGeneratorDry
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, ImgGenJobParams
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.img_gen.img_gen_setting import ImgGenModelChoice, ImgGenSetting
from pipelex.cogt.models.model_deck_check import check_img_gen_choice_with_deck
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.config import get_config
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.exceptions import WorkingMemoryStuffNotFoundError
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.exceptions import PipeValidationError, PipeValidationErrorType
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
from pipelex.core.stuffs.exceptions import StuffContentTypeError
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.hub import get_class_registry, get_concept_library, get_content_generator, get_model_deck, get_native_concept
from pipelex.pipe_operators.img_gen.exceptions import PipeImgGenRunError
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_run.exceptions import PipeRunParamsError
from pipelex.pipe_run.pipe_run_params import PipeRunParams, output_multiplicity_to_apply
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.misc.dict_utils import substitute_nested_in_context
from pipelex.tools.misc.image_utils import ImageFormat

if TYPE_CHECKING:
    from pipelex.core.stuffs.stuff_content import StuffContent


class PipeImgGenOutput(PipeOutput):
    pass


class PipeImgGen(PipeOperator[PipeImgGenOutput]):
    type: Literal["PipeImgGen"] = "PipeImgGen"
    prompt_blueprint: TemplateBlueprint
    negative_prompt_blueprint: TemplateBlueprint | None = None
    img_gen_choice: ImgGenModelChoice | None = None

    # One-time settings (not in ImgGenSetting)
    aspect_ratio: AspectRatio | None = Field(default=None, strict=False)
    is_raw: bool | None = None
    seed: int | Literal["auto"] | None = None
    background: Background | None = Field(default=None, strict=False)
    output_format: ImageFormat | None = Field(default=None, strict=False)
    output_multiplicity: VariableMultiplicity

    @override
    def needed_inputs(self, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        """Needed inputs are the inputs needed to run the pipe, specified in the inputs attribute of the pipe"""
        return self.inputs

    @override
    def required_variables(self) -> set[str]:
        """Required variables are the variables that are used in the prompt template"""
        required_variables = {variable_name for variable_name in self.prompt_blueprint.required_variables() if not variable_name.startswith("_")}
        if self.negative_prompt_blueprint:
            required_variables.update(
                {variable_name for variable_name in self.negative_prompt_blueprint.required_variables() if not variable_name.startswith("_")}
            )
        return required_variables

    @override
    def validate_inputs_static(self):
        if self.img_gen_choice:
            check_img_gen_choice_with_deck(img_gen_choice=self.img_gen_choice)

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
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        content_generator: ContentGeneratorProtocol | None = None,
    ) -> PipeImgGenOutput:
        content_generator = content_generator or get_content_generator()

        multiplicity_resolution = output_multiplicity_to_apply(
            base_multiplicity=self.output_multiplicity or False,
            override_multiplicity=pipe_run_params.output_multiplicity,
        )
        applied_output_multiplicity = multiplicity_resolution.resolved_multiplicity

        try:
            base_context: dict[str, Any] = working_memory.generate_context()
            positive_prompt_context = base_context.copy()
            if extra_params := pipe_run_params.params:
                positive_prompt_context = substitute_nested_in_context(context=positive_prompt_context, extra_params=extra_params)
            if extra_context := self.prompt_blueprint.extra_context:
                positive_prompt_context.update(**extra_context)
            positive_prompt_text = await content_generator.make_templated_text(
                context=positive_prompt_context,
                template=self.prompt_blueprint.template,
                templating_style=self.prompt_blueprint.templating_style,
                template_category=self.prompt_blueprint.category,
            )
            negative_prompt_text: str | None = None
            if self.negative_prompt_blueprint:
                negative_prompt_context = base_context.copy()
                if extra_params := pipe_run_params.params:
                    negative_prompt_context = substitute_nested_in_context(context=negative_prompt_context, extra_params=extra_params)
                if extra_context := self.negative_prompt_blueprint.extra_context:
                    negative_prompt_context.update(**extra_context)
                negative_prompt_text = await content_generator.make_templated_text(
                    context=negative_prompt_context,
                    template=self.negative_prompt_blueprint.template,
                    templating_style=self.negative_prompt_blueprint.templating_style,
                    template_category=self.negative_prompt_blueprint.category,
                )
        except WorkingMemoryStuffNotFoundError as stuff_not_found_error:
            msg = f"While runnning the PipeImgGen '{self.code}' some inputs could not be found in the working_memory: {stuff_not_found_error}"
            raise PipeImgGenRunError(message=msg) from stuff_not_found_error
        except StuffContentTypeError as stuff_content_type_error:
            msg = f"While runnning the PipeImgGen '{self.code}' some inputs are not of the right type: {stuff_content_type_error}"
            raise PipeImgGenRunError(message=msg) from stuff_content_type_error

        img_gen_config = get_config().cogt.img_gen_config
        img_gen_param_defaults = img_gen_config.img_gen_param_defaults
        model_deck = get_model_deck()

        # Get ImgGenSetting either from img_gen choice or legacy settings
        img_gen_setting: ImgGenSetting
        if self.img_gen_choice is not None:
            # New pattern: use img_gen choice (preset or inline setting)
            img_gen_setting = model_deck.get_img_gen_setting(self.img_gen_choice)
        else:
            # Use default from model deck
            img_gen_setting = model_deck.get_img_gen_setting(model_deck.img_gen_choice_default)

        # Process one-time settings
        seed_setting = self.seed or img_gen_param_defaults.seed
        seed: int | None
        if isinstance(seed_setting, str) and seed_setting == "auto":
            seed = None
        else:
            seed = seed_setting

        # Build ImgGenJobParams from ImgGenSetting + one-time settings
        img_gen_job_params = ImgGenJobParams(
            aspect_ratio=self.aspect_ratio or img_gen_param_defaults.aspect_ratio,
            background=self.background or img_gen_param_defaults.background,
            quality=img_gen_setting.quality,
            nb_steps=img_gen_setting.nb_steps,
            guidance_scale=img_gen_setting.guidance_scale,
            is_moderated=img_gen_setting.is_moderated,
            safety_tolerance=img_gen_setting.safety_tolerance,
            is_raw=self.is_raw if self.is_raw is not None else img_gen_param_defaults.is_raw,
            output_format=self.output_format,
            seed=seed,
        )
        # Get the image generation handle
        img_gen_handle = img_gen_setting.model
        log.verbose(f"Using img_gen handle: {img_gen_handle}")

        the_content: StuffContent
        nb_images: int
        if isinstance(applied_output_multiplicity, bool):
            if self.output_multiplicity:
                msg = "Cannot guess how many images to generate if multiplicity is just True."
                msg += f" Got PipeImgGen.output_multiplicity = {self.output_multiplicity},"
                msg += f" and pipe_run_params.output_multiplicity = {pipe_run_params.output_multiplicity}."
                msg += f" Tried to apply applied_output_multiplicity = {applied_output_multiplicity}."
                raise PipeRunParamsError(msg)
            nb_images = 1
        elif isinstance(applied_output_multiplicity, int):
            nb_images = applied_output_multiplicity
        else:
            nb_images = 1

        # Get the structure class from the registry (must be a subclass of ImageContent)
        image_content_subclass = get_class_registry().get_required_subclass(
            name=self.output.concept.structure_class_name,
            base_class=ImageContent,
        )
        if nb_images > 1:
            image_content_list = await content_generator.make_image_list(
                job_metadata=job_metadata,
                img_gen_handle=img_gen_handle,
                img_gen_prompt=ImgGenPrompt(
                    positive_text=positive_prompt_text,
                    negative_text=negative_prompt_text,
                ),
                nb_images=nb_images,
                img_gen_job_params=img_gen_job_params,
                img_gen_job_config=img_gen_config.img_gen_job_config,
            )
            subclass_content_items: list[ImageContent] = []
            for image_content in image_content_list:
                subclass_content = image_content_subclass.model_validate(image_content)
                subclass_content_items.append(subclass_content)
            the_content = ListContent(
                items=subclass_content_items,
            )
            log.verbose(the_content, title="List of image contents")
        else:
            image_content = await content_generator.make_single_image(
                job_metadata=job_metadata,
                img_gen_handle=img_gen_handle,
                img_gen_prompt=ImgGenPrompt(
                    positive_text=positive_prompt_text,
                    negative_text=negative_prompt_text,
                ),
                img_gen_job_params=img_gen_job_params,
                img_gen_job_config=img_gen_config.img_gen_job_config,
            )

            the_content = image_content_subclass.model_validate(image_content)
            log.verbose(the_content, title=f"output stuff content of PipeImg {self.code}")

        output_stuff = StuffFactory.make_stuff(
            name=output_name,
            concept=self.output.concept,
            content=the_content,
        )

        working_memory.set_new_main_stuff(
            stuff=output_stuff,
            name=output_name,
        )

        return PipeImgGenOutput(
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
    ) -> PipeImgGenOutput:
        return await self._live_run_operator_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
            output_name=output_name,
            content_generator=ContentGeneratorDry(),
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
