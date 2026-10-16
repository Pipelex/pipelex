"""Local arm of the local / Temporal problem parity pair for judgment.

Runs the ``native_judge`` pipe through the local (non-Temporal) ``PipeRouter`` with the judgment call
mocked to fail, and asserts the resulting problem carries the full classification —
its code, domain, verdict and step, and the model and the provider in the operator's diagnostics.

This is the baseline a distributed arm must match, asserting the same ``JudgeProblemParityTestData``
constants so local / distributed parity holds by construction. The judgment operator does not wrap the
leaf error (unlike PipeLLM), so the ``PipeRouter`` locates the raw ``JudgmentJobFailureError`` (a
``CogtError``) itself, and the problem's diagnostics carry its identity.
"""

from collections.abc import Generator

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.cogt.exceptions import JudgmentJobFailureError, find_inference_error_category_in_chain
from pipelex.errors.problem import ProblemView
from pipelex.interpreter_hub import get_pipe_router
from pipelex.pipe_run.exceptions import PipeRouterError
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.error_handling.test_data import JudgeProblemParityTestData
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle


@pytest.mark.asyncio(loop_scope="class")
class TestJudgeProblemLocalFullChain:
    """A failing judgment pipe run locally yields a fully classified problem."""

    @pytest.fixture
    def failing_judge_pipe_job_local(self) -> Generator[PipeJob, None, None]:
        """A PipeJob for the judgment pipe, in LIVE mode so the judgment call actually fires."""
        yield from pipe_job_from_bundle(
            bundle_file=JudgeProblemParityTestData.BUNDLE_FILE,
            pipe_code=JudgeProblemParityTestData.PIPE_CODE,
            pipe_run_mode=PipeRunMode.LIVE,
        )

    async def test_problem_from_local_execution(
        self,
        mocker: MockerFixture,
        failing_judge_pipe_job_local: PipeJob,
    ) -> None:
        """Local execution surfaces the worker failure, located, with the ``JudgmentJobFailureError``'s classification."""
        mocker.patch.object(
            ContentGenerator,
            "make_judgment_answers",
            side_effect=JudgeProblemParityTestData.make_failing_judgment_error(),
        )

        with pytest.raises(PipeRouterError) as exc_info:
            await get_pipe_router().run(pipe_job=failing_judge_pipe_job_local)
        assert isinstance(exc_info.value.__cause__, JudgmentJobFailureError)

        # The classification the problem carries — the parity target.
        error = exc_info.value
        problem = error.to_problem(view=ProblemView.OPERATOR)
        assert problem.code == JudgeProblemParityTestData.EXPECTED_CODE
        assert problem.domain == JudgeProblemParityTestData.EXPECTED_DOMAIN
        assert problem.is_retryable is JudgeProblemParityTestData.EXPECTED_RETRYABLE
        assert problem.next_step.kind == JudgeProblemParityTestData.EXPECTED_OPERATOR_STEP_KIND
        assert problem.diagnostics is not None
        assert problem.diagnostics.error_class == "JudgmentJobFailureError"
        assert problem.diagnostics.model == JudgeProblemParityTestData.FAILURE_MODEL
        assert problem.diagnostics.provider is not None
        assert problem.diagnostics.provider.name == JudgeProblemParityTestData.FAILURE_PROVIDER
        assert find_inference_error_category_in_chain(error) == JudgeProblemParityTestData.FAILURE_CATEGORY
        # The advice stays the local CLI's tip: the caller's view carries the code's step, never the advice.
        advice = error.advised_action()
        assert advice is not None
        assert advice.kind == JudgeProblemParityTestData.FAILURE_USER_ACTION_KIND
        assert JudgeProblemParityTestData.FAILURE_USER_ACTION_DETAIL not in str(error.to_problem(view=ProblemView.CALLER).to_wire())
