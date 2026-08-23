from __future__ import annotations

import base64
import io
from typing import TYPE_CHECKING, Any

from PIL import Image
from portkey_ai import AsyncPortkey

# The vendored openai package is the one AsyncPortkey.openai_client is built from, so the
# exceptions it raises are the vendored classes (not the real `openai` package's) — there is
# no public re-export of them in portkey_ai.
from portkey_ai._vendor import openai as portkey_vendored_openai  # ruff: ignore[import-private-name]
from portkey_ai.api_resources import exceptions as portkey_exceptions
from portkey_ai.api_resources.types.image_type import ImagesResponse
from pydantic import ValidationError
from typing_extensions import override

from pipelex.cogt.exceptions import ImgGenGenerationError, ImgGenParameterError, InferenceErrorCategory, SdkTypeError
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_args_factory import ImageFileTuple, ImgGenArgsFactory
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind, extract_gateway_metadata
from pipelex.cogt.inference.error_classify import classify_inference_error
from pipelex.cogt.inference.error_render import InferenceErrorFamily, render_inference_error
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.providers.fal.fal_poller import FalPoller
from pipelex.providers.gateway.gateway_schemas import GatewayImgGenAzureFlux2Pro, GatewayImgGenAzureGptImage
from pipelex.tools.misc.exceptions import FileTypeError
from pipelex.tools.misc.filetype_utils import detect_file_type_from_bytes
from pipelex.tools.misc.image_utils import ImageFormat
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

if TYPE_CHECKING:
    from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
    from pipelex.reporting.reporting_protocol import ReportingProtocol


