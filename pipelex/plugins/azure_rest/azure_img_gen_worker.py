import httpx
from typing_extensions import override

from pipelex.cogt.exceptions import CogtError
from pipelex.cogt.image.generated_image import GeneratedImage
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.hub import get_models_manager
from pipelex.plugins.azure_rest.azure_img_gen_factory import AzureImgGenFactory
from pipelex.plugins.plugin import Plugin
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.system.exceptions import CredentialsError


class AzureCredentialsError(CredentialsError):
    pass


class AzureImgGenConfigError(CogtError):
    pass


class AzureImgGenWorker(ImgGenWorkerAbstract):
    def __init__(
        self,
        plugin: Plugin,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(inference_model=inference_model, reporting_delegate=reporting_delegate)

        if plugin.sdk != "azure_rest":
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
        self.subscription_key: str = backend.api_key

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
    ) -> GeneratedImage:
        one_image_list = await self._gen_image_list(img_gen_job=img_gen_job, nb_images=1)
        return one_image_list[0]

    @override
    async def _gen_image_list(
        self,
        img_gen_job: ImgGenJob,
        nb_images: int,
    ) -> list[GeneratedImage]:
        """Generate multiple images using Azure OpenAI Image API."""
        # Extract parameters from the job
        img_gen_prompt_text = img_gen_job.img_gen_prompt.positive_text
        job_params = img_gen_job.job_params

        # Convert parameters to Azure format
        size, width, height = AzureImgGenFactory.image_size_for_azure(job_params.aspect_ratio)
        output_format = AzureImgGenFactory.output_format_for_azure(job_params.output_format)

        # Get deployment name (model_id from the inference model)
        deployment = self.inference_model.model_id

        # Build the API URL
        base_path = f"openai/deployments/{deployment}/images"
        params = f"?api-version={self.api_version}"
        generation_url = f"{self.endpoint}/{base_path}/generations{params}"

        # Build the request body
        generation_body = {
            "prompt": img_gen_prompt_text,
            "n": nb_images,
            "size": size,
            "background": job_params.background,
            "quality": job_params.quality,
            "output_format": output_format,
        }

        # Make the async HTTP request
        async with httpx.AsyncClient() as client:
            response = await client.post(
                generation_url,
                headers={
                    "Api-Key": self.subscription_key,
                    "Content-Type": "application/json",
                },
                json=generation_body,
                timeout=180.0,
            )
            response.raise_for_status()
            response_data = response.json()

        # Parse the response and create GeneratedImage objects
        generated_images: list[GeneratedImage] = []

        for item in response_data["data"]:
            # Get base64 image data
            b64_data = item["b64_json"]

            # Create data URI for the image (keeps it in memory)
            data_uri = f"data:image/{output_format};base64,{b64_data}"

            generated_images.append(
                GeneratedImage(
                    url=data_uri,
                    width=width,
                    height=height,
                )
            )

        return generated_images
