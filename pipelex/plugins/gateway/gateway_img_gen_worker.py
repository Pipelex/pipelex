from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import httpx
from portkey_ai import AsyncPortkey
from portkey_ai.api_resources.utils import GenericResponse
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    retry_if_exception_type,
    retry_if_result,
    stop_after_delay,
    wait_random_exponential,
)
from typing_extensions import override

from pipelex import log, pretty_print
from pipelex.cogt.exceptions import ImgGenGeneratedTypeError, ImgGenGenerationError, SdkTypeError
from pipelex.cogt.image.generated_image import GeneratedImage
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.plugins.fal.fal_factory import FalFactory
from pipelex.plugins.gateway.gateway_img_gen_factory import GatewayImgGenFactory
from pipelex.tools.misc.tenacity_utils import log_retry

if TYPE_CHECKING:
    from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
    from pipelex.reporting.reporting_protocol import ReportingProtocol


def _as_str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _make_data_uri(*, base64_data: str, mime_subtype: str) -> str:
    return f"data:image/{mime_subtype};base64,{base64_data}"


def _make_generated_image_from_item(*, item: Any, default_mime_subtype: str) -> GeneratedImage:
    width_default = 1024
    height_default = 1024

    if isinstance(item, str):
        return GeneratedImage(url=item, width=width_default, height=height_default)

    if not isinstance(item, dict):
        msg = f"Unexpected image item type in Portkey response: {type(item)}"
        raise ImgGenGeneratedTypeError(msg)

    item_dict = cast("dict[str, Any]", item)

    mime_subtype = _as_str_or_none(item_dict.get("output_format")) or default_mime_subtype

    width_raw = item_dict.get("width")
    height_raw = item_dict.get("height")
    try:
        width = int(width_raw) if width_raw is not None else width_default
        height = int(height_raw) if height_raw is not None else height_default
    except (TypeError, ValueError) as exc:
        msg = "Width/height values in image item are not numeric"
        raise ImgGenGeneratedTypeError(msg) from exc

    url = item_dict.get("url") or item_dict.get("image_url")
    if isinstance(url, str) and url:
        return GeneratedImage(url=url, width=width, height=height)

    base64_data = item_dict.get("b64_json") or item_dict.get("image_base64") or item_dict.get("base64")
    if isinstance(base64_data, str) and base64_data:
        return GeneratedImage(
            url=_make_data_uri(base64_data=base64_data, mime_subtype=mime_subtype),
            width=width,
            height=height,
        )

    msg = "Could not find a usable image url/base64 field in Portkey image item"
    raise ImgGenGenerationError(msg)


def make_generated_image_list_from_portkey_payload(
    *,
    payload: Any,
    default_mime_subtype: str,
) -> list[GeneratedImage]:
    """Parse typical Portkey/Gateway image-generation payload shapes into GeneratedImage objects."""
    items: list[Any] | None = None

    if isinstance(payload, list):
        items = cast("list[Any]", payload)
    elif isinstance(payload, dict):
        payload_dict = cast("dict[str, Any]", payload)
        images_value = payload_dict.get("images")
        data_value = payload_dict.get("data")
        if isinstance(images_value, list):
            items = cast("list[Any]", images_value)
        elif isinstance(data_value, list):
            # OpenAI-like shape
            items = cast("list[Any]", data_value)
        else:
            image_value = payload_dict.get("image")
            if image_value is not None:
                items = [image_value]

    if not items:
        payload_type_name = type(cast("object", payload)).__name__
        msg = f"Could not parse any images from payload (type={payload_type_name})"
        raise ImgGenGenerationError(msg)

    generated_images: list[GeneratedImage] = []
    for item in items:
        generated_images.append(
            _make_generated_image_from_item(
                item=item,
                default_mime_subtype=default_mime_subtype,
            )
        )
    return generated_images


def _is_transient_http(exc: BaseException) -> bool:
    if not isinstance(exc, httpx.HTTPStatusError):
        return False
    code = exc.response.status_code
    return code == 429 or 500 <= code <= 599


