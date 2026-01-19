import httpx
from typing_extensions import override

from pipelex.cogt.exceptions import CogtError, ImgGenGenerationError, ImgGenParameterError
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_args_factory import ImgGenArgsFactory
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.hub import get_models_manager
from pipelex.plugins.plugin import Plugin
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.system.exceptions import CredentialsError


class AzureCredentialsError(CredentialsError):
    pass


class AzureImgGenWorker(ImgGenWorkerAbstract):
    def __init__(
        self,
        plugin: Plugin,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(inference_model=inference_model, reporting_delegate=reporting_delegate)

        if plugin.sdk != "azure_rest_img_gen":
            msg = f"Plugin '{plugin}' is not supported for image generation"
            raise NotImplementedError(msg)
        self.plugin = plugin
        backend_name = self.plugin.backend
        backend = get_models_manager().get_required_inference_backend(backend_name)
        self.endpoint = backend.endpoint
        self.api_version = backend.extra_config.get("api_version")
        if not self.api_version:
            msg = "Azure OpenAI API version is not configured"
            raise CogtError(msg)
        if not backend.api_key:
            msg = "Azure OpenAI API key (subscription_key) is not configured"
            raise AzureCredentialsError(msg)
        self.api_key: str = backend.api_key

    #########################################################
    # Instance methods
    #########################################################

    @override
    def _check_can_perform_job(self, img_gen_job: ImgGenJob):
        # This can be overridden by subclasses for specific checks
        pass

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
        if self.inference_model.rules is None:
            msg = f"Model '{self.inference_model.name}' does not have rules configured"
            raise ImgGenParameterError(msg)

        args_dict = ImgGenArgsFactory.make_args_for_model(
            model_rules=self.inference_model.rules,
            img_gen_job=img_gen_job,
            nb_images=nb_images,
            model_id=self.inference_model.model_id,
        )

        args_dict["prompt"] = img_gen_job.img_gen_prompt.positive_text

        # Get deployment name (model_id from the inference model)
        deployment = self.inference_model.model_id

        # Build the API URL
        base_path = f"openai/deployments/{deployment}/images"
        params = f"?api-version={self.api_version}"
        generation_url = f"{self.endpoint}/{base_path}/generations{params}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                generation_url,
                headers={
                    "Api-Key": self.api_key,
                    "Content-Type": "application/json",
                },
                json=args_dict,
                timeout=180.0,
            )
            response.raise_for_status()
            response_dict = response.json()

        response_output_format: str | None = response_dict.get("output_format")
        if not response_output_format:
            msg = "No output format received from Azure"
            raise ImgGenGenerationError(msg)
        generated_images: list[GeneratedImageRawDetails] = []
        if images := response_dict.get("data"):
            size = response_dict.get("size")
            if not isinstance(size, str):
                msg = f"Size from img gen response is not a string: '{size}'"
                raise ImgGenGenerationError(msg)
            size_split = size.split("x")
            if len(size_split) != 2:
                msg = f"Size from img gen response is not a valid size: '{size}'"
                raise ImgGenGenerationError(msg)
            width_str, height_str = size_split
            width = int(width_str)
            height = int(height_str)
            for image in images:
                base64_str = image.get("b64_json")
                if not isinstance(base64_str, str):
                    msg = f"No base64 image data received from model '{self.inference_model.model_id}'"
                    raise ImgGenGenerationError(msg)
                generated_images.append(
                    GeneratedImageRawDetails(
                        base64_str=base64_str,
                        size=ImageSize(width=width, height=height),
                        image_format=response_output_format,
                    ),
                )
        else:
            msg = f"Unexpected response from model '{self.inference_model.model_id}' has no 'data' or 'images' key"
            raise ImgGenGenerationError(msg)

        return generated_images
