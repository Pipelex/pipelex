import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from google import genai
from google.genai import types
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import LLMCompletionError
from pipelex.cogt.extract.extract_input import ExtractInputError
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_output import ExtractOutput, Page
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.google.google_factory import GoogleFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.misc.path_utils import clarify_path_or_url


class GoogleExtractWorker(ExtractWorkerAbstract):
    def __init__(
        self,
        sdk_instance: genai.Client,
        extra_config: dict[str, Any],
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(
            extra_config=extra_config,
            inference_model=inference_model,
            reporting_delegate=reporting_delegate,
        )
        genai_client: genai.Client = sdk_instance
        self.genai_async_client = genai_client.aio

    @override
    def teardown(self):
        """Close the async client to free resources."""
        try:
            # Try to get the running event loop
            asyncio.get_running_loop()
            # If there's a running loop, run the close in a separate thread
            # to avoid blocking or creating conflicts
            with ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self.genai_async_client.aclose())
                future.result(timeout=5)  # Wait up to 5 seconds for cleanup
        except RuntimeError:
            # No running event loop, we can safely use asyncio.run()
            try:
                asyncio.run(self.genai_async_client.aclose())
            except Exception as exc:
                # Log but don't fail teardown if cleanup has issues
                log.debug(f"Error closing Google async client during teardown: {exc}")
        except Exception as exc:
            # Log but don't fail teardown if cleanup has issues
            log.debug(f"Error during Google async client teardown: {exc}")

    @override
    async def _extract_pages(
        self,
        extract_job: ExtractJob,
    ) -> ExtractOutput:
        # TODO: report usage
        if image_uri := extract_job.extract_input.image_uri:
            extract_output = await self._make_extract_output_from_image(
                image_uri=image_uri,
                should_caption_image=extract_job.job_params.should_caption_images,
            )

        elif _ := extract_job.extract_input.pdf_uri:
            msg = "PDF extraction is not implemented for Google yet."
            raise NotImplementedError(msg)
        else:
            msg = "No image nor PDF URI provided in ExtractJob"
            raise ExtractInputError(msg)
        return extract_output

    async def _make_extract_output_from_image(
        self,
        image_uri: str,
        should_caption_image: bool = False,
    ) -> ExtractOutput:
        if should_caption_image:
            msg = "Captioning is not implemented for Google OCR."
            raise NotImplementedError(msg)
        # Determine if image_uri is a file path or URL
        image_path, image_url = clarify_path_or_url(path_or_uri=image_uri)
        if image_path:
            image = PromptImageFactory.make_prompt_image(file_path=image_path)
        elif image_url:
            image = PromptImageFactory.make_prompt_image(url=image_url)
        else:
            msg = f"Could not determine if image_uri is a path or URL: {image_uri}"
            raise ExtractInputError(msg)
        contents = await GoogleFactory.prepare_extract_contents(images=[image])

        # Build generation config
        generation_config = types.GenerateContentConfig(temperature=0.5)
        # Generate content using async client
        response = await self.genai_async_client.models.generate_content(
            model=self.inference_model.model_id,
            contents=contents,
            config=generation_config,
        )

        # Extract text from response
        if not response.candidates:
            msg = f"No candidates returned from model: {self.inference_model.desc}"
            raise LLMCompletionError(msg)

        candidate = response.candidates[0]
        if not candidate.content or not candidate.content.parts:
            msg = f"No content parts in response from model: {self.inference_model.desc}"
            raise LLMCompletionError(msg)

        # Extract text from the first part
        text_content = candidate.content.parts[0].text
        if not text_content:
            msg = f"No text content in response from model: {self.inference_model.desc}"
            raise LLMCompletionError(msg)

        return ExtractOutput(
            pages={
                1: Page(
                    text=text_content,
                ),
            },
        )