async def _poll_fal_queue_until_complete(response_dict: dict[str, Any]) -> dict[str, Any]:
    """Poll fal Queue API until completion and return the final response JSON.

    Expects response_dict to include:
      - status_url (str)
      - response_url (str)

    Reads API key from env var FAL_KEY.
    """
    status_url = response_dict.get("status_url")
    response_url = response_dict.get("response_url")
    if not isinstance(status_url, str) or not isinstance(response_url, str):
        msg = "response_dict must include 'status_url' and 'response_url' as strings"
        raise TypeError(msg)

    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:

        async def _try_once() -> dict[str, Any] | None:
            # 1) poll status
            st = await client.get(status_url)
            st.raise_for_status()  # will be retried on 429/5xx via tenacity

            payload = st.json()
            status = payload.get("status")

            if status in {"IN_QUEUE", "IN_PROGRESS"}:
                return None  # tells tenacity to retry

            if status == "COMPLETED":
                # 2) fetch the actual response
                res = await client.get(response_url)
                res.raise_for_status()
                return cast("dict[str, Any]", res.json())

            # Terminal / unexpected states: fail fast (no retry)
            msg = f"fal request ended with status={status!r}: {payload}"
            raise RuntimeError(msg)

        retrying = AsyncRetrying(
            retry=(
                retry_if_result(lambda r: r is None)
                | retry_if_exception_type((httpx.TimeoutException, httpx.TransportError))
                | retry_if_exception(_is_transient_http)
            ),
            before_sleep=log_retry,
            wait=wait_random_exponential(multiplier=0.5, max=8.0),  # jittered backoff
            stop=stop_after_delay(300.0),  # total polling budget (seconds)
            reraise=True,
        )

        async for attempt in retrying:
            with attempt:
                result = await _try_once()
                if result is not None:
                    return result

    msg = "Polling ended unexpectedly"
    raise RuntimeError(msg)


class PortkeyImgGenWorker(ImgGenWorkerAbstract):
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
    ) -> GeneratedImage:
        one_image_list = await self._gen_image_list(img_gen_job=img_gen_job, nb_images=1)
        return one_image_list[0]

    @override
    async def _gen_image_list(
        self,
        img_gen_job: ImgGenJob,
        nb_images: int,
    ) -> list[GeneratedImage]:
        mime_subtype = GatewayImgGenFactory.mime_subtype_for_output_format(output_format=img_gen_job.job_params.output_format)

        common_args = FalFactory.make_common_args(img_gen_job=img_gen_job, nb_images=nb_images)
        args_for_model = FalFactory.make_args_for_model(model_id=self.inference_model.model_id, img_gen_job=img_gen_job)
        args_dict: dict[str, Any] = {**common_args, **args_for_model}
        pretty_print(args_dict, title="Gateway img-gen args")

        endpoint_path = f"/{self.inference_model.model_id}"
        response = await self.portkey_client.with_options(virtual_key="fal").post(url=endpoint_path, **args_dict)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

        if response is None:
            msg = f"Could not get a response for model '{self.inference_model.model_id}' via Portkey"
            raise ImgGenGenerationError(msg)

        if not isinstance(response, GenericResponse):
            msg = "Response is not of type GenericResponse"
            raise TypeError(msg)

        response_dict: dict[str, Any] = response.model_dump()

        # Handle FAL queue responses that require polling
        log.dev(f"FAL job status: {response_dict.get('status')}")
        if response_dict.get("status") in {"IN_QUEUE", "IN_PROGRESS"}:
            response_dict = await _poll_fal_queue_until_complete(response_dict)

        pretty_print(response_dict, title="FAL completed response")
        generated_images = make_generated_image_list_from_portkey_payload(
            payload=response_dict,
            default_mime_subtype=mime_subtype,
        )
        if not generated_images:
            msg = "No images returned by Portkey"
            raise ImgGenGenerationError(msg)
        return generated_images[:nb_images]
