from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.pipe_run_mode import PipeRunMode


class TestPipeRunParamsIsolation:
    """make_deep_copy() must give an independent pipe_stack — the concurrent controllers
    (PipeBatch, PipeParallel) rely on it so a branch's push/pop never corrupts a sibling's stack.
    """

    def test_make_deep_copy_isolates_pipe_stack(self) -> None:
        """A deep copy's pipe_stack is an independent list — a push on one branch does not leak into the other."""
        original = PipeRunParams(run_mode=PipeRunMode.LIVE, pipe_stack_limit=20, batch_max_concurrency=None, pipe_stack=["root"])

        branch = original.make_deep_copy()
        assert branch.pipe_stack is not original.pipe_stack, "a deep copy must not share the pipe_stack list object"

        branch.push_pipe_to_stack("branch_pipe")
        assert branch.pipe_stack == ["root", "branch_pipe"]
        assert original.pipe_stack == ["root"], "the branch's push must not leak into the original's stack"
