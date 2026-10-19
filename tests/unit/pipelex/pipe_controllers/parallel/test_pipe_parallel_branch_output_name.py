import pytest
from mthds.protocol.problem.registry import CoreCode, MethodNameConflictConflict

from pipelex.core.pipes.exceptions import PipeRunError
from pipelex.errors.problem import ProblemView
from pipelex.pipe_controllers.parallel.pipe_parallel import branch_output_name
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.system.pipe_run_mode import PipeRunMode


class TestPipeParallelBranchOutputName:
    def test_a_branch_output_name_is_taken_once(self) -> None:
        seen: set[str] = set()
        assert (
            branch_output_name(
                pipe_code="fan_out", sub_pipe=SubPipe(pipe_code="draft", output_name="draft"), seen_output_names=seen, run_mode=PipeRunMode.DRY
            )
            == "draft"
        )

    def test_a_name_an_earlier_branch_took_is_a_name_conflict_naming_it(self) -> None:
        with pytest.raises(PipeRunError) as raised:
            branch_output_name(
                pipe_code="fan_out",
                sub_pipe=SubPipe(pipe_code="review", output_name="draft"),
                seen_output_names={"draft"},
                run_mode=PipeRunMode.DRY,
            )

        caller = raised.value.to_problem(view=ProblemView.CALLER)
        assert caller.code == CoreCode.METHOD_NAME_CONFLICT
        assert caller.params is not None
        assert caller.params.as_wire() == {"name": "draft", "conflict": MethodNameConflictConflict.DUPLICATE_DECLARATION}
