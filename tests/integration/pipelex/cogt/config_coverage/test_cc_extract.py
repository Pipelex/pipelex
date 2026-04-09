import pytest

from pipelex import log, pretty_print
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobParams
from pipelex.cogt.extract.extract_job_factory import ExtractJobFactory
from pipelex.hub import get_extract_worker
from pipelex.pipeline.job_metadata import JobMetadata
from tests.cases.documents import DocumentTestCases
from tests.integration.pipelex.fixtures.model_combo import ModelCombo


@pytest.mark.extract
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestConfigCoverageExtract:
    async def test_extract_pdf(self, job_metadata: JobMetadata, extract_combo: ModelCombo, extract_job_params: ExtractJobParams) -> None:
        """Verify that PDF extraction works for this Portkey config."""
        log.info(f"Config coverage: testing extract '{extract_combo.handle}'")
        extract_worker = get_extract_worker(extract_handle=extract_combo.handle)
        if not extract_worker.is_pdf_supported:
            pytest.skip(f"PDF extraction not supported for '{extract_worker.desc}'")
        extract_job = ExtractJobFactory.make_extract_job(
            extract_input=ExtractInput(document_uri=DocumentTestCases.PDF_FILE_PATH_1),
            extract_job_params=extract_job_params,
            job_metadata=job_metadata,
        )
        extract_output = await extract_worker.extract_pages(extract_job=extract_job)
        assert extract_output.pages
        pretty_print(extract_output, title=f"Extract output for '{extract_combo.handle}'")
