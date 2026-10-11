"""What `pipelex usage-stats status` reports, read without changing anything: it creates, migrates and prints nothing else.

The JSON form is the contract's status object, field for field, which is how other tools and the conformance suite
read pipelex's statistics surface. The contract is `conformance/specs/usage-statistics.md`, "Commands".
"""

from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from pipelex.system.usage_stats.usage_stats_contract import NOTICE_VERSION, TOOL_NAME, UsageStatsOffBy
from pipelex.system.usage_stats.usage_stats_environment import is_ci, is_container
from pipelex.system.usage_stats.usage_stats_state import UsageStatsState
from pipelex.system.usage_stats.usage_stats_switches import read_switches


class UsageStatsStatus(BaseModel):
    """The status object of the contract: whether statistics are on, why not, and the shared facts they would carry."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool: str
    enabled: bool
    off_by: list[UsageStatsOffBy]
    installation_id: str | None
    notice_version: int
    internal: bool
    ci: bool
    container: bool
    state_dir: str


def read_usage_stats_status(*, state: UsageStatsState, env: Mapping[str, str], cwd: Path, is_pytest: bool) -> UsageStatsStatus:
    """Read every switch and the shared state as they are now, writing nothing."""
    off_by = read_switches(state=state, env=env, cwd=cwd, is_pytest=is_pytest)
    return UsageStatsStatus(
        tool=TOOL_NAME,
        enabled=not off_by,
        off_by=off_by,
        installation_id=state.read_installation_id(),
        notice_version=state.seen_notice_version(up_to=NOTICE_VERSION),
        internal=state.is_internal(),
        ci=is_ci(env=env),
        container=is_container(env=env),
        state_dir=str(state.state_dir),
    )


def describe_off_by(*, token: UsageStatsOffBy) -> str:
    """What a switch is, in words, for the text form of `status` and for `enable`."""
    match token:
        case UsageStatsOffBy.DO_NOT_TRACK:
            return "the DO_NOT_TRACK environment variable"
        case UsageStatsOffBy.TOOL_VARIABLE:
            return "the PIPELEX_USAGE_STATS environment variable"
        case UsageStatsOffBy.MACHINE_CHOICE:
            return "this machine's choice (`pipelex usage-stats disable`, or another tool's)"
        case UsageStatsOffBy.LEGACY_MTHDS_CHOICE:
            return "the telemetry setting of the mthds CLI in ~/.mthds/config"
        case UsageStatsOffBy.PROJECT_SETTING:
            return "this project's .pipelex/pipelex.toml ([usage_stats] enabled = false, or a file that cannot be read)"
        case UsageStatsOffBy.PACKAGED_DEFAULT:
            return "the configuration pipelex was packaged with"
        case UsageStatsOffBy.INTEGRATION_MODE:
            return "the pytest integration mode"
        case UsageStatsOffBy.INVALID_ENDPOINT_OVERRIDE:
            return "the PIPELEX_USAGE_STATS_ENDPOINT environment variable, which is not a loopback http origin"
