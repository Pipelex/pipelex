"""E2E test for PipeCompose with CV Job Matching pipeline."""

import pytest

from pipelex import pretty_print
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.cases import DocumentTestCases
from tests.e2e.pipelex.pipes.pipe_operators.pipe_compose.cv_job_matching_itvw_sheet import InterviewSheet


@pytest.mark.llm
@pytest.mark.extract
@pytest.mark.inference
@pytest.mark.dry_runnable
@pytest.mark.asyncio
class TestPipeComposeAfterInference:
    """E2E tests for the PipeCompose after inference pipeline."""

    async def test_pipe_compose_after_inference(self, pipe_run_mode: PipeRunMode):
        """Test a pipe which uses inference to analyze stuff and then uses PipeCompose to compose a structured content."""
        runner = PipelexMTHDSProtocol(
            library_dirs=["tests/e2e/pipelex/pipes/pipe_operators/pipe_compose"],
            pipe_run_mode=pipe_run_mode,
        )
        response = await runner.execute(
            pipe_code="cv_job_matcher",
            inputs={
                "cv_pdf": DocumentContent(url=DocumentTestCases.PDF_FILE_PATH_CV),
                "job_offer_pdf": DocumentContent(url=DocumentTestCases.PDF_FILE_PATH_2),
            },
        )
        pipe_output = response.pipe_output

        # Basic assertions
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        # Get the result as InterviewSheet
        interview_sheet = pipe_output.main_stuff_as(content_type=InterviewSheet)

        # Log output for debugging
        pretty_print(interview_sheet, title="Interview Sheet")

        # Verify the composed output structure
        assert interview_sheet is not None
        assert isinstance(interview_sheet, InterviewSheet)

        # Verify fields composed from match_analysis
        assert interview_sheet.overall_match_score is not None
        assert interview_sheet.matching_skills is not None
        assert interview_sheet.experience_alignment is not None
        assert interview_sheet.areas_to_explore is not None

        # Verify questions list composed from interview_questions
        assert interview_sheet.questions is not None
        assert isinstance(interview_sheet.questions, list)
        assert len(interview_sheet.questions) == 5

        # Verify each question has required fields
        for question in interview_sheet.questions:
            assert question.question_text is not None
            assert len(question.question_text) > 0
            assert question.purpose is not None
            assert len(question.purpose) > 0
