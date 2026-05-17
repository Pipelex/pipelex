import httpx
from typing_extensions import override

from pipelex.cogt.exceptions import CogtError, ImgGenGenerationError, ImgGenParameterError, InferenceErrorCategory
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_args_factory import ImgGenArgsFactory
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind, extract_azure_metadata, is_content_policy_violation
from pipelex.cogt.inference.transport_retry import request_with_transport_retry
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.config import get_config
from pipelex.hub import get_models_manager
from pipelex.plugins.plugin import Plugin
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.system.exceptions import CredentialsError
from pipelex.tools.log.log import log


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

    def _raise_categorized_azure_status_error(self, exc: httpx.HTTPStatusError) -> None:
        """Categorize an ``httpx.HTTPStatusError`` and raise the matching ``ImgGenGenerationError``."""
        status_code = exc.response.status_code
        error_body = exc.response.text
        metadata = extract_azure_metadata(exc)

        if status_code == 429:
            msg = f"Azure rate limit exceeded for model '{self.inference_model.desc}' (HTTP {status_code})"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.TRANSIENT,
                user_action=UserAction(
                    kind=UserActionKind.WAIT_AND_RETRY,
                    detail="Rate limited by Azure — the system will retry automatically",
                ),
                provider_metadata=metadata,
            ) from exc
        if status_code == 402:
            msg = f"Azure quota exhausted for model '{self.inference_model.desc}' (HTTP {status_code})"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.CAPACITY,
                user_action=UserAction(
                    kind=UserActionKind.CHECK_BILLING,
                    detail="Your Azure account has exceeded its quota — check billing in the Azure portal",
                ),
                provider_metadata=metadata,
            ) from exc
        if status_code in {401, 403}:
            msg = f"Azure authentication error for model '{self.inference_model.desc}' (HTTP {status_code})"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.CONFIGURATION,
                user_action=UserAction(
                    kind=UserActionKind.CHECK_CREDENTIALS,
                    detail="Azure rejected the API key — check your subscription key and permissions",
                ),
                provider_metadata=metadata,
            ) from exc
        if status_code == 404:
            msg = f"Azure deployment not found for model '{self.inference_model.desc}' (HTTP {status_code})"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.CONFIGURATION,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_MODEL,
                    detail=f"Deployment '{self.inference_model.model_id}' was not found — pick an available deployment",
                ),
                provider_metadata=metadata,
            ) from exc
        if status_code == 400:
            if is_content_policy_violation(error_body):
                msg = f"Content rejected by safety filters for model '{self.inference_model.desc}' (HTTP {status_code})"
                raise ImgGenGenerationError(
                    msg,
                    error_category=InferenceErrorCategory.CONTENT,
                    user_action=UserAction(
                        kind=UserActionKind.CHANGE_INPUT,
                        detail="Content was rejected by safety filters — revise the prompt",
                    ),
                    provider_metadata=metadata,
                ) from exc
            msg = f"Azure bad request for model '{self.inference_model.desc}' (HTTP {status_code})"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="Azure rejected the request — review the prompt and parameters",
                ),
                provider_metadata=metadata,
            ) from exc
        if status_code >= 500:
            msg = f"Azure server error (HTTP {status_code}) for model '{self.inference_model.desc}'"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.TRANSIENT,
                user_action=UserAction(
                    kind=UserActionKind.WAIT_AND_RETRY,
                    detail="Azure server error — the system will retry automatically",
                ),
                provider_metadata=metadata,
            ) from exc
        msg = f"Azure API error (HTTP {status_code}) for model '{self.inference_model.desc}'"
        raise ImgGenGenerationError(
            msg,
            error_category=InferenceErrorCategory.CONFIGURATION,
            user_action=UserAction(
                kind=UserActionKind.CONTACT_SUPPORT,
                detail=f"Azure returned an unexpected status code {status_code} — contact support if this persists",
            ),
            provider_metadata=metadata,
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

        # Build the API URL
        base_path = f"openai/deployments/{deployment}/images"
        params = f"?api-version={self.api_version}"
        generation_url = f"{self.endpoint}/{base_path}/generations{params}"

        # Tier 1 transport retry: this is a genuinely SDK-less path (raw httpx, no retrying SDK
        # in between), so it gets the transport-retry floor explicitly, from the same config
        # budget as the SDK-backed workers.
        async def _post_image_request() -> httpx.Response:
            async with httpx.AsyncClient() as client:
                http_response = await client.post(
                    generation_url,
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
            response_dict = response.json()
        except httpx.HTTPStatusError as exc:
            self._raise_categorized_azure_status_error(exc)
            raise  # unreachable: helper always raises
        except httpx.ConnectError as exc:
            metadata = extract_azure_metadata(exc)
            msg = f"Azure connection error for model '{self.inference_model.desc}': {exc}"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.TRANSIENT,
                user_action=UserAction(
                    kind=UserActionKind.WAIT_AND_RETRY,
                    detail="Could not reach Azure — the system will retry automatically",
                ),
                provider_metadata=metadata,
            ) from exc
        except httpx.TimeoutException as exc:
            metadata = extract_azure_metadata(exc)
            msg = f"Azure request timed out for model '{self.inference_model.desc}': {exc}"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.TRANSIENT,
                user_action=UserAction(
                    kind=UserActionKind.WAIT_AND_RETRY,
                    detail="Azure request timed out — the system will retry automatically",
                ),
                provider_metadata=metadata,
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
            width = int(width_str)
            height = int(height_str)
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
