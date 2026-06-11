"""E2E tests for document inputs in PipeLLM using execute()."""

import pytest

from pipelex import pretty_print
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from tests.cases.documents import DocumentTestCases
from tests.e2e.pipelex.pipes.pipe_operators.pipe_llm.pipe_llm_document_inputs import (
    DocumentListAnalysisE2E,
    DocumentSummaryE2E,
    MixedMediaAnalysisE2E,
)
from tests.integration.pipelex.cogt.test_data import LLMVisionTestCases

LIBRARY_DIRS = ["tests/e2e/pipelex/pipes/pipe_operators"]


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.dry_runnable
@pytest.mark.asyncio
class TestDocumentInputsE2E:
    """E2E tests for document input handling using execute()."""

    async def test_direct_single_document(self, pipe_run_mode: PipeRunMode) -> None:
        """Test single direct document input with local PDF file."""
        pipeline_response = await PipelexMTHDSProtocol(library_dirs=LIBRARY_DIRS, pipe_run_mode=pipe_run_mode).execute(
            pipe_code="summarize_single_document_e2e",
            inputs={
                "document": DocumentContent(url=DocumentTestCases.PDF_FILE_PATH_2),
            },
        )

        assert pipeline_response.pipe_output.main_stuff is not None
        if pipe_run_mode.is_live:
            result = pipeline_response.pipe_output.main_stuff_as(content_type=DocumentSummaryE2E)
            pretty_print(result, title="Direct Document Summary")
            assert len(result.summary) > 10
            assert result.document_type.lower() in {"job offer", "job", "offer", "employment", "contract"}

    async def test_direct_single_document_by_url(self, pipe_run_mode: PipeRunMode) -> None:
        """Test single direct document input with remote URL."""
        pipeline_response = await PipelexMTHDSProtocol(library_dirs=LIBRARY_DIRS, pipe_run_mode=pipe_run_mode).execute(
            pipe_code="summarize_single_document_e2e",
            inputs={
                "document": DocumentContent(url=DocumentTestCases.PDF_FILE_URL_1),
            },
        )

        assert pipeline_response.pipe_output.main_stuff is not None
        if pipe_run_mode.is_live:
            result = pipeline_response.pipe_output.main_stuff_as(content_type=DocumentSummaryE2E)
            pretty_print(result, title="Document Summary (URL)")
            assert len(result.summary) > 10

    async def test_document_list_input(self, pipe_run_mode: PipeRunMode) -> None:
        """Test document list input counts documents correctly."""
        documents = ListContent[DocumentContent](
            items=[
                DocumentContent(url=DocumentTestCases.PDF_FILE_PATH_2),
                DocumentContent(url=DocumentTestCases.PDF_FILE_PATH_3),
            ]
        )

        pipeline_response = await PipelexMTHDSProtocol(library_dirs=LIBRARY_DIRS, pipe_run_mode=pipe_run_mode).execute(
            pipe_code="analyze_document_list_e2e",
            inputs={"documents": documents},
        )

        assert pipeline_response.pipe_output.main_stuff is not None
        if pipe_run_mode.is_live:
            analysis = pipeline_response.pipe_output.main_stuff_as(content_type=DocumentListAnalysisE2E)
            pretty_print(analysis, title="Document List Analysis")
            assert analysis.document_count == 2

    async def test_compare_document_lists(self, pipe_run_mode: PipeRunMode) -> None:
        """Test comparing two document collections."""
        collection_a = ListContent[DocumentContent](items=[DocumentContent(url=DocumentTestCases.PDF_FILE_PATH_2)])
        collection_b = ListContent[DocumentContent](items=[DocumentContent(url=DocumentTestCases.PDF_FILE_PATH_3)])

        pipeline_response = await PipelexMTHDSProtocol(library_dirs=LIBRARY_DIRS, pipe_run_mode=pipe_run_mode).execute(
            pipe_code="compare_document_lists_e2e",
            inputs={
                "collection_a": collection_a,
                "collection_b": collection_b,
            },
        )

        assert pipeline_response.pipe_output.main_stuff is not None
        if pipe_run_mode.is_live:
            analysis = pipeline_response.pipe_output.main_stuff_as(content_type=DocumentListAnalysisE2E)
            pretty_print(analysis, title="Document Lists Comparison")
            # Should count both collections
            assert analysis.document_count == 2

    async def test_mixed_document_and_image_inputs(self, pipe_run_mode: PipeRunMode) -> None:
        """Test combining document with image input."""
        pipeline_response = await PipelexMTHDSProtocol(library_dirs=LIBRARY_DIRS, pipe_run_mode=pipe_run_mode).execute(
            pipe_code="mixed_document_image_inputs_e2e",
            inputs={
                "document": DocumentContent(url=DocumentTestCases.PDF_FILE_PATH_2),
                "image": ImageContent(url=LLMVisionTestCases.URL_CLOUDFRONT_ALAN_TURING_JPG),
            },
        )

        assert pipeline_response.pipe_output.main_stuff is not None
        if pipe_run_mode.is_live:
            result = pipeline_response.pipe_output.main_stuff_as(content_type=MixedMediaAnalysisE2E)
            pretty_print(result, title="Mixed Document + Image Analysis")
            assert result.can_see_both is True
            assert len(result.document_summary) > 10
            assert len(result.image_summary) > 10