class GatewayImgGenWorker(ImgGenWorkerAbstract):
    def __init__(
        self,
        sdk_instance: Any,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(inference_model=inference_model, reporting_delegate=reporting_delegate)

        if not isinstance(sdk_instance, AsyncPortkey):
            msg = f"Provided ImgGen sdk_instance for {self.__class__.__name__} is not of type portkey_ai.AsyncPortkey: it's a '{type(sdk_instance)}'"
            raise SdkTypeError(msg)

        self.portkey_client: AsyncPortkey = sdk_instance

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
        *,
        nb_images: int,
    ) -> list[GeneratedImageRawDetails]:
        if self.inference_model.rules is None:
            msg = f"Model '{self.inference_model.name}' does not have rules configured"
            raise ImgGenParameterError(msg)
        args_dict = await ImgGenArgsFactory.make_args_for_model(
            model_rules=self.inference_model.rules,
            img_gen_job=img_gen_job,
            nb_images=nb_images,
            model_id=self.inference_model.model_id,
            model_name=self.inference_model.name,
        )

        image_files: list[ImageFileTuple] | None = args_dict.pop("image", None)
        response_dict: dict[str, Any]
        # Declared rather than inferred: the SDK's image methods are typed with `**kwargs: Unknown`,
        # so calling them with a spread argument dict leaves pyright unable to name the result.
        response: Any
        try:
            # TODO: add portkey tracing headers when enabled
            if image_files is not None:
                # OpenAI's Images API splits generation and editing across two routes, and only
                # /images/edits accepts input images (/images/generations rejects them with a 400
                # "Unknown parameter"). Which route is called is the SDK method's business, and the
                # shape of the multipart body is too: a list under `image` is serialized as `image[]`
                # parts, a single file as the bare `image` field. That distinction is not cosmetic —
                # a server handed repeated bare `image` parts keeps one and silently drops the rest,
                # so an edit of several images would come back as a plausible edit of the first.
                images_arg: Any = image_files[0] if len(image_files) == 1 else list(image_files)
                response = await self.portkey_client.images.edit(image=images_arg, **args_dict)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            else:
                response = await self.portkey_client.images.generate(**args_dict)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            if not isinstance(response, ImagesResponse):
                msg = f"Response from model '{self.inference_model.name}' is not of type ImagesResponse: it's a '{type(response)}'"  # pyright: ignore[reportUnknownArgumentType]
                raise TypeError(msg)
            # Different backends and different models reach this worker, so the response shape is
            # detected below rather than assumed; ImagesResponse allows extra fields, which is what
            # carries `size`, `output_format` and `usage` through to that detection.
            response_dict = response.model_dump(serialize_as_any=True)
        except (portkey_exceptions.APIError, portkey_vendored_openai.APIError) as exc:
            metadata = extract_gateway_metadata(exc)
            classification = classify_inference_error(metadata)
            raise render_inference_error(
                metadata=metadata,
                classification=classification,
                family=InferenceErrorFamily.IMG_GEN,
                model_desc=self.inference_model.desc,
                model_handle=self.inference_model.name,
            ) from exc

        # Extract usage tokens if available
        if (usage_dict := response_dict.get("usage")) and (img_gen_tokens_usage := img_gen_job.job_report.img_gen_tokens_usage):
            nb_tokens: NbTokensByCategoryDict = {}
            if input_tokens := usage_dict.get("prompt_tokens") or usage_dict.get("input_tokens"):
                nb_tokens[TokenCategory.INPUT] = input_tokens
            if output_tokens := usage_dict.get("completion_tokens") or usage_dict.get("output_tokens"):
                nb_tokens[TokenCategory.OUTPUT] = output_tokens
            img_gen_tokens_usage.nb_tokens_by_category = nb_tokens

        generated_images: list[GeneratedImageRawDetails] = []
        if images := response_dict.get("data"):
            # Azure-shaped responses, model is either OpenAI's GPT Image or Black Forest Labs' Flux 2 Pro
            azure_gpt_image: GatewayImgGenAzureGptImage | None = None
            flux_2_pro_image: GatewayImgGenAzureFlux2Pro | None = None
            parsing_errors: str = ""
            try:
                response_azure_gpt_image = GatewayImgGenAzureGptImage.model_validate(response_dict)
                azure_gpt_image = response_azure_gpt_image
            except ValidationError as azure_gpt_image_error:
                validation_error_summary = format_pydantic_validation_error(azure_gpt_image_error)
                parsing_errors += f"Azure GPT Image: {validation_error_summary}\n"
                try:
                    response_flux_2_pro_image = GatewayImgGenAzureFlux2Pro.model_validate(response_dict)
                    flux_2_pro_image = response_flux_2_pro_image
                except ValidationError as flux_2_pro_image_error:
                    validation_error_summary = format_pydantic_validation_error(flux_2_pro_image_error)
                    parsing_errors += f"\n\nFlux 2 Pro: {validation_error_summary}\n"

            width: int
            height: int
            image_format: str | None
            if azure_gpt_image:
                image_format = response_dict.get("output_format")
                if not image_format:
                    msg = "No output format received from Gateway"
                    raise ImgGenGenerationError(
                        msg,
                        error_category=InferenceErrorCategory.UNKNOWN,
                        user_action=UserAction(
                            kind=UserActionKind.CHANGE_MODEL,
                            detail="The Gateway returned an image without an output format — try a different model",
                        ),
                        provider_metadata=None,
                    )
                size = response_dict.get("size")
                if not isinstance(size, str):
                    msg = f"Size from img gen response is not a string: '{size}'"
                    raise ImgGenGenerationError(
                        msg,
                        error_category=InferenceErrorCategory.UNKNOWN,
                        user_action=UserAction(
                            kind=UserActionKind.CHANGE_MODEL,
                            detail="The Gateway returned a malformed image size — try a different model",
                        ),
                        provider_metadata=None,
                    )
                size_split = size.split("x")
                if len(size_split) != 2:
                    msg = f"Size from img gen response is not a valid size: '{size}'"
                    raise ImgGenGenerationError(
                        msg,
                        error_category=InferenceErrorCategory.UNKNOWN,
                        user_action=UserAction(
                            kind=UserActionKind.CHANGE_MODEL,
                            detail="The Gateway returned a malformed image size — try a different model",
                        ),
                        provider_metadata=None,
                    )
                width_str, height_str = size_split
                try:
                    width = int(width_str)
                    height = int(height_str)
                except ValueError as exc:
                    msg = f"Size from img gen response has non-numeric dimensions: '{size}'"
                    raise ImgGenGenerationError(
                        msg,
                        error_category=InferenceErrorCategory.UNKNOWN,
                        user_action=UserAction(
                            kind=UserActionKind.CHANGE_MODEL,
                            detail="The Gateway returned a malformed image size — try a different model",
                        ),
                        provider_metadata=None,
                    ) from exc
            elif flux_2_pro_image:
                # Detect size and format from the first image's data
                first_image = images[0] if images else None
                if not first_image:
                    msg = "No images in Flux 2 Pro response"
                    raise ImgGenGenerationError(
                        msg,
                        error_category=InferenceErrorCategory.CONTENT,
                        user_action=UserAction(
                            kind=UserActionKind.CHANGE_INPUT,
                            detail="The Gateway returned no image — try rephrasing the prompt or using a different model",
                        ),
                        provider_metadata=None,
                    )
                first_base64 = first_image.get("b64_json")
                if not isinstance(first_base64, str):
                    msg = f"No base64 image data in first image from model '{self.inference_model.name}'"
                    raise ImgGenGenerationError(
                        msg,
                        error_category=InferenceErrorCategory.CONTENT,
                        user_action=UserAction(
                            kind=UserActionKind.CHANGE_INPUT,
                            detail="The Gateway returned no image data — try rephrasing the prompt or using a different model",
                        ),
                        provider_metadata=None,
                    )

                # Decode base64 once and detect file type and dimensions. A malformed
                # success body (invalid base64, an unrecognized/truncated image) must
                # surface as a categorized ImgGenGenerationError, not a raw
                # binascii/PIL exception — the latter escapes the Temporal PipelexError
                # bridge and gets retried, duplicating a billable generation.
                try:
                    image_bytes = base64.b64decode(first_base64)
                    image_format = ImageFormat.from_mime_type(
                        mime_type=detect_file_type_from_bytes(image_bytes).mime,
                    ).value
                    with Image.open(io.BytesIO(image_bytes)) as pil_img:
                        width, height = pil_img.size
                except (ValueError, OSError, FileTypeError) as exc:
                    msg = f"Could not decode the image returned by the Gateway for model '{self.inference_model.name}'"
                    raise ImgGenGenerationError(
                        msg,
                        error_category=InferenceErrorCategory.UNKNOWN,
                        user_action=UserAction(
                            kind=UserActionKind.CHANGE_MODEL,
                            detail="The Gateway returned a malformed image — try a different model",
                        ),
                        provider_metadata=None,
                    ) from exc
            else:
                msg = f"Could not parse image generation from Gateway response:\n{parsing_errors}"
                raise ImgGenGenerationError(
                    msg,
                    error_category=InferenceErrorCategory.UNKNOWN,
                    user_action=UserAction(
                        kind=UserActionKind.CHANGE_MODEL,
                        detail="The Gateway returned an unexpected response shape — try a different model",
                    ),
                    provider_metadata=None,
                )

            for image in images:
                base64_str = image.get("b64_json")
                if not isinstance(base64_str, str):
                    msg = f"No base64 image data received from model '{self.inference_model.name}'"
                    raise ImgGenGenerationError(
                        msg,
                        error_category=InferenceErrorCategory.CONTENT,
                        user_action=UserAction(
                            kind=UserActionKind.CHANGE_INPUT,
                            detail="The Gateway returned no image data — try rephrasing the prompt or using a different model",
                        ),
                        provider_metadata=None,
                    )
                generated_images.append(
                    GeneratedImageRawDetails(
                        base64_str=base64_str,
                        size=ImageSize(width=width, height=height),
                        image_format=image_format,
                    ),
                )

        elif response_dict.get("status") in {"IN_QUEUE", "IN_PROGRESS"}:
            # Handle FAL queue responses that require polling
            fal_poller = FalPoller()
            response_dict = await fal_poller.poll_queue_until_complete(response_dict=response_dict)

            for image in response_dict.get("images", []):
                url = image.get("url")
                if not isinstance(url, str):
                    msg = "Missing url field in image response"
                    raise ImgGenGenerationError(
                        msg,
                        error_category=InferenceErrorCategory.UNKNOWN,
                        user_action=UserAction(
                            kind=UserActionKind.CHANGE_MODEL,
                            detail="The Gateway returned an image without a url — try a different model",
                        ),
                        provider_metadata=None,
                    )
                fal_width = image.get("width")
                if not isinstance(fal_width, int):
                    msg = "Missing width field in image response"
                    raise ImgGenGenerationError(
                        msg,
                        error_category=InferenceErrorCategory.UNKNOWN,
                        user_action=UserAction(
                            kind=UserActionKind.CHANGE_MODEL,
                            detail="The Gateway returned an image without a width — try a different model",
                        ),
                        provider_metadata=None,
                    )
                fal_height = image.get("height")
                if not isinstance(fal_height, int):
                    msg = "Missing height field in image response"
                    raise ImgGenGenerationError(
                        msg,
                        error_category=InferenceErrorCategory.UNKNOWN,
                        user_action=UserAction(
                            kind=UserActionKind.CHANGE_MODEL,
                            detail="The Gateway returned an image without a height — try a different model",
                        ),
                        provider_metadata=None,
                    )
                content_type = image.get("content_type")
                if not isinstance(content_type, str):
                    msg = "Missing content_type field in image response"
                    raise ImgGenGenerationError(
                        msg,
                        error_category=InferenceErrorCategory.UNKNOWN,
                        user_action=UserAction(
                            kind=UserActionKind.CHANGE_MODEL,
                            detail="The Gateway returned an image without a content type — try a different model",
                        ),
                        provider_metadata=None,
                    )
                generated_image = GeneratedImageRawDetails(
                    actual_url_or_prefixed_base64=url,
                    size=ImageSize(width=fal_width, height=fal_height),
                    mime_type=content_type,
                )
                generated_images.append(generated_image)
        else:
            msg = f"Unexpected response from model '{self.inference_model.name}' has no 'data' or 'images' key"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.UNKNOWN,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_MODEL,
                    detail="The Gateway returned an unexpected response shape — try a different model",
                ),
                provider_metadata=None,
            )

        return generated_images
