from typing import Any, List, Optional

import openai
import shortuuid
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import ImggGenerationError, SdkTypeError
from pipelex.cogt.image.generated_image import GeneratedImage
from pipelex.cogt.imgg.imgg_engine import ImggEngine
from pipelex.cogt.imgg.imgg_job import ImggJob
from pipelex.cogt.imgg.imgg_job_components import Quality
from pipelex.cogt.imgg.imgg_worker_abstract import ImggWorkerAbstract, imgg_job_func
from pipelex.cogt.inference.inference_report_delegate import InferenceReportDelegate
from pipelex.config import get_config
from pipelex.plugins.openai.openai_imgg_factory import OpenAIImggFactory
from pipelex.tools.misc.base_64_utils import save_base64_to_binary_file
from pipelex.tools.misc.file_utils import ensure_path

TEMP_OUTPUTS_DIR = "temp/imgg_by_gpt_image"


class OpenAIImggWorker(ImggWorkerAbstract):
    def __init__(
        self,
        sdk_instance: Any,
        imgg_engine: ImggEngine,
        report_delegate: Optional[InferenceReportDelegate] = None,
    ):
        super().__init__(imgg_engine=imgg_engine, report_delegate=report_delegate)

        if not isinstance(sdk_instance, openai.AsyncOpenAI):
            raise SdkTypeError(f"Provided Imgg sdk_instance is not of type openai.AsyncOpenAI: it's a '{type(sdk_instance)}'")

        self.openai_client = sdk_instance

    @override
    @imgg_job_func
    async def gen_image(
        self,
        imgg_job: ImggJob,
    ) -> GeneratedImage:
        one_image_list = await self.gen_image_list(imgg_job=imgg_job, nb_images=1)
        generated_image = one_image_list[0]
        return generated_image

    @override
    @imgg_job_func
    async def gen_image_list(
        self,
        imgg_job: ImggJob,
        nb_images: int,
    ) -> List[GeneratedImage]:
        image_size = OpenAIImggFactory.image_size_for_gpt_image_1(aspect_ratio=imgg_job.job_params.aspect_ratio)
        output_format = OpenAIImggFactory.output_format_for_gpt_image_1(output_format=imgg_job.job_params.output_format)
        moderation = OpenAIImggFactory.moderation_for_gpt_image_1(is_moderated=imgg_job.job_params.is_moderated)
        background = OpenAIImggFactory.background_for_gpt_image_1(background=imgg_job.job_params.background)
        quality = OpenAIImggFactory.quality_for_gpt_image_1(quality=imgg_job.job_params.quality or Quality.LOW)
        output_compression = get_config().plugins.openai_config.image_output_compression
        result = await self.openai_client.images.generate(
            prompt=imgg_job.imgg_prompt.positive_text,
            model=self.imgg_engine.imgg_model_name,
            moderation=moderation,
            background=background,
            quality=quality,
            size=image_size,
            output_format=output_format,
            output_compression=output_compression,
            n=nb_images,
        )
        if not result.data:
            raise ImggGenerationError("No result from OpenAI")

        generated_image_list: List[GeneratedImage] = []
        image_id = shortuuid.uuid()[:4]
        for image_index, image_data in enumerate(result.data):
            image_base64 = image_data.b64_json
            if not image_base64:
                raise ImggGenerationError("No base64 image data received from OpenAI")

            folder_path = TEMP_OUTPUTS_DIR
            ensure_path(folder_path)
            img_path = f"{folder_path}/{image_id}_{image_index}.png"
            save_base64_to_binary_file(b64=image_base64, file_path=img_path)
            log.debug(f"Saved image to {img_path}")
            generated_image_list.append(
                GeneratedImage(
                    url=img_path,
                    width=1024,
                    height=1024,
                )
            )
        return generated_image_list
