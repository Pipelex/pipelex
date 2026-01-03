import asyncio
from typing import Any

from google import genai
from google.genai import types as genai_types
from typing_extensions import override

from pipelex import log
from pipelex.base_exceptions import PipelexError
from pipelex.cogt.exceptions import ImgGenGenerationError, SdkTypeError
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.google.google_img_gen_factory import GoogleImgGenFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol


class GoogleImgGenWorkerError(PipelexError):
    """Base exception for Google Image Generation Worker errors."""


class GoogleImgGenWorker(ImgGenWorkerAbstract):
    """Worker for generating images using Google Gemini Image models (Nano Banana)."""

    def __init__(
        self,
        sdk_instance: Any,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(inference_model=inference_model, reporting_delegate=reporting_delegate)

        if not isinstance(sdk_instance, genai.Client):
            msg = f"Provided ImgGen sdk_instance is not of type genai.Client: it's a '{type(sdk_instance)}'"
            raise SdkTypeError(msg)

        self.genai_client: genai.Client = sdk_instance
        self.genai_async_client = sdk_instance.aio

        # Capture the event loop at creation time if one is running
        self._event_loop: asyncio.AbstractEventLoop | None
        try:
            self._event_loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop at creation time
            self._event_loop = None

    @override
    def teardown(self):
        """Close the async client to free resources."""
        try:
            # First, try to use the loop captured at creation time if it's still running
            if self._event_loop is not None and self._event_loop.is_running():
                # Schedule cleanup on the captured loop and store reference to prevent garbage collection
                task = self._event_loop.create_task(self.genai_async_client.aclose())
                # Add a callback to log any errors that occur during cleanup
                task.add_done_callback(lambda t: log.debug(f"Google async client cleanup error: {t.exception()}") if t.exception() else None)
                log.verbose("Scheduled Google async client cleanup on captured event loop")
                return

            # Otherwise, try to get the current running loop
            try:
                current_loop = asyncio.get_running_loop()
                # Schedule cleanup on the current running loop and store reference to prevent garbage collection
                task = current_loop.create_task(self.genai_async_client.aclose())
                # Add a callback to log any errors that occur during cleanup
                task.add_done_callback(lambda t: log.debug(f"Google async client cleanup error: {t.exception()}") if t.exception() else None)
                log.verbose("Scheduled Google async client cleanup on current event loop")
            except RuntimeError:
                # No running event loop, we can safely use asyncio.run()
                try:
                    asyncio.run(self.genai_async_client.aclose())
                    log.verbose("Closed Google async client using asyncio.run()")
                except Exception as exc:
                    # Log but don't fail teardown if cleanup has issues
                    log.verbose(f"Error closing Google async client during teardown: {exc}")
        except Exception as exc:
            # Log but don't fail teardown if cleanup has issues
            log.debug(f"Error during Google async client teardown: {exc}")

    @override
    async def _gen_image(
        self,
        img_gen_job: ImgGenJob,
    ) -> GeneratedImageRawDetails:
        """Generate a single image using Google Gemini Image API."""
        prompt_text = img_gen_job.img_gen_prompt.positive_text
        aspect_ratio_str = GoogleImgGenFactory.aspect_ratio_string(img_gen_job.job_params.aspect_ratio)
        width, height = GoogleImgGenFactory.image_size_for_aspect_ratio(img_gen_job.job_params.aspect_ratio)

        # Build image config for aspect ratio
        image_config = genai_types.ImageConfig(
            aspect_ratio=aspect_ratio_str,
        )

        # Build generation config with image output
        generation_config = genai_types.GenerateContentConfig(
            response_modalities=["Image"],
            image_config=image_config,
        )

        # Generate content using async client
        response = await self.genai_async_client.models.generate_content(
            model=self.inference_model.model_id,
            contents=prompt_text,
            config=generation_config,
        )

        usage_metadata: genai_types.GenerateContentResponseUsageMetadata | None = response.usage_metadata
        if not usage_metadata:
            log.warning("No usage metadata returned from Google")

        # Extract image from response
        if not response.candidates:
            msg = f"No candidates returned from model: {self.inference_model.desc}"
            raise ImgGenGenerationError(msg)

        candidate = response.candidates[0]
        if not candidate.content or not candidate.content.parts:
            msg = f"No content parts in response from model: {self.inference_model.desc}"
            raise ImgGenGenerationError(msg)

        # Look for image data in response parts
        for part in candidate.content.parts:
            if part.inline_data is not None:
                image_bytes = part.inline_data.data
                if image_bytes is None:
                    continue
                mime_type = part.inline_data.mime_type
                if not mime_type:
                    msg = "No mime type returned from Google"
                    raise ImgGenGenerationError(msg)
                return GeneratedImageRawDetails(
                    actual_bytes=image_bytes,
                    size=ImageSize(width=width, height=height),
                    mime_type=mime_type,
                )

        msg = f"No image data in response from model: {self.inference_model.desc}"
        raise ImgGenGenerationError(msg)

    @override
    async def _gen_image_list(
        self,
        img_gen_job: ImgGenJob,
        nb_images: int,
    ) -> list[GeneratedImageRawDetails]:
        """Generate multiple images by calling _gen_image multiple times.

        Google Gemini Image API does not support generating multiple images in a single call,
        so we generate them sequentially.
        """
        generated_images: list[GeneratedImageRawDetails] = []
        # TODO: async gen images in parallel
        for _ in range(nb_images):
            image = await self._gen_image(img_gen_job=img_gen_job)
            generated_images.append(image)
        return generated_images
