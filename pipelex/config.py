from pipelex.hub import get_optional_config, get_required_config
from pipelex.system.configuration.configs import PipelexConfig
from pipelex.system.environment import get_optional_env

_SANDBOX_HOSTED_ENV = "PIPELEX_SANDBOX_HOSTED"
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def get_config() -> PipelexConfig:
    singleton_config = get_required_config()
    if not isinstance(singleton_config, PipelexConfig):
        msg = f"Expected {PipelexConfig}, but got {type(singleton_config)}"
        raise TypeError(msg)
    return singleton_config


def is_pipe_func_sandbox_hosted() -> bool:
    """Whether PipeFunc is sandbox-hosted in this process (non-raising; defaults to local).

    Read from the optional config so it is safe to call from pydantic validators that may run
    before the global config is set (e.g. very early boot or isolated unit tests). When no config
    is set, or it is not a PipelexConfig, the answer is False — i.e. local/direct behavior, which
    keeps the non-hosted path byte-identical to the pre-flag behavior.
    """
    # An env override wins over config so a deployment (or a multi-process local run — submitter +
    # worker) can flip hosted mode without editing a config file. Absent env → fall back to config.
    env_value = get_optional_env(_SANDBOX_HOSTED_ENV)
    if env_value is not None:
        return env_value.strip().lower() in _TRUTHY
    optional_config = get_optional_config()
    if not isinstance(optional_config, PipelexConfig):
        return False
    return optional_config.pipelex.pipe_func_config.is_sandbox_hosted
