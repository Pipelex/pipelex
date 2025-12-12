from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

import httpx
from portkey_ai import AsyncPortkey
from portkey_ai.api_resources.utils import GenericResponse
from typing_extensions import override

from pipelex import log, pretty_print
from pipelex.cogt.exceptions import ImgGenGeneratedTypeError, ImgGenGenerationError, SdkTypeError
from pipelex.cogt.image.generated_image import GeneratedImage
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.plugins.gateway.gateway_img_gen_factory import GatewayImgGenFactory

if TYPE_CHECKING:
    from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
    from pipelex.reporting.reporting_protocol import ReportingProtocol

# FAL queue polling constants
FAL_POLL_INTERVAL_SECONDS = 1.0
FAL_MAX_POLL_DURATION_SECONDS = 300.0


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


async def _poll_fal_queue_until_complete(response_dict: dict[str, Any]) -> dict[str, Any]:
    """Poll FAL queue status until the job completes and return the final result."""
    response_url = response_dict.get("response_url")
    status_url = response_dict.get("status_url")

    if not response_url:
        msg = "FAL queued response is missing response_url"
        raise ImgGenGenerationError(msg)
    if not status_url:
        msg = "FAL queued response is missing status_url"
        raise ImgGenGenerationError(msg)

    log.verbose(f"FAL job queued, polling status at: {status_url}")

    loop = asyncio.get_event_loop()
    start_time = loop.time()

    async with httpx.AsyncClient() as client:
        while True:
            elapsed = loop.time() - start_time
            if elapsed > FAL_MAX_POLL_DURATION_SECONDS:
                msg = f"FAL job timed out after {FAL_MAX_POLL_DURATION_SECONDS} seconds"
                raise ImgGenGenerationError(msg)

            # Check status
            status_response = await client.get(status_url, timeout=30.0)
            status_response.raise_for_status()
            status_data = status_response.json()

            status = status_data.get("status")
            log.verbose(f"FAL job status: {status} (elapsed: {elapsed:.1f}s)")

            if status == "COMPLETED":
                # Fetch the final result from response_url
                result_response = await client.get(response_url, timeout=60.0)
                result_response.raise_for_status()
                result_data: dict[str, Any] = result_response.json()
                log.verbose(result_data, title="FAL completed result")
                return result_data

            if status == "FAILED":
                error_msg = status_data.get("error", "Unknown error")
                msg = f"FAL job failed: {error_msg}"
                raise ImgGenGenerationError(msg)

            # Still in progress, wait and retry
            await asyncio.sleep(FAL_POLL_INTERVAL_SECONDS)


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
        image_size = GatewayImgGenFactory.image_size_for_gateway(aspect_ratio=img_gen_job.job_params.aspect_ratio)
        output_format = GatewayImgGenFactory.output_format_for_gateway(output_format=img_gen_job.job_params.output_format)
        mime_subtype = GatewayImgGenFactory.mime_subtype_for_output_format(output_format=img_gen_job.job_params.output_format)

        payload = {
            "prompt": img_gen_job.img_gen_prompt.positive_text,
            "guidance_scale": img_gen_job.job_params.guidance_scale,
            "num_inference_steps": img_gen_job.job_params.nb_steps,
            "image_size": image_size,
            "num_images": 2,
            "enable_safety_checker": img_gen_job.job_params.is_moderated,
            "output_format": output_format,
            "seed": img_gen_job.job_params.seed,
        }

        endpoint_path = f"/{self.inference_model.model_id}"
        # endpoint_path = "/flux-2"
        response = await self.portkey_client.with_options(virtual_key="fal").post(url=endpoint_path, **payload)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

        if response is None:
            msg = f"Could not get a response for model '{self.inference_model.model_id}' via Portkey"
            raise ImgGenGenerationError(msg)

        if not isinstance(response, GenericResponse):
            msg = "Response is not of type GenericResponse"
            raise TypeError(msg)

        pretty_print(response, title="Gateway img-gen response")
        response_dict: dict[str, Any] = response.model_dump()

        # Handle FAL queue responses that require polling
        if response_dict.get("status") in {"IN_QUEUE", "IN_PROGRESS"} and "response_url" in response_dict:
            response_dict = await _poll_fal_queue_until_complete(response_dict)

        generated_images = make_generated_image_list_from_portkey_payload(
            payload=response_dict,
            default_mime_subtype=mime_subtype,
        )
        if not generated_images:
            msg = "No images returned by Portkey"
            raise ImgGenGenerationError(msg)
        return generated_images[:nb_images]
