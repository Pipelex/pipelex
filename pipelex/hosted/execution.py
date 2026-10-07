"""Where a run executes: the `--hosted`/`--local` flag, then the `[run] execution` setting.

Both CLIs call `resolve_run_execution` before they boot anything, because the answer decides what to boot: a
local run boots the runtime with its inference, a hosted run boots nothing and talks to the hosted API.
"""

from pipelex.core.validation import raise_config_setup_error
from pipelex.hosted.run_config import RunExecution
from pipelex.runtime_hub import get_optional_config
from pipelex.system.configuration.config_loader import CONFIG_REFUSED, config_manager
from pipelex.system.configuration.config_surface import PIPELEX_CONFIG_SURFACE_ID
from pipelex.system.configuration.configs import PipelexConfig


def get_or_load_pipelex_config() -> PipelexConfig:
    """The booted configuration when a boot holds one, else the same layers read and validated without booting.

    A hosted run never boots the runtime, so it reads its settings the way a boot would: the package defaults, the
    home configuration directory, then the project's `.pipelex/`, project over home.

    Raises:
        PipelexConfigError: If the configuration files do not validate, with what a `pipelex migrate` would find.
    """
    booted = get_optional_config()
    if isinstance(booted, PipelexConfig):
        return booted
    try:
        return config_manager.load_config_validated(config_cls=PipelexConfig)
    except CONFIG_REFUSED as config_error:
        raise_config_setup_error(config_error=config_error, surface_id=PIPELEX_CONFIG_SURFACE_ID)


def configured_run_execution() -> RunExecution:
    """The `[run] execution` setting: the project's `.pipelex/pipelex.toml` over the home one over the packaged `local`."""
    return get_or_load_pipelex_config().run.execution


def resolve_run_execution(*, requested: RunExecution | None) -> RunExecution:
    """Where this run executes: the execution the command requested, else the configured default.

    Args:
        requested: The execution the command's flags name (`--hosted`, `--local`, or `--runner` on the agent CLI),
            or `None` when they name none.

    Returns:
        The execution to use. A requested one never reads the configuration.
    """
    if requested is not None:
        return requested
    return configured_run_execution()
