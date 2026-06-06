"""Unit tests for the ``is_mock_inference`` branch in the LLM leaf (llm_generate).

The leaf is the single point where direct execution and the Temporal activities converge, so branching
there covers both modes. These tests pin that the branch is keyed strictly on
``job_metadata.is_mock_inference``: when set, the worker is never touched and the mock helper answers;
when unset, the real worker path runs.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.assignment_models import LLMAssignment
from pipelex.cogt.content_generation.llm_generate import llm_gen_text
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.pipeline.job_metadata import JobMetadata


class TestLlmGenerateMockBranch:
    def _assignment(self, *, is_mock_inference: bool) -> LLMAssignment:
        return LLMAssignment(
            job_metadata=JobMetadata(user_id="u", pipeline_run_id="run_branch", is_mock_inference=is_mock_inference),
            llm_setting=LLMSetting(model="gpt-4o", temperature=0.5),
            llm_prompt=LLMPrompt(),
        )

    @pytest.mark.asyncio
    async def test_mock_flag_routes_to_mock_and_skips_worker(self, mocker: MockerFixture) -> None:
        """is_mock_inference=True -> the mock helper answers and get_llm_worker is never called (no spend)."""
        worker_spy = mocker.patch("pipelex.cogt.content_generation.llm_generate.get_llm_worker")
        mocker.patch("pipelex.cogt.content_generation.dry_mock.get_report_delegate", return_value=mocker.MagicMock())

        result = await llm_gen_text(self._assignment(is_mock_inference=True))

        worker_spy.assert_not_called()
        assert result.startswith("MOCK INFERENCE")

    @pytest.mark.asyncio
    async def test_no_flag_uses_real_worker(self, mocker: MockerFixture) -> None:
        """is_mock_inference=False -> the real worker path runs (get_llm_worker is called)."""
        worker = mocker.MagicMock()
        worker.gen_text = mocker.AsyncMock(return_value="real generated text")
        worker_spy = mocker.patch("pipelex.cogt.content_generation.llm_generate.get_llm_worker", return_value=worker)
        report_spy = mocker.patch("pipelex.cogt.content_generation.dry_mock.get_report_delegate", return_value=mocker.MagicMock())

        result = await llm_gen_text(self._assignment(is_mock_inference=False))

        worker_spy.assert_called_once()
        assert result == "real generated text"
        report_spy.assert_not_called()  # the mock reporting path is not taken on a real run
