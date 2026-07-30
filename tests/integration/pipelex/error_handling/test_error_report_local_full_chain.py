"""Local arm of the local / Temporal ``ErrorReport`` parity pair.

Runs the ``native_text_sequence`` pipe through the local (non-Temporal)
``PipeRouter`` with the LLM call mocked to fail, and asserts the resulting
``ErrorReport`` carries the full classification — ``error_category`` /
``retryable`` / ``model`` / ``provider`` / ``user_action``.

This is the baseline the Temporal full-chain test
(``tests/integration/pipelex/temporal/test_workflow_error_report_full_chain.py``)
must match. Both arms assert the same ``ErrorReportParityTestData`` constants, so
local / Temporal parity holds by construction. They live in separate modules on
purpose: the Temporal arm needs ``temporal.is_enabled = True`` and the temporal
``boot_temporal`` fixture, this one must stay on default config — separate
modules avoid any in-test config swapping.
"""

from collections.abc import Generator

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.interpreter_hub import get_pipe_router
from pipelex.pipe_run.exceptions import PipeRouterError
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.error_handling.test_data import ErrorReportParityTestData
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle


@pytest.mark.asyncio(loop_scope="class")
class TestErrorReportLocalFullChain:
    """A failing pipe run locally yields a fully classified ``ErrorReport``."""

    @pytest.fixture
    def failing_pipe_job_local(self) -> Generator[PipeJob, None, None]:
        """A PipeJob for the failing pipe, in LIVE mode so the LLM call actually fires."""
        yield from pipe_job_from_bundle(
            bundle_file=ErrorReportParityTestData.BUNDLE_FILE,
            pipe_code=ErrorReportParityTestData.PIPE_CODE,
            pipe_run_mode=PipeRunMode.LIVE,
        )

    async def test_error_report_from_local_execution(
        self,
        mocker: MockerFixture,
        failing_pipe_job_local: PipeJob,
    ) -> None:
        """Local execution surfaces the worker failure as a classified ``PipeRouterError``."""
        mocker.patch.object(
            ContentGenerator,
            "make_llm_text",
            side_effect=ErrorReportParityTestData.make_failing_llm_error(),
        )

        with pytest.raises(PipeRouterError) as exc_info:
            await get_pipe_router().run(pipe_job=failing_pipe_job_local)

        # The classification fields — the parity target. error_type / message
        # legitimately differ from the Temporal arm (PipeRouterError vs
        # WorkflowExecutionError; PipeLLM wraps the leaf message), so they are
        # not asserted here.
        report = exc_info.value.to_error_report()
        assert report.error_category == ErrorReportParityTestData.FAILURE_CATEGORY
        assert report.retryable == ErrorReportParityTestData.EXPECTED_RETRYABLE
        assert report.model == ErrorReportParityTestData.FAILURE_MODEL
        assert report.provider == ErrorReportParityTestData.FAILURE_PROVIDER
        assert report.user_action is not None
        assert report.user_action.kind == ErrorReportParityTestData.EXPECTED_USER_ACTION_KIND
