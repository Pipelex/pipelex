"""Local arm of the local / Temporal ``ErrorReport`` parity pair for judgment.

Runs the ``native_judge`` pipe through the local (non-Temporal) ``PipeRouter`` with the judgment call
mocked to fail, and asserts the resulting ``ErrorReport`` carries the full classification —
``error_category`` / ``retryable`` / ``model`` / ``provider`` / ``user_action``.

This is the baseline a distributed arm must match, asserting the same ``JudgeErrorReportParityTestData``
constants so local / distributed parity holds by construction. The judgment operator does not wrap the
leaf error (unlike PipeLLM), so the ``PipeRouter`` locates the raw ``JudgmentJobFailureError`` (a
``CogtError``) itself, and the report carries its identity.
"""

from collections.abc import Generator

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.cogt.exceptions import JudgmentJobFailureError
from pipelex.interpreter_hub import get_pipe_router
from pipelex.pipe_run.exceptions import PipeRouterError
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.error_handling.test_data import JudgeErrorReportParityTestData
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle


@pytest.mark.asyncio(loop_scope="class")
class TestJudgeErrorReportLocalFullChain:
    """A failing judgment pipe run locally yields a fully classified ``ErrorReport``."""

    @pytest.fixture
    def failing_judge_pipe_job_local(self) -> Generator[PipeJob, None, None]:
        """A PipeJob for the judgment pipe, in LIVE mode so the judgment call actually fires."""
        yield from pipe_job_from_bundle(
            bundle_file=JudgeErrorReportParityTestData.BUNDLE_FILE,
            pipe_code=JudgeErrorReportParityTestData.PIPE_CODE,
            pipe_run_mode=PipeRunMode.LIVE,
        )

    async def test_error_report_from_local_execution(
        self,
        mocker: MockerFixture,
        failing_judge_pipe_job_local: PipeJob,
    ) -> None:
        """Local execution surfaces the worker failure, located, with the ``JudgmentJobFailureError``'s classification."""
        mocker.patch.object(
            ContentGenerator,
            "make_judgment_answers",
            side_effect=JudgeErrorReportParityTestData.make_failing_judgment_error(),
        )

        with pytest.raises(PipeRouterError) as exc_info:
            await get_pipe_router().run(pipe_job=failing_judge_pipe_job_local)
        assert isinstance(exc_info.value.__cause__, JudgmentJobFailureError)

        # The classification fields — the parity target.
        report = exc_info.value.to_error_report()
        assert report.error_type == "JudgmentJobFailureError"
        assert report.error_category == JudgeErrorReportParityTestData.FAILURE_CATEGORY
        assert report.retryable == JudgeErrorReportParityTestData.EXPECTED_RETRYABLE
        assert report.model == JudgeErrorReportParityTestData.FAILURE_MODEL
        assert report.provider == JudgeErrorReportParityTestData.FAILURE_PROVIDER
        assert report.user_action is not None
        assert report.user_action.kind == JudgeErrorReportParityTestData.EXPECTED_USER_ACTION_KIND
