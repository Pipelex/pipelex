"""The switches that turn usage statistics off, read in the contract's order before a process does any work.

Statistics are on unless a switch says off, and no switch can turn them back on over another that says off. Every
switch is read, so `status` names each one that says off, in this order: `DO_NOT_TRACK`, `PIPELEX_USAGE_STATS`, the
shared `disabled` file, the legacy `mthds` opt-out newer than its migration, the project's `.pipelex/pipelex.toml`
(failing closed), pipelex's packaged configuration, the `pytest` integration mode, and an endpoint override that is not a
loopback origin. The contract is `conformance/specs/usage-statistics.md`, "Switches".
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import tomli

from pipelex.system.configuration.config_loader import CONFIG_NAME, ConfigLoader
from pipelex.system.environment import CONFIG_DIR_NAME
from pipelex.system.usage_stats.usage_stats_contract import SETTING_KEY, SETTING_TABLE, UsageStatsEnvVar, UsageStatsOffBy
from pipelex.system.usage_stats.usage_stats_core import UsageStatsState, path_exists
from pipelex.system.usage_stats.usage_stats_environment import is_truthy_flag, resolve_endpoint, tool_switch_says_off

#: pipelex's packaged configuration, which carries `[usage_stats] enabled = true`; a packager may ship `false`.
PACKAGED_CONFIG_PATH = Path(__file__).resolve().parents[2] / CONFIG_NAME


def setting_says_off(*, config_path: Path) -> bool:
    """Whether a configuration file's `[usage_stats] enabled` turns statistics off, failing closed.

    `false` says off, and so does a file that cannot be read, is not valid TOML, has a `usage_stats` that is not a
    table, or an `enabled` that is not a boolean. `true`, or no `enabled` at all, has no effect.
    """
    try:
        document = tomli.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomli.TOMLDecodeError):
        return True
    table: object = document.get(SETTING_TABLE)
    if table is None:
        return False
    if not isinstance(table, dict):
        return True
    enabled: object = cast("dict[str, Any]", table).get(SETTING_KEY)
    if enabled is None:
        return False
    if not isinstance(enabled, bool):
        return True
    return not enabled


def project_setting_says_off(*, cwd: Path) -> bool:
    """Whether the project's own `.pipelex/pipelex.toml` turns statistics off, read alone, never the merged configuration.

    The project is found the way pipelex finds its project configuration: from `cwd`, walking up to the first directory
    holding a project marker, stopping at the home directory, which is never a project, and at the filesystem root. So
    `~/.pipelex/pipelex.toml`, pipelex's home layer, is not a switch. No project, or no file there, means no setting;
    a project or a file that cannot be looked for is a file that cannot be read, which turns statistics off.
    """
    try:
        project_root = ConfigLoader.find_project_root(cwd)
    except (OSError, RuntimeError):
        # A directory on the way up that cannot be looked into, or no home directory to stop at: the project's file
        # cannot be read, which fails closed.
        return True
    if project_root is None:
        return False
    config_path = project_root / CONFIG_DIR_NAME / CONFIG_NAME
    config_exists = path_exists(path=config_path)
    if config_exists is None:
        # A file whose very existence cannot be told cannot be read either, which fails closed.
        return True
    if not config_exists:
        return False
    return setting_says_off(config_path=config_path)


def packaged_default_says_off(*, packaged_config_path: Path = PACKAGED_CONFIG_PATH) -> bool:
    """Whether pipelex's packaged configuration ships statistics off; a package that does not say `true` fails closed."""
    try:
        document = tomli.loads(packaged_config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomli.TOMLDecodeError):
        return True
    table: object = document.get(SETTING_TABLE)
    if not isinstance(table, dict):
        return True
    return cast("dict[str, Any]", table).get(SETTING_KEY) is not True


def read_switches(
    *,
    state: UsageStatsState,
    env: Mapping[str, str],
    cwd: Path,
    is_pytest: bool,
    packaged_config_path: Path = PACKAGED_CONFIG_PATH,
) -> list[UsageStatsOffBy]:
    """Every switch that says off, by its token, in the contract's order; empty when statistics are on.

    Read-only: the legacy migration, which every reporting process runs first, is the caller's to run, since `status`
    reads the switches without migrating anything.
    """
    off_by: list[UsageStatsOffBy] = []
    if is_truthy_flag(env=env, name=UsageStatsEnvVar.DO_NOT_TRACK):
        off_by.append(UsageStatsOffBy.DO_NOT_TRACK)
    if tool_switch_says_off(env=env):
        off_by.append(UsageStatsOffBy.TOOL_VARIABLE)
    if state.is_disabled():
        off_by.append(UsageStatsOffBy.MACHINE_CHOICE)
    if state.legacy_opt_out_is_pending():
        off_by.append(UsageStatsOffBy.LEGACY_MTHDS_CHOICE)
    if project_setting_says_off(cwd=cwd):
        off_by.append(UsageStatsOffBy.PROJECT_SETTING)
    if packaged_default_says_off(packaged_config_path=packaged_config_path):
        off_by.append(UsageStatsOffBy.PACKAGED_DEFAULT)
    if is_pytest:
        off_by.append(UsageStatsOffBy.INTEGRATION_MODE)
    if resolve_endpoint(env=env) is None:
        off_by.append(UsageStatsOffBy.INVALID_ENDPOINT_OVERRIDE)
    return off_by
