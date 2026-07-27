"""Tests for LLM document understanding capabilities."""

import pytest

from pipelex import log, pretty_print
from pipelex.cogt.document.prompt_document import PromptDocumentUri
from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.llm.llm_job_factory import LLMJobFactory
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.runtime_hub import get_llm_worker
from pipelex.system.job_metadata import JobMetadata
from tests.integration.pipelex.cogt.test_data import LLMDocumentTestCases
from tests.integration.pipelex.fixtures.model_combo import ModelCombo


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestLLMDocument:
    """Tests for passing documents to LLM Workers."""

    @pytest.mark.parametrize(("topic", "document_path"), LLMDocumentTestCases.PDF_DOCUMENT_PATHS)
    async def test_gen_text_from_document_by_path(
        self,
        job_metadata: JobMetadata,
        llm_job_params: LLMJobParams,
        llm_combo: ModelCombo,
        topic: str,
        document_path: str,
    ):
        """Test LLM text generation from a local document file."""
        prompt_document = PromptDocumentUri(uri=document_path)
        llm_worker = get_llm_worker(llm_handle=llm_combo.handle)
        log.info(f"Using llm_worker: {llm_worker.desc}")
        llm_job = LLMJobFactory.make_llm_job(
            llm_prompt=LLMPrompt(
                user_text=LLMDocumentTestCases.DOCUMENT_USER_TEXT,
                user_documents=[prompt_document],
            ),
            job_metadata=job_metadata,
            llm_job_params=llm_job_params,
        )

        try:
            generated_text = await llm_worker.gen_text(llm_job=llm_job)
            assert generated_text
            pretty_print(generated_text, title=f"Document summary of {topic}")
        except LLMCapabilityError as exc:
            pytest.skip(f"Document capability not supported for this LLM: {llm_combo.handle} because {exc}")

    @pytest.mark.parametrize(("topic", "document_url"), LLMDocumentTestCases.DOCUMENT_URLS)
    async def test_gen_text_from_document_by_url(
        self,
        job_metadata: JobMetadata,
        llm_job_params: LLMJobParams,
        llm_combo: ModelCombo,
        topic: str,
        document_url: str,
    ):
        """Test LLM text generation from a remote document URL."""
        prompt_document = PromptDocumentUri(uri=document_url)
        llm_worker = get_llm_worker(llm_handle=llm_combo.handle)
        log.info(f"Using llm_worker: {llm_worker.desc}")
        llm_job = LLMJobFactory.make_llm_job(
            llm_prompt=LLMPrompt(
                user_text=LLMDocumentTestCases.DOCUMENT_USER_TEXT,
                user_documents=[prompt_document],
            ),
            job_metadata=job_metadata,
            llm_job_params=llm_job_params,
        )

        try:
            generated_text = await llm_worker.gen_text(llm_job=llm_job)
            assert generated_text
            pretty_print(generated_text, title=f"Document summary of {topic} (URL)")
        except LLMCapabilityError as exc:
            pytest.skip(f"Document capability not supported for this LLM: {llm_combo.handle} because {exc}")
