from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from mthds.protocol.problem.registry import CoreCode, StepKind
from typing_extensions import override

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.config import get_config
from pipelex.errors.error_codes import error_code_spec
from pipelex.errors.problem import PipelexProblem, ProblemView
from pipelex.pipe_run.exceptions import PipeRouterError, find_failure_location
from pipelex.pipe_run.pipe_router import PipeRouter
from pipelex.pipe_run.pipe_run import PipeRun
from pipelex.pipe_run.pipe_run_protocol import PipeRunProtocol
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.runtime_bridge.direct_orchestrator import DirectOrchestrator
from pipelex.runtime_bridge.exceptions import PipelexBridgeDispatchError
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.pipeline.test_data import LocatedRunFailureTestData

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
    from pipelex.pipe_run.pipe_job import PipeJob
    from pipelex.system.configuration.configs import PipelineExecutionConfig


def _dry_mock_config() -> PipelineExecutionConfig:
    return get_config().interpreter.pipeline_execution.with_execution_overrides(
        generate_graph=False,
        mock_inputs=True,
    )


class _DirectOrchestratorPipeRun(PipeRunProtocol):
    """Dispatch through the in-process orchestrator, as the API runner's `/execute` does in `direct` mode."""

    @override
    async def run(self, pipe_job: PipeJob, *, delivery_assignment: DeliveryAssignment | None = None) -> PipeOutput:
        await DirectOrchestrator().execute(pipe_job=pipe_job, delivery_assignment=delivery_assignment)
        msg = "This adapter only serves failing runs."
        raise AssertionError(msg)


class _RecoveredProblemError(PipelexError):
    """Carries a problem recovered across a transport boundary, as a distributed submitter does."""

    def __init__(self, message: str, *, recovered_problem: PipelexProblem):
        super().__init__(message)
        self.carried_problem = recovered_problem

    @override
    def recovered_problem(self) -> PipelexProblem | None:
        return self.carried_problem


class _RecoveredProblemPipeRun(PipeRunProtocol):
    """Fail the way a distributed orchestrator does: its bridge sentence around a recovered problem."""

    def __init__(self, *, recovered_problem: PipelexProblem):
        self._recovered_problem = recovered_problem

    @override
    async def run(self, pipe_job: PipeJob, *, delivery_assignment: DeliveryAssignment | None = None) -> PipeOutput:
        recovered_message = self._recovered_problem.diagnostics.message if self._recovered_problem.diagnostics else self._recovered_problem.detail
        recovered = _RecoveredProblemError(recovered_message, recovered_problem=self._recovered_problem)
        msg = f"Pipe execution failed in temporal blocking delivery for pipe '{pipe_job.pipe.code}': {recovered}"
        raise PipelexBridgeDispatchError(msg) from recovered


class _ForeignFailureRouter(PipeRouter):
    """A router whose pipe raises an exception that is not a PipelexError."""

    @override
    async def _run_pipe_job(self, pipe_job: PipeJob) -> PipeOutput:
        msg = "boom from a pipe"
        raise KeyError(msg)


