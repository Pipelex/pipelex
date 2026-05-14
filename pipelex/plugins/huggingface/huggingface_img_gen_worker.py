from typing import Any

from huggingface_hub import AsyncInferenceClient
from huggingface_hub.errors import HfHubHTTPError, InferenceTimeoutError
from PIL import Image
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import ImgGenGenerationError, ImgGenParameterError, InferenceErrorCategory, SdkTypeError
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.img_gen.img_gen_args_factory import ImgGenArgsFactory
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind, extract_huggingface_metadata
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

    def _raise_categorized_hf_http_error(self, exc: HfHubHTTPError) -> None:
        """Categorize an ``HfHubHTTPError`` and raise the matching ``ImgGenGenerationError``."""
        status_code: int | None = None
        if hasattr(exc, "response") and exc.response is not None:
            status_code = exc.response.status_code
        metadata = extract_huggingface_metadata(exc)

        if status_code == 429:
            msg = f"HuggingFace rate limit exceeded for model '{self.inference_model.desc}': {exc}"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.TRANSIENT,
                user_action=UserAction(
                    kind=UserActionKind.WAIT_AND_RETRY,
                    detail="Rate limited by HuggingFace — the system will retry automatically",
                ),
                provider_metadata=metadata,
            ) from exc
        if status_code == 402:
            msg = f"HuggingFace quota exhausted for model '{self.inference_model.desc}': {exc}"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.CAPACITY,
                user_action=UserAction(
                    kind=UserActionKind.CHECK_BILLING,
                    detail="Your HuggingFace account has exceeded its quota — check billing in your HF dashboard",
                ),
                provider_metadata=metadata,
            ) from exc
        if status_code in {401, 403}:
            msg = f"HuggingFace authentication error for model '{self.inference_model.desc}': {exc}"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.CONFIGURATION,
                user_action=UserAction(
                    kind=UserActionKind.CHECK_CREDENTIALS,
                    detail="HuggingFace rejected the API token — check your credentials",
                ),
                provider_metadata=metadata,
            ) from exc
        if status_code == 404:
            msg = f"HuggingFace model not found for '{self.inference_model.desc}': {exc}"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.CONFIGURATION,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_MODEL,
                    detail=f"Model '{self.inference_model.model_id}' was not found — pick an available model",
                ),
                provider_metadata=metadata,
            ) from exc
        if status_code == 400:
            msg = f"HuggingFace bad request for model '{self.inference_model.desc}': {exc}"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="HuggingFace rejected the request — review the prompt and parameters",
                ),
                provider_metadata=metadata,
            ) from exc
        msg = f"HuggingFace API error for model '{self.inference_model.desc}': {exc}"
        raise ImgGenGenerationError(
            msg,
            error_category=InferenceErrorCategory.TRANSIENT,
            user_action=UserAction(
                kind=UserActionKind.WAIT_AND_RETRY,
                detail="HuggingFace returned an error — the system will retry automatically",
            ),
            provider_metadata=metadata,
        ) from exc

    async def _generate_single_image(
        self,
        img_gen_job: ImgGenJob,
    ) -> Image.Image:
        if self.inference_model.rules is None:
            msg = f"Model '{self.inference_model.name}' does not have rules configured"
            raise ImgGenParameterError(msg)
        args_dict = await ImgGenArgsFactory.make_args_for_model(
            model_rules=self.inference_model.rules,
            img_gen_job=img_gen_job,
            nb_images=1,
            model_id=self.inference_model.model_id,
            model_name=self.inference_model.name,
        )
        prompt = args_dict.pop("prompt")
        model_id = args_dict.pop("model", None)
        if model_id is None:
            msg = f"Model '{self.inference_model.name}' rules must include a 'model_choice' entry"
            raise ImgGenParameterError(msg)
        try:
            return await self.hf_async_client.text_to_image(
                prompt=prompt,
                model=model_id,
                extra_body=args_dict,
            )
        except InferenceTimeoutError as exc:
            metadata = extract_huggingface_metadata(exc)
            msg = f"HuggingFace request timed out for model '{self.inference_model.desc}': {exc}"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.TRANSIENT,
                user_action=UserAction(
                    kind=UserActionKind.WAIT_AND_RETRY,
                    detail="HuggingFace request timed out — the system will retry automatically",
                ),
                provider_metadata=metadata,
            ) from exc
        except HfHubHTTPError as exc:
            self._raise_categorized_hf_http_error(exc)
            raise  # unreachable: helper always raises

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
