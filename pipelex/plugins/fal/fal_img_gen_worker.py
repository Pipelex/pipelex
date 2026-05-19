from typing import Any

from fal_client import AsyncClient, InProgress
from fal_client.auth import MissingCredentialsError
from fal_client.client import FalClientError, FalClientHTTPError, FalClientTimeoutError
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import ImgGenGenerationError, ImgGenParameterError, InferenceErrorCategory, SdkTypeError
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.img_gen.img_gen_args_factory import ImgGenArgsFactory
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind, extract_fal_metadata
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.fal.fal_factory import FalFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.urls import URLs


class FalImgGenWorker(ImgGenWorkerAbstract):
    def __init__(
        self,
        sdk_instance: Any,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(inference_model=inference_model, reporting_delegate=reporting_delegate)

        if not isinstance(sdk_instance, AsyncClient):
            msg = f"Provided ImgGen sdk_instance is not of type fal_client.AsyncClient: it's a '{type(sdk_instance)}'"
            raise SdkTypeError(msg)

        self.fal_async_client = sdk_instance

    def _raise_categorized_fal_http_error(self, exc: FalClientHTTPError) -> None:
        """Categorize a ``FalClientHTTPError`` and raise the matching ``ImgGenGenerationError``."""
        status_code = exc.status_code
        metadata = extract_fal_metadata(exc)

        if status_code == 402:
            msg = f"FAL quota exhausted for model '{self.inference_model.desc}': {exc}"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.CAPACITY,
                user_action=UserAction(
                    kind=UserActionKind.CHECK_BILLING,
                    detail=f"Your FAL account has exceeded its quota — check billing at {URLs.fal_billing}",
                ),
                provider_metadata=metadata,
            ) from exc
        if status_code == 429:
            msg = f"FAL rate limit exceeded for model '{self.inference_model.desc}': {exc}"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.TRANSIENT,
                user_action=UserAction(
                    kind=UserActionKind.WAIT_AND_RETRY,
                    detail="Rate limited by FAL — the system will retry automatically",
                ),
                provider_metadata=metadata,
            ) from exc
        if status_code in {401, 403}:
            msg = f"FAL authentication error for model '{self.inference_model.desc}': {exc}"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.CONFIGURATION,
                user_action=UserAction(
                    kind=UserActionKind.CHECK_CREDENTIALS,
                    detail="FAL rejected the API key — check your credentials",
                ),
                provider_metadata=metadata,
            ) from exc
        if status_code == 404:
            msg = f"FAL model not found for '{self.inference_model.desc}': {exc}"
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
            msg = f"FAL bad request for model '{self.inference_model.desc}': {exc}"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="FAL rejected the request — review the prompt and parameters",
                ),
                provider_metadata=metadata,
            ) from exc
        if 400 <= status_code < 500:
            msg = f"FAL client error ({status_code}) for model '{self.inference_model.desc}': {exc}"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.CONFIGURATION,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="FAL rejected the request — review the prompt, parameters, and model configuration",
                ),
                provider_metadata=metadata,
            ) from exc
        msg = f"FAL API error ({status_code}) for model '{self.inference_model.desc}': {exc}"
        raise ImgGenGenerationError(
            msg,
            error_category=InferenceErrorCategory.TRANSIENT,
            user_action=UserAction(
                kind=UserActionKind.WAIT_AND_RETRY,
                detail="FAL returned an error — the system will retry automatically",
            ),
            provider_metadata=metadata,
        ) from exc

    async def _submit_and_get_result(
        self,
        img_gen_job: ImgGenJob,
        nb_images: int,
    ) -> Any:
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
        fal_application = args_dict.pop("model", None)
        if fal_application is None:
            msg = f"Model '{self.inference_model.name}' rules must include a 'model_choice' entry"
            raise ImgGenParameterError(msg)
        log.verbose(args_dict, title=f"Fal arguments, application={fal_application}")
        try:
            handler = await self.fal_async_client.submit(
                application=fal_application,
                arguments=args_dict,
            )

            log_index = 0
            async for event in handler.iter_events(with_logs=True):
                if isinstance(event, InProgress):
                    if not event.logs:
                        continue
                    new_logs = event.logs[log_index:]
                    for event_log in new_logs:
                        log.verbose(event_log["message"], title="FAL Log")
                    log_index = len(event.logs)

            return await handler.get()
        except MissingCredentialsError as exc:
            metadata = extract_fal_metadata(exc)
            msg = f"FAL API key not configured for model '{self.inference_model.desc}'"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.CONFIGURATION,
                user_action=UserAction(
                    kind=UserActionKind.CHECK_CREDENTIALS,
                    detail="Check that the FAL_KEY environment variable is set",
                ),
                provider_metadata=metadata,
            ) from exc
        except FalClientHTTPError as exc:
            self._raise_categorized_fal_http_error(exc)
            raise  # unreachable: helper always raises
        except FalClientTimeoutError as exc:
            metadata = extract_fal_metadata(exc)
            msg = f"FAL request timed out for model '{self.inference_model.desc}': {exc}"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.TRANSIENT,
                user_action=UserAction(
                    kind=UserActionKind.WAIT_AND_RETRY,
                    detail="FAL request timed out — the system will retry automatically",
                ),
                provider_metadata=metadata,
            ) from exc
        except FalClientError as exc:
            metadata = extract_fal_metadata(exc)
            msg = f"FAL error for model '{self.inference_model.desc}': {exc}"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.TRANSIENT,
                user_action=UserAction(
                    kind=UserActionKind.WAIT_AND_RETRY,
                    detail="FAL returned an error — the system will retry automatically",
                ),
                provider_metadata=metadata,
            ) from exc

    @override
    async def _gen_image(
        self,
        img_gen_job: ImgGenJob,
    ) -> GeneratedImageRawDetails:
        fal_result = await self._submit_and_get_result(img_gen_job=img_gen_job, nb_images=1)
        generated_image = FalFactory.make_generated_image(fal_result=fal_result)
        log.verbose(generated_image, title="generated_image")
        return generated_image

    @override
    async def _gen_image_list(
        self,
        img_gen_job: ImgGenJob,
        nb_images: int,
    ) -> list[GeneratedImageRawDetails]:
        fal_result = await self._submit_and_get_result(img_gen_job=img_gen_job, nb_images=nb_images)
        generated_image_list = FalFactory.make_generated_image_list(fal_result=fal_result)
        log.verbose(generated_image_list, title="generated_image_list")
        return generated_image_list
