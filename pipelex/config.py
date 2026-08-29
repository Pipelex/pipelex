from pipelex import log
from pipelex.plugins.pipe_func_executor_registry import DIRECT_PIPE_FUNC_EXECUTION_MODE
from pipelex.runtime_hub import get_optional_config, get_required_config
from pipelex.system.configuration.configs import PipelexConfig
from pipelex.system.environment import get_optional_env

METHODS_FETCH_ON_MISS_ENV_VAR = "PIPELEX_METHODS_FETCH_ON_MISS"

_ENV_TRUTHY = {"1", "true", "yes", "on"}
_ENV_FALSY = {"0", "false", "no", "off"}


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


def is_method_fetch_on_miss_enabled() -> bool:
    """Whether a missed address-based method reference may be fetched from the network (non-raising).

    The ``PIPELEX_METHODS_FETCH_ON_MISS`` environment variable overrides the config when set
    (``1``/``true``/``yes``/``on`` enables, ``0``/``false``/``no``/``off`` disables; an
    unrecognized value is warned about and ignored). Otherwise the answer is the config's
    ``interpreter.methods.fetch_on_miss``, defaulting to enabled when no config is set — safe to
    call from loading paths that may run before the global config exists.
    """
    raw_env = get_optional_env(METHODS_FETCH_ON_MISS_ENV_VAR)
    if raw_env is not None:
        normalized = raw_env.strip().lower()
        if normalized in _ENV_TRUTHY:
            return True
        if normalized in _ENV_FALSY:
            return False
        log.warning(f"Unrecognized {METHODS_FETCH_ON_MISS_ENV_VAR}={raw_env!r} (expected 1/0, true/false); falling back to the config")
    optional_config = get_optional_config()
    if not isinstance(optional_config, PipelexConfig):
        return True
    return optional_config.interpreter.methods.fetch_on_miss


def is_pipe_func_sandbox_hosted() -> bool:
    """Whether PipeFunc runs out-of-process in this process (non-raising; defaults to local).

    Derived from the selected execution mode: core owns ``direct`` as the one in-process mode, and by
    the seam's invariant every other mode (``daytona``, …) is a remote/sandbox
    backend that transports the customer's source rather than importing it here. So library loading
    and the PipeFunc validators gate on this: ``True`` ⇒ capture source + skip callable inspection.
    """
    return get_pipe_func_execution_mode() != DIRECT_PIPE_FUNC_EXECUTION_MODE
