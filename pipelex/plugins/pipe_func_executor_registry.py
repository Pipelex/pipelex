from collections.abc import Callable
from typing import TYPE_CHECKING, TypeAlias

from pipelex.plugins.exceptions import UnknownPipeFuncExecutionModeError
from pipelex.system.configuration.pipe_func_config import PipeFuncConfig

if TYPE_CHECKING:
    # Deferred on purpose: the protocol lives under ``pipe_operators`` (the method-interpretation
    # layer) but this registry is imported from ``pipelex.config``, which the inference layer loads.
    # A module-level import here would drag the interpreter into every closure that touches
    # inference — the exact coupling the runtime_hub / interpreter_hub split removes. The underlying
    # placement inversion (a ``plugins`` module typed by a ``pipe_operators`` protocol) is recorded
    # in docs/contribute/hub-layering.md as a known inversion.
    from pipelex.pipe_operators.func.pipe_func_executor_protocol import PipeFuncExecutorProtocol

# The one in-process execution mode core always owns. Every other mode is a remote/sandbox backend
# contributed by a plugin (e.g. an out-of-tree ``daytona`` backend) and, by the seam's invariant,
# transports the customer's source to run it out-of-process rather than importing it here.
DIRECT_PIPE_FUNC_EXECUTION_MODE = "direct"

# A plugin's factory for one PipeFunc execution mode: the pipe_func config in, an executor out. The
# whole ``PipeFuncConfig`` (not a pre-resolved value) is passed so a factory can read whatever it
# needs at the boot apply-point, never at registration — mirrors ``StorageProviderFactoryFn``.
PipeFuncExecutorFactoryFn: TypeAlias = Callable[[PipeFuncConfig], "PipeFuncExecutorProtocol"]


class PipeFuncExecutorRegistry:
    """Read view over the PipeFunc-executor factories contributed by discovered plugins.

    Keyed by the open ``execution_mode`` token (a ``str``; core owns ``direct``, an external plugin
    registers e.g. ``"daytona"``). Built once
    at boot from the registrar's accumulated ``pipe_func_executors`` and stored on the hub; core reads
    ``pipe_func_config.execution_mode`` and calls the looked-up factory to produce the one executor set
    on the hub. This is the config-selected-singleton sibling of ``StorageProviderRegistry`` — the
    PipeFunc execution axis, orthogonal to the orchestration axis (a ``temporal`` boot still resolves
    its executor mode through this registry on the worker side).
    """

    def __init__(self, pipe_func_executors: dict[str, PipeFuncExecutorFactoryFn]):
        self._pipe_func_executors: dict[str, PipeFuncExecutorFactoryFn] = dict(pipe_func_executors)

    def get_required(self, *, mode: str) -> PipeFuncExecutorFactoryFn:
        factory = self._pipe_func_executors.get(mode)
        if factory is None:
            raise UnknownPipeFuncExecutionModeError(mode=mode, registered_modes=self.modes)
        return factory

    def has(self, *, mode: str) -> bool:
        return mode in self._pipe_func_executors

    @property
    def modes(self) -> list[str]:
        return list(self._pipe_func_executors)
