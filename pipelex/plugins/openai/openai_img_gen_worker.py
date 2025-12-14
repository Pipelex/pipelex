from typing import Any

import openai
import shortuuid
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import ImgGenGenerationError, SdkTypeError
from pipelex.cogt.image.generated_image import GeneratedImage
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.openai.openai_img_gen_factory import OpenAIImgGenFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.misc.base_64_utils import prefixed_base64_str_from_base64_str


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

    @override
    async def _gen_image(
        self,
        img_gen_job: ImgGenJob,
    ) -> GeneratedImage:
        one_image_list = await self._gen_image_list(img_gen_job=img_gen_job, nb_images=1)
        return one_image_list[0]

    @override
    async def _gen_image_list(
        self,
        img_gen_job: ImgGenJob,
        nb_images: int,
    ) -> list[GeneratedImage]:
        image_size = OpenAIImgGenFactory.image_size_for_gpt_image_1(aspect_ratio=img_gen_job.job_params.aspect_ratio)
        output_format = OpenAIImgGenFactory.output_format_for_gpt_image_1(output_format=img_gen_job.job_params.output_format)
        moderation = OpenAIImgGenFactory.moderation_for_gpt_image_1(is_moderated=img_gen_job.job_params.is_moderated)
        background = OpenAIImgGenFactory.background_for_gpt_image_1(background=img_gen_job.job_params.background)
        quality = OpenAIImgGenFactory.quality_for_gpt_image_1(quality=img_gen_job.job_params.quality or Quality.LOW)
        output_compression = OpenAIImgGenFactory.output_compression_for_gpt_image_1()
        result = await self.openai_client.images.generate(
            prompt=img_gen_job.img_gen_prompt.positive_text,
            model=self.inference_model.model_id,
            moderation=moderation,
            background=background,
            quality=quality,
            size=image_size,
            output_format=output_format,
            output_compression=output_compression,
            n=nb_images,
        )
        if not result.data:
            msg = "No result from OpenAI"
            raise ImgGenGenerationError(msg)

        generated_images: list[GeneratedImage] = []
        for image_data in result.data:
            image_base64 = image_data.b64_json
            if not image_base64:
                msg = "No base64 image data received from OpenAI"
                raise ImgGenGenerationError(msg)

            base64_url = prefixed_base64_str_from_base64_str(b64_str=image_base64)
            generated_images.append(
                GeneratedImage(
                    url=base64_url,
                    width=1024,
                    height=1024,
                ),
            )
        return generated_images
