from typing import Any

from huggingface_hub import AsyncInferenceClient
from PIL import Image
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import ImgGenParameterError, SdkTypeError
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.img_gen.img_gen_args_factory import ImgGenArgsFactory
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.misc.image_utils import ImageFormat


class HuggingFaceImgGenWorker(ImgGenWorkerAbstract):
    def __init__(
        self,
        sdk_instance: Any,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(inference_model=inference_model, reporting_delegate=reporting_delegate)

        if not isinstance(sdk_instance, AsyncInferenceClient):
            msg = f"Provided ImgGen sdk_instance is not of type huggingface_hub.AsyncInferenceClient: it's a '{type(sdk_instance)}'"
            raise SdkTypeError(msg)

        self.hf_async_client = sdk_instance

    async def _generate_single_image(
        self,
        img_gen_job: ImgGenJob,
    ) -> Image.Image:
        if self.inference_model.rules is None:
            msg = f"Model '{self.inference_model.name}' does not have rules configured"
            raise ImgGenParameterError(msg)
        args_dict = ImgGenArgsFactory.make_args_for_model(
            model_rules=self.inference_model.rules,
            img_gen_job=img_gen_job,
            nb_images=1,
            model_id=self.inference_model.model_id,
        )
        prompt = args_dict.pop("prompt")
        model_id = self.inference_model.model_id
        return await self.hf_async_client.text_to_image(
            prompt=prompt,
            model=model_id,
            extra_body=args_dict,
        )

    @override
    async def _gen_image(
        self,
        img_gen_job: ImgGenJob,
    ) -> GeneratedImageRawDetails:
        pil_image = await self._generate_single_image(img_gen_job=img_gen_job)
        output_format = img_gen_job.job_params.output_format or ImageFormat.PNG
        generated_image = GeneratedImageRawDetails.make_from_pil_image(pil_image=pil_image, image_format=output_format)
        log.verbose(generated_image, title="generated_image")
        return generated_image

    @override
    async def _gen_image_list(
        self,
        img_gen_job: ImgGenJob,
        nb_images: int,
    ) -> list[GeneratedImageRawDetails]:
        # HuggingFace's text_to_image doesn't support batch generation directly,
        # so we generate images one at a time
        generated_image_list: list[GeneratedImageRawDetails] = []
        for idx in range(nb_images):
            log.verbose(f"Generating image {idx + 1}/{nb_images}")
            generated_image = await self._gen_image(img_gen_job=img_gen_job)
            generated_image_list.append(generated_image)

        return generated_image_list
