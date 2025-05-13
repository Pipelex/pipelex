# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import List, Literal, Optional, Union, cast

from pydantic import Field
from typing_extensions import override

from pipelex import log, pretty_print
from pipelex.cogt.imgg.imgg_handle import ImggHandle
from pipelex.cogt.imgg.imgg_job_components import AspectRatio, ImggJobParams
from pipelex.cogt.imgg.imgg_prompt import ImggPrompt
from pipelex.config import get_config
from pipelex.core.domain import SpecialDomain
from pipelex.core.pipe import PipeAbstract, update_job_metadata_for_pipe
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import PipeOutputMultiplicity, PipeRunParams, output_multiplicity_to_apply
from pipelex.core.stuff_content import ImageContent, ListContent, StuffContent, TextContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory import WorkingMemory
from pipelex.exceptions import PipeRunParamsError
from pipelex.hub import get_content_generator
from pipelex.job_metadata import JobMetadata


class PipeImgGenOutput(PipeOutput):
    @property
    def image_urls(self) -> List[str]:
        items = self.main_stuff_as_items(item_type=ImageContent)
        return [item.url for item in items]


class PipeImgGen(PipeAbstract):
    output_concept_code: str = f"{SpecialDomain.NATIVE}.Image"
    # TODO: wrap this up in imgg llm_presets like for llm
    imgg_handle: Optional[ImggHandle] = None
    aspect_ratio: Optional[AspectRatio] = Field(default=None, strict=False)
    nb_steps: Optional[int] = Field(default=None, gt=0)
    guidance_scale: Optional[float] = Field(default=None, gt=0)
    is_safety_checker_enabled: Optional[bool] = None
    safety_tolerance: Optional[int] = Field(default=None, ge=1, le=6)
    is_raw: Optional[bool] = None
    seed: Optional[Union[int, Literal["auto"]]] = None
    output_multiplicity: PipeOutputMultiplicity

    @override
    @update_job_metadata_for_pipe
    async def run_pipe(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        pipe_code: str,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeImgGenOutput:
        if not self.output_concept_code:
            raise ValueError("PipeImgGen should have a non-None output_concept_code")

        applied_output_multiplicity, _, _ = output_multiplicity_to_apply(
            output_multiplicity_base=self.output_multiplicity or False,
            output_multiplicity_override=pipe_run_params.output_multiplicity,
        )

        log.debug("Getting image generation prompt from context")
        imgg_prompt_stuff = working_memory.get_stuff("imgg_prompt")
        if not imgg_prompt_stuff:
            raise ValueError("imgg_prompt not found in context")

        imgg_prompt_text = cast(TextContent, imgg_prompt_stuff.content).text
        imgg_config = get_config().cogt.imgg_config
        imgg_param_defaults = imgg_config.imgg_param_defaults

        seed_setting = self.seed or imgg_param_defaults.seed
        seed: Optional[int]
        if isinstance(seed_setting, str) and seed_setting == "auto":
            seed = None
        else:
            seed = seed_setting

        imgg_job_params = ImggJobParams(
            nb_steps=self.nb_steps or imgg_param_defaults.nb_steps,
            aspect_ratio=self.aspect_ratio or imgg_param_defaults.aspect_ratio,
            guidance_scale=self.guidance_scale or imgg_param_defaults.guidance_scale,
            is_safety_checker_enabled=self.is_safety_checker_enabled or imgg_param_defaults.is_safety_checker_enabled,
            safety_tolerance=self.safety_tolerance or imgg_param_defaults.safety_tolerance,
            is_raw=self.is_raw or imgg_param_defaults.is_raw,
            output_format=imgg_param_defaults.output_format,
            seed=seed,
        )
        imgg_handle = self.imgg_handle or imgg_config.default_imgg_handle
        log.debug(f"Using imgg handle: {imgg_handle}")
        pretty_print(imgg_job_params, title=f"Imgg Job Params used with '{imgg_handle}'")

        the_content: StuffContent
        image_urls: List[str] = []
        nb_images: int
        if isinstance(applied_output_multiplicity, bool):
            if self.output_multiplicity:
                msg = "Cannot guess how many images to generate if multiplicity is just True."
                msg += f" Got PipeImgGen.output_multiplicity = {self.output_multiplicity},"
                msg += f" and pipe_run_params.output_multiplicity = {pipe_run_params.output_multiplicity}."
                msg += f" Tried to apply applied_output_multiplicity = {applied_output_multiplicity}."
                raise PipeRunParamsError(msg)
            else:
                nb_images = 1
        elif isinstance(applied_output_multiplicity, int):
            nb_images = applied_output_multiplicity
        else:
            nb_images = 1

        if nb_images > 1:
            generated_image_list = await get_content_generator().make_image_list(
                job_metadata=job_metadata,
                imgg_handle=imgg_handle,
                imgg_prompt=ImggPrompt(
                    positive_text=imgg_prompt_text,
                ),
                nb_images=nb_images,
                imgg_job_params=imgg_job_params,
                imgg_job_config=imgg_config.imgg_job_config,
                wfid="imgg",
            )
            image_content_items: List[StuffContent] = []
            for generated_image in generated_image_list:
                image_content_items.append(
                    ImageContent(
                        url=generated_image.url,
                        source_prompt=imgg_prompt_text,
                    )
                )
                image_urls.append(generated_image.url)
            the_content = ListContent(
                items=image_content_items,
            )
            log.verbose(the_content, title="List of image contents")
        else:
            generated_image = await get_content_generator().make_single_image(
                job_metadata=job_metadata,
                imgg_handle=imgg_handle,
                imgg_prompt=ImggPrompt(
                    positive_text=imgg_prompt_text,
                ),
                imgg_job_params=imgg_job_params,
                imgg_job_config=imgg_config.imgg_job_config,
                wfid="imgg",
            )

            generated_image_url = generated_image.url
            image_urls = [generated_image_url]

            the_content = ImageContent(
                url=generated_image_url,
                source_prompt=imgg_prompt_text,
            )
            log.verbose(the_content, title="Single image content")

        output_stuff = StuffFactory.make_stuff(
            name=output_name,
            concept_code=self.output_concept_code,
            content=the_content,
        )

        working_memory.set_new_main_stuff(
            stuff=output_stuff,
            name=output_name,
        )

        pipe_output = PipeImgGenOutput(
            working_memory=working_memory,
        )
        return pipe_output
