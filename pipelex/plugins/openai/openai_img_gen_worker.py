from typing import TYPE_CHECKING, Any

import openai
from openai import Omit, omit
from typing_extensions import override

from pipelex.cogt.exceptions import ImgGenGenerationError, ImgGenParameterError, SdkTypeError
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.cogt.img_gen.img_gen_model_rules import BackgroundTaxonomy, ImgGenArgTopic
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.plugins.openai.openai_img_gen_factory import GptImage1BackgroundType, OpenAIImgGenFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol

if TYPE_CHECKING:
    from openai.types.images_response import ImagesResponse, Usage


class OpenAIImgGenWorker(ImgGenWorkerAbstract):
    def __init__(
        self,
        sdk_instance: Any,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(inference_model=inference_model, reporting_delegate=reporting_delegate)

        if not isinstance(sdk_instance, openai.AsyncOpenAI):
            msg = f"Provided ImgGen sdk_instance is not of type openai.AsyncOpenAI: it's a '{type(sdk_instance)}'"
            raise SdkTypeError(msg)

        self.openai_client = sdk_instance

    def _resolve_background_taxonomy(self) -> BackgroundTaxonomy:
        """Read the per-model `background` rule. Defaults to GPT for models without a rules table."""
        rules = self.inference_model.rules
        if rules is None:
            return BackgroundTaxonomy.AVAILABLE
        rule_value = rules.get(ImgGenArgTopic.BACKGROUND)
        if rule_value is None:
            return BackgroundTaxonomy.AVAILABLE
        return BackgroundTaxonomy(rule_value)

    @override
    async def _gen_image(
        self,
        img_gen_job: ImgGenJob,
    ) -> GeneratedImageRawDetails:
        one_image_list = await self._gen_image_list(img_gen_job=img_gen_job, nb_images=1)
        return one_image_list[0]

    @override
    async def _gen_image_list(
        self,
        img_gen_job: ImgGenJob,
        nb_images: int,
    ) -> list[GeneratedImageRawDetails]:
        image_size, width, height = OpenAIImgGenFactory.image_size_for_gpt_image_1(aspect_ratio=img_gen_job.job_params.aspect_ratio)
        output_format = OpenAIImgGenFactory.output_format_for_gpt_image_1(output_format=img_gen_job.job_params.output_format)
        moderation = OpenAIImgGenFactory.moderation_for_gpt_image_1(is_moderated=img_gen_job.job_params.is_moderated)
        quality = OpenAIImgGenFactory.quality_for_gpt_image_1(quality=img_gen_job.job_params.quality or Quality.LOW)
        output_compression = OpenAIImgGenFactory.output_compression_for_gpt_image_1()

        background_taxonomy = self._resolve_background_taxonomy()
        background_arg: GptImage1BackgroundType | Omit
        match background_taxonomy:
            case BackgroundTaxonomy.AVAILABLE:
                background_arg = OpenAIImgGenFactory.background_for_gpt_image_1(
                    background=img_gen_job.job_params.background,
                )
            case BackgroundTaxonomy.UNAVAILABLE:
                if img_gen_job.job_params.background.is_certainly_transparent:
                    msg = f"Model '{self.inference_model.name}' does not support transparent background"
                    raise ImgGenParameterError(msg)
                background_arg = omit

        images_response: ImagesResponse = await self.openai_client.images.generate(
            prompt=img_gen_job.img_gen_prompt.positive_text,
            model=self.inference_model.model_id,
            moderation=moderation,
            background=background_arg,
            quality=quality,
            size=image_size,
            output_format=output_format,
            output_compression=output_compression,
            n=nb_images,
        )
        if not images_response.data:
            msg = "No result from OpenAI"
            raise ImgGenGenerationError(msg)

        response_output_format: str | None = images_response.output_format
        if response_output_format is None:
            msg = "No output format received from OpenAI"
            raise ImgGenGenerationError(msg)
        size: str | None = images_response.size
        if not size:
            msg = "No size received from OpenAI"
            raise ImgGenGenerationError(msg)
        size_split = size.split("x")
        if len(size_split) != 2:
            msg = f"Size from OpenAI is not a valid size: '{size}'"
            raise ImgGenGenerationError(msg)
        width_str, height_str = size_split
        width = int(width_str)
        height = int(height_str)

        usage: Usage | None = images_response.usage
        if not usage:
            msg = "No usage received from OpenAI"
            raise ImgGenGenerationError(msg)

        if img_gen_tokens_usage := img_gen_job.job_report.img_gen_tokens_usage:
            nb_tokens: NbTokensByCategoryDict = {
                TokenCategory.INPUT: usage.input_tokens,
                TokenCategory.OUTPUT: usage.output_tokens,
            }
            img_gen_tokens_usage.nb_tokens_by_category = nb_tokens

        generated_images: list[GeneratedImageRawDetails] = []
        for image_data in images_response.data:
            base64_str = image_data.b64_json
            if not base64_str:
                msg = "No base64 image data received from OpenAI"
                raise ImgGenGenerationError(msg)

            generated_images.append(
                GeneratedImageRawDetails(
                    base64_str=base64_str,
                    size=ImageSize(width=width, height=height),
                    image_format=response_output_format,
                ),
            )
        return generated_images
