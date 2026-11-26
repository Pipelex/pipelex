"""Local arm of the local / Temporal problem parity pair.

Runs the ``native_text_sequence`` pipe through the local (non-Temporal)
``PipeRouter`` with the LLM call mocked to fail, and asserts the resulting
problem carries the full classification — its code, domain,
verdict and step, and the model and the provider in the operator's diagnostics.

This is the baseline the Temporal full-chain test
(``tests/integration/pipelex/temporal/test_workflow_problem_full_chain.py``)
must match. Both arms assert the same ``ProblemParityCases`` constants, so
local / Temporal parity holds by construction. They live in separate modules on
purpose: the Temporal arm needs ``temporal.is_enabled = True`` and the temporal
``boot_temporal`` fixture, this one must stay on default config — separate
modules avoid any in-test config swapping.
"""

from collections.abc import Generator

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.cogt.exceptions import find_inference_error_category_in_chain
from pipelex.errors.problem import ProblemView
from pipelex.interpreter_hub import get_pipe_router
from pipelex.pipe_run.exceptions import PipeRouterError
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.error_handling.cases import ProblemParityCases
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle


@pytest.mark.asyncio(loop_scope="class")
class TestProblemLocalFullChain:
    """A failing pipe run locally yields a fully classified problem."""

    @pytest.fixture
    def failing_pipe_job_local(self) -> Generator[PipeJob, None, None]:
        """A PipeJob for the failing pipe, in LIVE mode so the LLM call actually fires."""
        yield from pipe_job_from_bundle(
            bundle_file=ProblemParityCases.BUNDLE_FILE,
            pipe_code=ProblemParityCases.PIPE_CODE,
            pipe_run_mode=PipeRunMode.LIVE,
        )

    async def test_problem_from_local_execution(
        self,
        mocker: MockerFixture,
        failing_pipe_job_local: PipeJob,
    ) -> None:
        """Local execution surfaces the worker failure as a classified ``PipeRouterError``."""
        mocker.patch.object(
            ContentGenerator,
            "make_llm_text",
            side_effect=ProblemParityCases.make_failing_llm_error(),
        )

        with pytest.raises(PipeRouterError) as exc_info:
            await get_pipe_router().run(pipe_job=failing_pipe_job_local)

        # The classification the problem carries — the parity target.
        error = exc_info.value
        problem = error.to_problem(view=ProblemView.OPERATOR)
        assert problem.code == ProblemParityCases.EXPECTED_CODE
        assert problem.domain == ProblemParityCases.EXPECTED_DOMAIN
        assert problem.is_retryable is ProblemParityCases.EXPECTED_RETRYABLE
        assert problem.next_step.kind == ProblemParityCases.EXPECTED_OPERATOR_STEP_KIND
        assert problem.diagnostics is not None
        assert problem.diagnostics.model == ProblemParityCases.FAILURE_MODEL
        assert problem.diagnostics.provider is not None
        assert problem.diagnostics.provider.name == ProblemParityCases.FAILURE_PROVIDER
        assert find_inference_error_category_in_chain(error) == ProblemParityCases.FAILURE_CATEGORY
        # The advice stays the local CLI's tip: the caller's view carries the code's step, never the advice.
        advice = error.advised_action()
        assert advice is not None
        assert advice.kind == ProblemParityCases.FAILURE_USER_ACTION_KIND
        assert ProblemParityCases.FAILURE_USER_ACTION_DETAIL not in str(error.to_problem(view=ProblemView.CALLER).to_wire())
