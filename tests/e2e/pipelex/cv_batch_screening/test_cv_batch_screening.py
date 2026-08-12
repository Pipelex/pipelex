"""Direct-mode e2e test for the CV batch screening pipeline.

Runs the CV batch screening pipeline through ``PipelexMTHDSProtocol`` without any
Temporal layer. The same bundle is also exercised by the in-process Temporal test in
our Temporal plugin and by the ``/temporal-e2e-validate`` skill (distributed 3-process
validation). Each repo keeps its own copy of the crate (see ``test_data.py``).
"""

from pathlib import Path
from typing import Any, cast

import pytest

from pipelex import log
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.cases.documents import DocumentTestCases
from tests.e2e.pipelex.cv_batch_screening.test_data import CvBatchScreeningTemporalTestData


@pytest.mark.dry_runnable
@pytest.mark.llm
@pytest.mark.extract
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestCvBatchScreening:
    async def test_batch_analyze_cvs_for_job_offer_direct(self, pipe_run_mode: PipeRunMode):
        """Direct-mode (no Temporal) execution of the full batch screening pipeline.

        Uses real PDFs from ``tests/data/documents/`` in live mode; in dry mode the
        pipe controllers run end-to-end with mock content stamped at the operator
        boundaries.
        """
        mthds_content = Path(CvBatchScreeningTemporalTestData.BUNDLE_FILE).read_text(encoding="utf-8")

        runner = PipelexMTHDSProtocol(pipe_run_mode=pipe_run_mode)
        response = await runner.execute(
            pipe_code=CvBatchScreeningTemporalTestData.PIPE_CODE,
            mthds_contents=[mthds_content],
            inputs={
                "cvs": [
                    DocumentContent(url=DocumentTestCases.PDF_FILE_PATH_CV),
                ],
                "job_offer_pdf": DocumentContent(url=DocumentTestCases.PDF_FILE_PATH_2),
            },
        )
        pipe_output = response.pipe_output

        assert pipe_output is not None
        working_memory = pipe_output.working_memory
        assert working_memory is not None

        for stuff_name in CvBatchScreeningTemporalTestData.EXPECTED_STUFF_NAMES:
            assert working_memory.is_stuff_exists(stuff_name), f"Expected stuff '{stuff_name}' missing from output"

        match_analyses = working_memory.get_stuff("match_analyses")
        assert match_analyses.content is not None
        list_content = cast("ListContent[Any]", match_analyses.content)
        assert isinstance(list_content, ListContent), "match_analyses should be a ListContent"
        log.info(f"CV batch screening produced {len(list_content.items)} candidate matches")
