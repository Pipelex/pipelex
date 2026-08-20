"""The PipeFunc operator hands its executor the QUALIFIED ref, never the bare code.

The transported path (Daytona sandbox, Temporal activity) resolves that value against the
transported library, which is keyed by ``pipe_ref`` — under the strict lookup a bare code resolves
to nothing there. The in-process ``DirectPipeFuncExecutor`` ignores the argument entirely, so no
end-to-end test in this repo reddens if the operator regresses to sending ``self.code``: this pin is
the only in-repo guard on the producer side of that contract.
"""

from collections.abc import Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.pipe_operators.func.pipe_func_executor_protocol import PipeFuncExecutionResult
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.registries.func_registry import func_registry


def transported_ref_probe_func(working_memory: WorkingMemory) -> TextContent:  # noqa: ARG001  # pyright: ignore[reportUnusedParameter]
    """Registered in the test so the PipeFunc validators accept the blueprint in local mode."""
    return TextContent(text="probe")


class TestPipeFuncTransportedRef:
    @pytest.mark.asyncio
    async def test_live_run_transports_the_qualified_ref(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ):
        load_empty_library()
        func_registry.register_function(transported_ref_probe_func, name="transported_ref_probe_func")
        blueprint = PipeFuncBlueprint(
            description="Producer-side pin: the executor must receive the qualified ref.",
            inputs={},
            output="native.Text",
            function_name="transported_ref_probe_func",
        )
        the_pipe_func = PipeFactory[PipeFunc].make_from_blueprint(
            domain_code="func_probe_domain",
            pipe_code="probe_pipe",
            blueprint=blueprint,
        )

        executor = mocker.Mock()
        executor.run_pipe_func = mocker.AsyncMock(return_value=PipeFuncExecutionResult(content=TextContent(text="probe")))
        mocker.patch("pipelex.pipe_operators.func.pipe_func.get_pipe_func_executor", return_value=executor)

        await the_pipe_func._live_run_operator_pipe(  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
            job_metadata=JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", user_id="user", pipeline_run_id="run")),
            working_memory=WorkingMemoryFactory.make_empty(),
            pipe_run_params=PipeRunParams(run_mode=PipeRunMode.LIVE, pipe_stack_limit=10, batch_max_concurrency=None),
        )

        # The discriminating assertion: `self.code` would send the bare 'probe_pipe'.
        assert executor.run_pipe_func.call_args.kwargs["pipe_code"] == "func_probe_domain.probe_pipe"
