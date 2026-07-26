"""Local arm of the local / Temporal ``ErrorReport`` parity pair for web search.

Runs the ``native_search`` pipe through the local (non-Temporal) ``PipeRouter`` with the search call
mocked to fail, and asserts the resulting ``ErrorReport`` carries the full classification —
``error_category`` / ``retryable`` / ``model`` / ``provider`` / ``user_action``.

This is the baseline the Temporal full-chain test
(``tests/integration/pipelex/temporal/test_workflow_search_error_report_full_chain.py``) must match.
Both arms assert the same ``SearchErrorReportParityTestData`` constants, so local / Temporal parity holds
by construction. The search operator does not wrap the leaf error (unlike PipeLLM), so a raw
``SearchJobFailureError`` (a ``CogtError``) propagates and the ``PipeRouter`` re-raises it as-is.
"""

from collections.abc import Generator

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.cogt.exceptions import SearchJobFailureError
from pipelex.method_hub import get_pipe_router
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.error_handling.test_data import SearchErrorReportParityTestData
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle


@pytest.mark.asyncio(loop_scope="class")
class TestSearchErrorReportLocalFullChain:
    """A failing search pipe run locally yields a fully classified ``ErrorReport``."""

    @pytest.fixture
    def failing_search_pipe_job_local(self) -> Generator[PipeJob, None, None]:
        """A PipeJob for the search pipe, in LIVE mode so the search call actually fires."""
        yield from pipe_job_from_bundle(
            bundle_file=SearchErrorReportParityTestData.BUNDLE_FILE,
            pipe_code=SearchErrorReportParityTestData.PIPE_CODE,
            pipe_run_mode=PipeRunMode.LIVE,
        )

    async def test_error_report_from_local_execution(
        self,
        mocker: MockerFixture,
        failing_search_pipe_job_local: PipeJob,
    ) -> None:
        """Local execution surfaces the worker failure as a classified ``SearchJobFailureError``."""
        mocker.patch.object(
            ContentGenerator,
            "make_search_sourced_answer",
            side_effect=SearchErrorReportParityTestData.make_failing_search_error(),
        )

        with pytest.raises(SearchJobFailureError) as exc_info:
            await get_pipe_router().run(pipe_job=failing_search_pipe_job_local)

        # The classification fields — the parity target.
        report = exc_info.value.to_error_report()
        assert report.error_category == SearchErrorReportParityTestData.FAILURE_CATEGORY
        assert report.retryable == SearchErrorReportParityTestData.EXPECTED_RETRYABLE
        assert report.model == SearchErrorReportParityTestData.FAILURE_MODEL
        assert report.provider == SearchErrorReportParityTestData.FAILURE_PROVIDER
        assert report.user_action is not None
        assert report.user_action.kind == SearchErrorReportParityTestData.EXPECTED_USER_ACTION_KIND
