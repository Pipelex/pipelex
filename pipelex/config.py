from pipelex.plugins.pipe_func_executor_registry import DIRECT_PIPE_FUNC_EXECUTION_MODE
from pipelex.runtime_hub import get_optional_config, get_required_config
from pipelex.system.configuration.configs import PipelexConfig


def get_config() -> PipelexConfig:
    singleton_config = get_required_config()
    if not isinstance(singleton_config, PipelexConfig):
        msg = f"Expected {PipelexConfig}, but got {type(singleton_config)}"
        raise TypeError(msg)
    return singleton_config


def get_pipe_func_execution_mode() -> str:
    """The selected PipeFunc execution mode in this process (non-raising; defaults to ``direct``).

    Read from the optional config (``interpreter.pipe_func.execution_mode``) so it is safe to call
    from pydantic validators that may run before the global config is set (e.g. very early boot or
    isolated unit tests). When no config is set, or it is not a PipelexConfig, the answer is
    ``direct`` — the in-process mode, which keeps the default path byte-identical to the pre-seam
    behavior. Selecting a sandbox backend is a deployment CONFIG concern (the hosted runner and the
    worker set it in their ``.pipelex`` overrides), not an env var.
    """
    optional_config = get_optional_config()
    if not isinstance(optional_config, PipelexConfig):
        return DIRECT_PIPE_FUNC_EXECUTION_MODE
    return optional_config.interpreter.pipe_func.execution_mode


def is_pipe_func_sandbox_hosted() -> bool:
    """Whether PipeFunc runs out-of-process in this process (non-raising; defaults to local).

    Derived from the selected execution mode: core owns ``direct`` as the one in-process mode, and by
    the seam's invariant every other mode (``daytona``, …) is a remote/sandbox
    backend that transports the customer's source rather than importing it here. So library loading
    and the PipeFunc validators gate on this: ``True`` ⇒ capture source + skip callable inspection.
    """
    return get_pipe_func_execution_mode() != DIRECT_PIPE_FUNC_EXECUTION_MODE
