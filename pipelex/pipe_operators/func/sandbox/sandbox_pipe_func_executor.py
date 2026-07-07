from typing_extensions import override

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.pipe_operators.func.pipe_func_executor_protocol import PipeFuncExecutionResult, PipeFuncExecutorProtocol
from pipelex.pipe_operators.func.sandbox.local_subprocess_sandbox_client import LocalSubprocessSandboxClient
from pipelex.pipe_operators.func.sandbox.sandbox_bridge import build_sandbox_request, execution_result_from_sandbox
from pipelex.pipe_operators.func.sandbox.sandbox_transport import SandboxClientProtocol
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata


class SandboxPipeFuncExecutor(PipeFuncExecutorProtocol):
    """PipeFuncExecutor that runs the customer function in a sandbox instead of this process.

    It carries no customer code: it packages the crate (which holds ``python_sources``) plus the
    transported working memory into a SandboxRunRequest, hands it to a SandboxClient, and rebinds
    the transported output against THIS process's registry. It never imports or executes the
    function — that only happens inside the sandbox.

    The default client is a local subprocess (for local end-to-end runs and tests); production
    injects a Daytona-backed client behind the same protocol.
    """

    def __init__(self, *, sandbox_client: SandboxClientProtocol | None = None) -> None:
        self._sandbox_client: SandboxClientProtocol = sandbox_client or LocalSubprocessSandboxClient()

    @override
    async def run_pipe_func(
        self,
        *,
        job_metadata: JobMetadata,
        pipe_code: str,
        function_name: str,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
    ) -> PipeFuncExecutionResult:
        request = build_sandbox_request(
            job_metadata=job_metadata,
            pipe_code=pipe_code,
            function_name=function_name,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
        )
        result = await self._sandbox_client.run(request=request)
        return execution_result_from_sandbox(result)
