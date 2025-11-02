from typing import Any

from typing_extensions import override

from pipelex.cogt.extract.extract_input import ExtractInputError
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_output import ExtractOutput, Page
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_worker_internal_abstract import LLMWorkerInternalAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.misc.path_utils import clarify_path_or_url


class VlmExtractWorker(ExtractWorkerAbstract):
    def __init__(
        self,
        llm_worker: LLMWorkerInternalAbstract,
        extra_config: dict[str, Any],
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(
            extra_config=extra_config,
            inference_model=inference_model,
            reporting_delegate=reporting_delegate,
        )
        if llm_worker.is_vision_supported:
            self.llm_worker = llm_worker
        else:
            msg = "LLM worker must support vision for VLM extraction"
            raise ValueError(msg)

    #########################################################
    # Instance methods
    #########################################################

    @property
    @override
    def desc(self) -> str:
        return f"Extraction using {self.inference_model.desc}"

    @override
    async def _extract_pages(
        self,
        extract_job: ExtractJob,
    ) -> ExtractOutput:
        if image_uri := extract_job.extract_input.image_uri:
            extract_output = await self._make_extract_output_from_image(
                image_uri=image_uri,
                extract_job=extract_job,
            )

        elif _ := extract_job.extract_input.pdf_uri:
            msg = "PDF extraction is not implemented for VLM yet."
            raise NotImplementedError(msg)
        else:
            msg = "No image nor PDF URI provided in ExtractJob"
            raise ExtractInputError(msg)
        return extract_output

    async def _make_extract_output_from_image(
        self,
        image_uri: str,
        extract_job: ExtractJob,
    ) -> ExtractOutput:
        # Determine if image_uri is a file path or URL
        image_path, image_url = clarify_path_or_url(path_or_uri=image_uri)
        if image_path:
            image = PromptImageFactory.make_prompt_image(file_path=image_path)
        elif image_url:
            image = PromptImageFactory.make_prompt_image(url=image_url)
        else:
            msg = f"Could not determine if image_uri is a path or URL: {image_uri}"
            raise ExtractInputError(msg)

        # Build LLM prompt for text extraction
        llm_prompt = LLMPrompt(
            user_text="Extract all text from this image.",
            user_images=[image],
        )

        # Build LLM job
        llm_job = LLMJob(
            llm_prompt=llm_prompt,
            job_params=LLMJobParams(
                temperature=0.0,
                max_tokens=None,
                seed=None,
            ),
            job_config=LLMJobConfig(
                is_streaming_enabled=False,
                max_retries=3,
            ),
            job_metadata=extract_job.job_metadata,
        )

        # Execute extraction using LLM worker
        text_content = await self.llm_worker.gen_text(llm_job=llm_job)

        return ExtractOutput(
            pages={
                1: Page(
                    text=text_content,
                ),
            },
        )