@pytest.mark.asyncio(loop_scope="class")
class TestLocatedRunFailure:
    async def _run_parallel_failure(self, *, pipe_run: PipeRunProtocol | None = None) -> PipelineExecutionError:
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, execution_config=_dry_mock_config(), pipe_run=pipe_run)
        with pytest.raises(PipelineExecutionError) as exc_info:
            await runner.execute(pipe_code="flow", mthds_contents=[LocatedRunFailureTestData.PARALLEL_MTHDS])
        return exc_info.value

    async def test_unserved_model_is_reported_at_the_failing_step(self) -> None:
        """The model example: the failing step, its path and the model error's own identity, code and sentence."""
        runner = PipelexMTHDSProtocol()
        with pytest.raises(PipelineExecutionError) as exc_info:
            await runner.execute(pipe_code="two_steps", mthds_contents=[LocatedRunFailureTestData.MODEL_MTHDS], inputs={"topic": "cats"})
        error = exc_info.value

        assert error.pipe_code == "summarize"
        assert error.pipe_stack == ["two_steps", "summarize"]

        unserved_handle = LocatedRunFailureTestData.UNSERVED_MODEL_HANDLE
        caller = error.to_problem(view=ProblemView.CALLER)
        assert caller.code == CoreCode.MODEL_UNKNOWN
        assert caller.title == error_code_spec(CoreCode.MODEL_UNKNOWN).title
        assert caller.type == error_code_spec(CoreCode.MODEL_UNKNOWN).type_uri
        assert caller.location is not None
        assert (caller.location.pipe, caller.location.path) == ("summarize", ["two_steps", "summarize"])
        assert caller.detail == f"The method names the llm model '{unserved_handle}', which no catalog knows."
        assert caller.diagnostics is None

        operator = error.to_problem(view=ProblemView.OPERATOR)
        assert operator.diagnostics is not None
        assert operator.diagnostics.error_class == "ModelNotFoundError"
        assert operator.diagnostics.message == f"Model handle '{unserved_handle}' was not found in the model deck."
        assert operator.diagnostics.model == unserved_handle
        assert error.message == f"Pipe 'summarize' failed (two_steps → summarize): Model handle '{unserved_handle}' was not found in the model deck."
        # The local-deck remedy is the local CLI's to give: neither reader's text names it.
        for text in (error.message, str(caller.to_wire()), str(operator.to_wire())):
            assert ".pipelex/inference" not in text
            assert "pipelex init" not in text
        # The model lookup advises changing the model the step names, a local tip that rides no problem.
        assert error.advised_action() == UserAction(
            kind=UserActionKind.CHANGE_MODEL,
            detail=f"Change the model '{unserved_handle}' to an LLM the model deck serves.",
        )

    async def test_parallel_combine_failure_is_reported_at_the_nested_parallel(self) -> None:
        """The multiplicity example: the parallel nested in the sequence, with the combine's own identity and message."""
        error = await self._run_parallel_failure()

        assert error.pipe_code == "analyze"
        assert error.pipe_stack == ["flow", "analyze"]

        # The combine's refusal restated with its multiplicity remedy, a StuffFactoryError raised from the
        # combine's own, is the root fault: of two faults of the same class, the outer one.
        operator = error.to_problem(view=ProblemView.OPERATOR)
        assert operator.diagnostics is not None
        assert operator.diagnostics.error_class == "StuffFactoryError"
        assert operator.diagnostics.message.startswith("PipeParallel 'analyze' cannot combine its branch results into its output 'Report'.")
        assert error.message.startswith(
            "Pipe 'analyze' failed (flow → analyze): PipeParallel 'analyze' cannot combine its branch results into its output 'Report'."
        )
        assert "Branch 'gen_ideas' gives result 'ideas' as a list, 'Idea[]', but field 'ideas' of 'Report' holds a single item." in error.message
        caller = error.to_problem(view=ProblemView.CALLER)
        assert caller.code == CoreCode.PIPE_OUTPUT_MULTIPLICITY
        assert caller.detail == ("Pipe 'analyze' produced an output of the multiplicity 'list', but its output 'ideas' is declared 'single'.")
        # A mismatched combine is the caller's to fix: the caller's step is the code's, the branch to change the operator's message.
        assert caller.next_step.kind == StepKind.CHANGE_METHOD
        assert "Branch 'gen_ideas'" not in str(caller.to_wire())

    async def test_every_branch_whose_multiplicity_differs_is_an_item(self) -> None:
        """Two branches give a list to a single field: the problem names the first, and one item names each."""
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, execution_config=_dry_mock_config())
        with pytest.raises(PipelineExecutionError) as exc_info:
            await runner.execute(pipe_code="flow", mthds_contents=[LocatedRunFailureTestData.PARALLEL_TWO_MULTIPLICITIES_MTHDS])

        caller = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert caller.code == CoreCode.PIPE_OUTPUT_MULTIPLICITY
        assert caller.detail == "Pipe 'analyze' produced an output of the multiplicity 'list', but its output 'ideas' is declared 'single'."
        assert caller.errors is not None
        assert [(item.code, item.detail) for item in caller.errors] == [
            (
                CoreCode.PIPE_OUTPUT_MULTIPLICITY,
                "Pipe 'analyze' produced an output of the multiplicity 'list', but its output 'ideas' is declared 'single'.",
            ),
            (
                CoreCode.PIPE_OUTPUT_MULTIPLICITY,
                "Pipe 'analyze' produced an output of the multiplicity 'list', but its output 'summary' is declared 'single'.",
            ),
        ]

    async def test_a_method_fault_at_the_root_reads_its_code_s_sentence_located(self) -> None:
        """A root fault of the caller's own method reads its code's sentence, located at the failing pipe."""
        runner = PipelexMTHDSProtocol()
        with pytest.raises(PipelineExecutionError) as exc_info:
            await runner.execute(pipe_code="force_flow", mthds_contents=[LocatedRunFailureTestData.FORCE_MTHDS], inputs={})
        error = exc_info.value

        assert error.pipe_code == "force_echo"
        assert error.pipe_stack == ["force_flow", "force_echo"]
        assert error.message.startswith("Pipe 'force_echo' failed (force_flow → force_echo): ")
        assert "clause" in error.message

        caller = error.to_problem(view=ProblemView.CALLER)
        assert caller.code == CoreCode.PIPE_FORCED_INPUT_ABSENT
        assert caller.detail == "Pipe 'force_echo' forces 'clause' with '!', and it was absent in this run."
        assert caller.location is not None
        assert (caller.location.pipe, caller.location.path) == ("force_echo", ["force_flow", "force_echo"])
        operator = error.to_problem(view=ProblemView.OPERATOR)
        assert operator.diagnostics is not None
        assert operator.diagnostics.error_class == "OptionalValueAbsentError"

    async def test_in_process_orchestrator_adds_nothing(self) -> None:
        """Through the in-process bridge, the problem and the location are the direct run's; the bridge's sentence is in neither."""
        direct_error = await self._run_parallel_failure()
        bridged_error = await self._run_parallel_failure(pipe_run=_DirectOrchestratorPipeRun())

        assert isinstance(bridged_error.__cause__, PipelexBridgeDispatchError)
        assert bridged_error.pipe_code == direct_error.pipe_code
        assert bridged_error.pipe_stack == direct_error.pipe_stack
        assert bridged_error.message == direct_error.message
        for view in (ProblemView.CALLER, ProblemView.OPERATOR):
            assert bridged_error.to_problem(view=view) == direct_error.to_problem(view=view)
        assert "DIRECT mode" not in str(bridged_error.to_problem(view=ProblemView.OPERATOR).to_wire())

    async def test_recovered_problem_adds_nothing(self) -> None:
        """A problem recovered across a transport boundary, as the hosted run stores it, reads as the direct run's."""
        direct_error = await self._run_parallel_failure()
        location = find_failure_location(error=direct_error)
        assert isinstance(location, PipeRouterError)
        # What a distributed worker's run root stores: the located router error's problem, in the operator's view.
        recovered_problem = location.to_problem(view=ProblemView.OPERATOR)

        bridged_error = await self._run_parallel_failure(pipe_run=_RecoveredProblemPipeRun(recovered_problem=recovered_problem))

        for view in (ProblemView.CALLER, ProblemView.OPERATOR):
            assert bridged_error.to_problem(view=view) == direct_error.to_problem(view=view)
        assert "temporal blocking delivery" not in str(bridged_error.to_problem(view=ProblemView.OPERATOR).to_wire())
        assert "temporal blocking delivery" not in bridged_error.message

    async def test_foreign_exception_is_located_as_unexpected_error(self) -> None:
        """A non-PipelexError raised in a pipe's run comes out located, as a PipelexUnexpectedError naming its class."""
        error = await self._run_parallel_failure(pipe_run=PipeRun(pipe_router=_ForeignFailureRouter()))

        assert error.pipe_code == "flow"
        assert error.pipe_stack == ["flow"]
        # Named by its class alone: a foreign exception's text can carry a key of the run's data.
        assert error.message == "Pipe 'flow' failed: KeyError"
        operator = error.to_problem(view=ProblemView.OPERATOR)
        assert operator.code == CoreCode.RUNTIME_UNEXPECTED
        assert operator.diagnostics is not None
        assert operator.diagnostics.error_class == "PipelexUnexpectedError"
        assert operator.diagnostics.message == "KeyError"
        assert "boom from a pipe" not in str(operator.to_wire())
        caller = error.to_problem(view=ProblemView.CALLER)
        assert caller.code == CoreCode.RUNTIME_UNEXPECTED
        assert "boom from a pipe" not in str(caller.to_wire())
        assert "KeyError" not in str(caller.to_wire())
