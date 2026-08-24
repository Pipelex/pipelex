from pipelex.pipe_operators.func.direct_pipe_func_executor import DirectPipeFuncExecutor
from pipelex.pipe_operators.func.pipe_func_executor_protocol import PipeFuncExecutorProtocol
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.pipe_func_executor_registry import DIRECT_PIPE_FUNC_EXECUTION_MODE
from pipelex.plugins.registrar import PluginRegistrar
from pipelex.system.configuration.pipe_func_config import PipeFuncConfig


def _make_direct_pipe_func_executor(config: PipeFuncConfig) -> PipeFuncExecutorProtocol:  # ruff: ignore[unused-function-argument] — stateless; the mode carries no config
    return DirectPipeFuncExecutor()


class PipeFuncPlugin:
    """Always-on built-in provider of the ``direct`` (in-process) PipeFunc execution mode.

    Core-unconditional: PipeFunc execution is required infra, so this plugin cannot be disabled into a
    boot with no executor (see ``INTERPRETER_CORE_UNCONDITIONAL_PLUGIN_NAMES``). It registers the one mode core
    owns — ``direct``, which imports and runs the customer function in this process. Running a PipeFunc
    in a sandbox instead is a commercial capability contributed out of tree by our Daytona
    plugin (mode ``daytona``); core never imports it.

    This is the PipeFunc-execution axis, orthogonal to the orchestration axis: it selects *how* a
    function body runs (here vs in a sandbox), independent of *where* the pipe runs (in-process vs on a
    Temporal worker). A ``temporal`` boot claims the ``PIPE_FUNC_EXECUTOR`` hub slot to wrap execution
    in an activity, and inside that activity resolves the real executor through this same registry.
    """

    name = "pipe_func"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_pipe_func_executor(mode=DIRECT_PIPE_FUNC_EXECUTION_MODE, factory=_make_direct_pipe_func_executor)
