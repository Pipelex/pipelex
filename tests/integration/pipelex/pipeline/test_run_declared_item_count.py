from typing import Any

import pytest
from mthds.protocol.pipeline_inputs import PipelineInputs
from pytest_mock import MockerFixture

from pipelex.core.stuffs.text_content import TextContent
from pipelex.errors.problem import ProblemView
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.pipeline import pipeline_run_setup
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.exceptions import RunParameterError
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.libraries.test_data import DeclaredItemCountCases

_INPUTS: PipelineInputs = {"topic": {"concept": "Text", "content": "rivers"}}


def _declaring(count: int) -> str:
    """A bundle whose `make_ideas` pipe outputs `Text[count]`."""
    return DeclaredItemCountCases.SPELLINGS[1][1](count)


def _refusal_params(*, exc: ValidateBundleError) -> list[dict[str, Any]]:
    """The parameters set on every item the refusal carries under the declared-count code."""
    problem = exc.to_problem(view=ProblemView.OPERATOR)
    refusals = [item for item in problem.errors or [] if item.code == PipelexErrorCode.DEPLOYMENT_DECLARED_COUNT_OVER_LIMIT]
    return [item.params.model_dump(exclude_none=True) if item.params is not None else {} for item in refusals]


@pytest.mark.asyncio(loop_scope="class")
class TestRunDeclaredItemCount:
    async def test_a_run_holds_the_method_to_the_deployments_maximum(self) -> None:
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY)

        with pytest.raises(ValidateBundleError) as exc_info:
            await runner.execute(pipe_code="make_ideas", mthds_contents=[_declaring(1001)], inputs=_INPUTS)

        assert _refusal_params(exc=exc_info.value) == [{"slot": "the output of the pipe 'make_ideas'", "count": 1001, "limit": 1000}]

    async def test_the_runs_own_maximum_reaches_the_load_the_job_and_every_pipe_run(self, mocker: MockerFixture) -> None:
        """A maximum above the deployment's lets the method load, and its pipe run builds every mock item it declares.

        The dry run's mock builders sit outside the setup's scope, inside the pipe run, which reads the maximum from the
        job's `RunMetadata`: the 1,500 mock items are built only because the job carried the run's maximum there.
        """
        prepare_spy = mocker.spy(pipeline_run_setup, "prepare_pipe_job")
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, max_declared_item_count=2000)

        response = await runner.execute(pipe_code="make_ideas", mthds_contents=[_declaring(1500)], inputs=_INPUTS)

        assert len(response.pipe_output.main_stuff.as_list_of_fixed_content_type(TextContent).items) == 1500
        assert prepare_spy.call_args.kwargs["max_declared_item_count"] == 2000
        pipe_job = prepare_spy.spy_return
        assert pipe_job.job_metadata.run_metadata.max_declared_item_count == 2000

    async def test_a_lower_maximum_refuses_what_the_deployment_allows(self) -> None:
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, max_declared_item_count=4)

        with pytest.raises(ValidateBundleError) as exc_info:
            await runner.execute(pipe_code="make_ideas", mthds_contents=[_declaring(5)], inputs=_INPUTS)

        assert _refusal_params(exc=exc_info.value) == [{"slot": "the output of the pipe 'make_ideas'", "count": 5, "limit": 4}]

    async def test_a_maximum_no_runtime_may_set_is_refused_when_the_protocol_is_built(self) -> None:
        with pytest.raises(RunParameterError):
            PipelexMTHDSProtocol(max_declared_item_count=0)
