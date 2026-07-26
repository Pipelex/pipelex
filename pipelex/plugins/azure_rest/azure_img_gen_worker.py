import json

import httpx
from typing_extensions import override

from pipelex.cogt.exceptions import CogtError, ImgGenGenerationError, ImgGenParameterError, InferenceErrorCategory
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_args_factory import ImageFileTuple, ImgGenArgsFactory
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.inference.error_classification import (
    UserAction,
    UserActionKind,
    extract_azure_metadata,
    extract_azure_metadata_from_response,
)
from pipelex.cogt.inference.error_classify import classify_inference_error
from pipelex.cogt.inference.error_render import InferenceErrorFamily, render_inference_error
from pipelex.cogt.inference.transport_retry import request_with_transport_retry
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.config import get_config
from pipelex.plugins.azure_rest.azure_exceptions import AzureCredentialsError
from pipelex.plugins.model_handle import ModelHandle
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.runtime_hub import get_models_manager
from pipelex.tools.log.log import log


class AzureImgGenWorker(ImgGenWorkerAbstract):
    def __init__(
        self,
        model_handle: ModelHandle,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(inference_model=inference_model, reporting_delegate=reporting_delegate)

        if model_handle.sdk != "azure_rest_img_gen":
            msg = f"ModelHandle '{model_handle}' is not supported for image generation"
            raise NotImplementedError(msg)
        self.model_handle = model_handle
        backend_name = self.model_handle.backend
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

    def _raise_categorized_azure_status_error(self, exc: httpx.HTTPStatusError) -> None:
        """Categorize an ``httpx.HTTPStatusError`` and raise the matching ``ImgGenGenerationError``.

        4xx statuses route through the shared Classify+Render pipeline; 5xx stays a worker-specific
        ``AMBIGUOUS`` branch because image generation is a non-idempotent POST and the shared
        classifier (which is operation-agnostic) would mis-mark these as ``TRANSIENT`` and let
        the Temporal bridge auto-retry — duplicating a billed generation.
        """
        metadata = extract_azure_metadata(exc)
        status_code = exc.response.status_code
        if status_code >= 500:
            msg = f"Azure server error (HTTP {status_code}) for model '{self.inference_model.desc}'"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.AMBIGUOUS,
                user_action=UserAction(
                    kind=UserActionKind.WAIT_AND_RETRY,
                    detail="Azure server error after submission — the outcome is unknown; retry manually after checking for a duplicate image",
                ),
                provider_metadata=metadata,
            ) from exc
        classification = classify_inference_error(metadata)
        raise render_inference_error(
            metadata=metadata,
            classification=classification,
            family=InferenceErrorFamily.IMG_GEN,
            model_desc=self.inference_model.desc,
            model_handle=self.inference_model.name,
        ) from exc

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

        args_dict["prompt"] = img_gen_job.img_gen_prompt.positive_text

        # Get deployment name (model_id from the inference model)
        deployment = self.inference_model.model_id

        # Build the API URL. Azure's Images API splits generation and editing across two REST
        # routes, and only /images/edits accepts the 'image' parameter (/images/generations
        # rejects it with a 400 "Unknown parameter"). The args factory maps input images to
        # httpx-style file tuples under "image".
        base_path = f"openai/deployments/{deployment}/images"
        params = f"?api-version={self.api_version}"
        image_files: list[ImageFileTuple] | None = args_dict.pop("image", None)
        route = "edits" if image_files is not None else "generations"
        image_url = f"{self.endpoint}/{base_path}/{route}{params}"

        # Tier 1 transport retry: this is a genuinely SDK-less path (raw httpx, no retrying SDK
        # in between), so it gets the transport-retry floor explicitly, from the same config
        # budget as the SDK-backed workers.
        async def _post_image_request() -> httpx.Response:
            async with httpx.AsyncClient() as client:
                if image_files is not None:
                    # OpenAI's multipart convention for /images/edits (matching the openai SDK's
                    # extract_files serialization): a single input image is the bare 'image' field,
                    # but multiple images must each go under 'image[]' — repeated bare 'image' parts
                    # are collapsed to one by the server, silently dropping the others.
                    image_field_name = "image[]" if len(image_files) > 1 else "image"
                    http_response = await client.post(
                        image_url,
                        headers={"Api-Key": self.api_key},
                        data={key: str(value) for key, value in args_dict.items()},
                        files=[(image_field_name, image_file) for image_file in image_files],
                        timeout=600.0,
                    )
                else:
                    http_response = await client.post(
                        image_url,
                        headers={
                            "Api-Key": self.api_key,
                            "Content-Type": "application/json",
                        },
                        json=args_dict,
                        timeout=600.0,
                    )
                http_response.raise_for_status()
                return http_response

        try:
            # Image generation is a billable, non-idempotent POST: once the request reaches Azure,
            # a retry could generate (and bill) a second image. retry_on_ambiguous_failure=False
            # keeps the retry to failures that prove Azure did no work — the request was never
            # delivered (connect / pool errors), or Azure rejected it before generating (408 / 429).
            response = await request_with_transport_retry(
                send_request=_post_image_request,
                max_retries=get_config().cogt.transport_max_retries,
                retry_on_ambiguous_failure=False,
            )
        except httpx.HTTPStatusError as exc:
            self._raise_categorized_azure_status_error(exc)
            raise  # unreachable: helper always raises
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            # Pre-request transport failures: the request never reached Azure (the connection was
            # never established or never acquired from the pool), so no billable work was done.
            # Safe to retry — routed through the shared classifier, which maps these to TRANSIENT.
            # Must precede the httpx.TimeoutException clause below (ConnectTimeout / PoolTimeout are
            # subclasses).
            metadata = extract_azure_metadata(exc)
            classification = classify_inference_error(metadata)
            raise render_inference_error(
                metadata=metadata,
                classification=classification,
                family=InferenceErrorFamily.IMG_GEN,
                model_desc=self.inference_model.desc,
                model_handle=self.inference_model.name,
            ) from exc
        except httpx.TimeoutException as exc:
            # Remaining timeouts — ReadTimeout / WriteTimeout — fire after the request reached
            # Azure, so the outcome is ambiguous: Azure may have generated (and billed) the image.
            # Image generation is a non-idempotent POST, so this is categorized AMBIGUOUS
            # (non-retryable) — an automatic Temporal retry could duplicate the generation. The
            # pre-request timeouts are peeled off by the clause above.
            metadata = extract_azure_metadata(exc)
            msg = f"Azure request timed out mid-request for model '{self.inference_model.desc}': {exc}"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.AMBIGUOUS,
                user_action=UserAction(
                    kind=UserActionKind.WAIT_AND_RETRY,
                    detail="Azure timed out mid-request — the outcome is unknown; retry manually after checking for a duplicate image",
                ),
                provider_metadata=metadata,
            ) from exc
        except httpx.TransportError as exc:
            # Catch-all for the remaining httpx.TransportError family — ReadError / WriteError /
            # RemoteProtocolError and the like — which fire when the connection drops mid-request.
            # The connect/timeout handlers above are also TransportError subclasses, so this clause
            # must stay last; without it these escape unwrapped, bypassing the categorized error.
            # The outcome is ambiguous — the request may have reached Azure and generated (and
            # billed) an image — so for this non-idempotent POST it is categorized AMBIGUOUS
            # (non-retryable): an automatic Temporal retry could duplicate the generation.
            metadata = extract_azure_metadata(exc)
            msg = f"Azure transport error for model '{self.inference_model.desc}': {exc}"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.AMBIGUOUS,
                user_action=UserAction(
                    kind=UserActionKind.WAIT_AND_RETRY,
                    detail="The connection to Azure failed mid-request — the outcome is unknown; retry manually after checking for a duplicate image",
                ),
                provider_metadata=metadata,
            ) from exc

        # The HTTP status was successful, but Azure (or an intermediary gateway) can still
        # return a malformed or non-JSON body. json() raises a json.JSONDecodeError here, so
        # categorize it as a worker error rather than letting a raw ValueError escape uncategorized.
        try:
            response_dict = response.json()
        except json.JSONDecodeError as exc:
            metadata = extract_azure_metadata_from_response(response, sdk_exception_type=type(exc).__name__, message=str(exc))
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
            log.debug(usage_dict, title="Azure img gen usage")
            nb_tokens: NbTokensByCategoryDict = {}
            input_tokens = usage_dict.get("prompt_tokens")
            if input_tokens is None:
                input_tokens = usage_dict.get("input_tokens")
            if input_tokens is not None:
                nb_tokens[TokenCategory.INPUT] = input_tokens
            output_tokens = usage_dict.get("completion_tokens")
            if output_tokens is None:
                output_tokens = usage_dict.get("output_tokens")
            if output_tokens is not None:
                nb_tokens[TokenCategory.OUTPUT] = output_tokens
            img_gen_tokens_usage.nb_tokens_by_category = nb_tokens

        response_output_format: str | None = response_dict.get("output_format")
        if not response_output_format:
            msg = "No output format received from Azure"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.UNKNOWN,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_MODEL,
                    detail="Azure returned an image without an output format — try a different model",
                ),
                provider_metadata=None,
            )
        generated_images: list[GeneratedImageRawDetails] = []
        if images := response_dict.get("data"):
            size = response_dict.get("size")
            if not isinstance(size, str):
                msg = f"Size from img gen response is not a string: '{size}'"
                raise ImgGenGenerationError(
                    msg,
                    error_category=InferenceErrorCategory.UNKNOWN,
                    user_action=UserAction(
                        kind=UserActionKind.CHANGE_MODEL,
                        detail="Azure returned a malformed image size — try a different model",
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
                        detail="Azure returned a malformed image size — try a different model",
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
                        detail="Azure returned a malformed image size — try a different model",
                    ),
                    provider_metadata=None,
                ) from exc
            for image in images:
                base64_str = image.get("b64_json")
                if not isinstance(base64_str, str):
                    msg = f"No base64 image data received from model '{self.inference_model.model_id}'"
                    raise ImgGenGenerationError(
                        msg,
                        error_category=InferenceErrorCategory.CONTENT,
                        user_action=UserAction(
                            kind=UserActionKind.CHANGE_INPUT,
                            detail="Azure returned no image data — try rephrasing the prompt or using a different model",
                        ),
                        provider_metadata=None,
                    )
                generated_images.append(
                    GeneratedImageRawDetails(
                        base64_str=base64_str,
                        size=ImageSize(width=width, height=height),
                        image_format=response_output_format,
                    ),
                )
        else:
            msg = f"Unexpected response from model '{self.inference_model.model_id}' has no 'data' or 'images' key"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.UNKNOWN,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_MODEL,
                    detail="Azure returned an unexpected response shape — try a different model",
                ),
                provider_metadata=None,
            )

        return generated_images
