from pipelex.pipe_operators.func.in_process_pipe_func_executor import InProcessPipeFuncExecutor
from pipelex.pipe_operators.func.pipe_func_executor_protocol import PipeFuncExecutorProtocol
from pipelex.pipe_operators.func.sandbox.local_subprocess_sandbox_client import LocalSubprocessSandboxClient
from pipelex.pipe_operators.func.sandbox.sandbox_pipe_func_executor import SandboxPipeFuncExecutor
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.pipe_func_executor_registry import DIRECT_PIPE_FUNC_EXECUTION_MODE
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.system.configuration.pipe_func_config import PipeFuncConfig

# The in-tree reference sandbox mode: runs the customer function out-of-process in a local
# subprocess behind the same ``SandboxClientProtocol`` a remote backend (``daytona``) uses. It makes
# the whole source-transport path real and testable without any closed plugin, and is the template a
# remote sandbox backend follows — it only swaps the client behind the protocol.
LOCAL_SANDBOX_PIPE_FUNC_EXECUTION_MODE = "local_sandbox"


def _make_direct_pipe_func_executor(config: PipeFuncConfig) -> PipeFuncExecutorProtocol:  # noqa: ARG001 — stateless; the mode carries no config
    return InProcessPipeFuncExecutor()


def _make_local_sandbox_pipe_func_executor(config: PipeFuncConfig) -> PipeFuncExecutorProtocol:  # noqa: ARG001 — default local client
    return SandboxPipeFuncExecutor(sandbox_client=LocalSubprocessSandboxClient())


class PipeFuncPlugin:
    """Always-on built-in provider of the ``direct`` and ``local_sandbox`` PipeFunc execution modes.

    Core-unconditional: PipeFunc execution is required infra, so this plugin cannot be disabled into a
    boot with no executor (see ``CORE_UNCONDITIONAL_PLUGIN_NAMES``). It registers one factory per
    built-in mode; ``pipe_func_config.execution_mode`` selects which one boot invokes. Importing this
    module is import-light — the in-process and subprocess executors pull no backend SDK. A remote
    backend (``pipelex-daytona-sandbox``) contributes its own ``daytona`` mode the same way, out of
    tree, so core never imports it.

    This is the PipeFunc-execution axis, orthogonal to the orchestration axis: it selects *how* a
    function body runs (here vs in a sandbox), independent of *where* the pipe runs (in-process vs on a
    Temporal worker). A ``temporal`` boot claims the ``PIPE_FUNC_EXECUTOR`` hub slot to wrap execution
    in an activity, and inside that activity resolves the real executor through this same registry.
    """

    name = "pipe_func"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_pipe_func_executor(mode=DIRECT_PIPE_FUNC_EXECUTION_MODE, factory=_make_direct_pipe_func_executor)
        registrar.add_pipe_func_executor(mode=LOCAL_SANDBOX_PIPE_FUNC_EXECUTION_MODE, factory=_make_local_sandbox_pipe_func_executor)
