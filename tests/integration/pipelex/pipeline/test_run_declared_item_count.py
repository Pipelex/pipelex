from typing import Any

import pytest
from mthds.protocol.pipeline_inputs import PipelineInputs
from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.core.pipes.exceptions import DeclaredItemCountLimitError
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
        mocker.patch.object(get_config().interpreter.method_limits, "max_declared_item_count_ceiling", 2000)
        prepare_spy = mocker.spy(pipeline_run_setup, "prepare_pipe_job")
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, max_declared_item_count=2000)

        response = await runner.execute(pipe_code="make_ideas", mthds_contents=[_declaring(1500)], inputs=_INPUTS)

        assert len(response.pipe_output.main_stuff.as_list_of_fixed_content_type(TextContent).items) == 1500
        assert prepare_spy.call_args.kwargs["max_declared_item_count"] == 2000
        pipe_job = prepare_spy.spy_return
        assert pipe_job.job_metadata.run_metadata.max_declared_item_count == 2000

    async def test_a_lower_maximum_lowers_nothing(self, mocker: MockerFixture) -> None:
        """A run's maximum only raises the deployment's: a lower one leaves the deployment's in force."""
        mocker.patch.object(get_config().interpreter.method_limits, "max_declared_item_count", 5)
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, max_declared_item_count=4)

        response = await runner.execute(pipe_code="make_ideas", mthds_contents=[_declaring(5)], inputs=_INPUTS)
        assert len(response.pipe_output.main_stuff.as_list_of_fixed_content_type(TextContent).items) == 5

        with pytest.raises(ValidateBundleError) as exc_info:
            await runner.execute(pipe_code="make_ideas", mthds_contents=[_declaring(6)], inputs=_INPUTS)

        assert _refusal_params(exc=exc_info.value) == [{"slot": "the output of the pipe 'make_ideas'", "count": 6, "limit": 5}]

    async def test_a_maximum_past_the_deployments_ceiling_is_refused_before_the_run_starts(self) -> None:
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, max_declared_item_count=1001)

        with pytest.raises(RunParameterError, match="max_declared_item_count_ceiling"):
            await runner.execute(pipe_code="make_ideas", mthds_contents=[_declaring(5)], inputs=_INPUTS)

    @pytest.mark.parametrize(
        ("max_declared_item_count", "output_multiplicity", "limit"),
        [
            pytest.param(None, 1001, 1000, id="deployment-maximum"),
            pytest.param(4, 1001, 1000, id="lower-run-maximum"),
        ],
    )
    async def test_an_output_multiplicity_past_the_maximum_is_refused_before_the_run_starts(
        self, mocker: MockerFixture, max_declared_item_count: int | None, output_multiplicity: int, limit: int
    ) -> None:
        """A run's own `output_multiplicity` asks a model, or a dry run's builder, for that many items: it is held to the maximum."""
        acquire_spy = mocker.spy(pipeline_run_setup, "acquire_library_async")
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, max_declared_item_count=max_declared_item_count)

        with pytest.raises(DeclaredItemCountLimitError) as exc_info:
            await runner.execute(pipe_code="make_ideas", mthds_contents=[_declaring(2)], inputs=_INPUTS, output_multiplicity=output_multiplicity)

        assert exc_info.value.problem_params() == {
            "slot": "the run's output, with `output_multiplicity`",
            "count": output_multiplicity,
            "limit": limit,
        }
        assert str(exc_info.value).startswith(f"The run asks for {output_multiplicity} items")
        acquire_spy.assert_not_called()

    async def test_an_output_multiplicity_within_the_maximum_runs(self) -> None:
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, max_declared_item_count=4)

        response = await runner.execute(pipe_code="make_ideas", mthds_contents=[_declaring(2)], inputs=_INPUTS, output_multiplicity=4)

        assert len(response.pipe_output.main_stuff.as_list_of_fixed_content_type(TextContent).items) == 4

    async def test_a_maximum_no_runtime_may_set_is_refused_when_the_protocol_is_built(self) -> None:
        with pytest.raises(RunParameterError):
            PipelexMTHDSProtocol(max_declared_item_count=0)
