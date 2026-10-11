"""What a process can tell about where it runs, read the way the usage-statistics contract reads it.

Every reader takes the environment as a mapping rather than reading `os.environ` itself, so a test hands it
the environment it means, and so the detached sender can read the same facts from the environment it was given.
Standard library only, for the reason `usage_stats_contract` gives.
"""

import platform
import re
import sys
from collections.abc import Mapping
from pathlib import Path

from pipelex.system.usage_stats.usage_stats_contract import (
    CAPTURE_HOST,
    CI_VARIABLES,
    CONTAINER_CGROUP_FILE,
    CONTAINER_CGROUP_WORDS,
    CONTAINER_MARKER_FILES,
    CONTAINER_MARKER_VARIABLES,
    FALSY_VALUES,
    RELEASE_VERSION_PATTERN,
    TOOL_SWITCH_NO_EFFECT_VALUES,
    UsageStatsArch,
    UsageStatsEnvVar,
    UsageStatsHost,
    UsageStatsOs,
)

#: A loopback `http` origin with a port and no path: the only endpoint override the contract accepts.
_LOOPBACK_ORIGIN = re.compile(r"^http://(127\.0\.0\.1|localhost|\[::1\]):([0-9]{1,5})$")
_LEADING_RELEASE = re.compile(r"^[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}")


def read_switch_value(*, env: Mapping[str, str], name: str) -> str | None:
    """A switch variable's value, trimmed and lowercased as the contract reads every one, or `None` when unset."""
    raw_value = env.get(name)
    if raw_value is None:
        return None
    return raw_value.strip().lower()


def is_truthy_flag(*, env: Mapping[str, str], name: str) -> bool:
    """Whether a variable read as `DO_NOT_TRACK` is set to anything but the values with no effect."""
    value = read_switch_value(env=env, name=name)
    return value is not None and value not in FALSY_VALUES


def tool_switch_says_off(*, env: Mapping[str, str]) -> bool:
    """Whether `PIPELEX_USAGE_STATS` turns statistics off: an off value, or any value nobody can read, failing closed."""
    value = read_switch_value(env=env, name=UsageStatsEnvVar.TOOL_SWITCH)
    return value is not None and value not in TOOL_SWITCH_NO_EFFECT_VALUES


def is_debug(*, env: Mapping[str, str]) -> bool:
    """Whether `PIPELEX_USAGE_STATS_DEBUG` asks for every event on stderr instead of sent."""
    return is_truthy_flag(env=env, name=UsageStatsEnvVar.DEBUG)


def resolve_endpoint(*, env: Mapping[str, str]) -> str | None:
    """The origin events are posted to: PostHog's capture host, or a loopback override; `None` for an override that is neither.

    `None` turns statistics off for the process (`invalid_endpoint_override`), so the variable can never send events
    anywhere but the project or the machine itself.
    """
    override = env.get(UsageStatsEnvVar.ENDPOINT_OVERRIDE)
    if override is None:
        return CAPTURE_HOST
    return override if is_loopback_origin(origin=override) else None


def is_loopback_origin(*, origin: str) -> bool:
    """Whether `origin` is `http://127.0.0.1:<port>`, `http://localhost:<port>` or `http://[::1]:<port>`, with no path."""
    match = _LOOPBACK_ORIGIN.fullmatch(origin)
    if match is None:
        return False
    port = int(match.group(2))
    return 0 < port < 65536


def is_ci(*, env: Mapping[str, str]) -> bool:
    """Whether any CI variable is set to anything but the empty string, `0` or `false`."""
    return any(is_truthy_flag(env=env, name=variable) for variable in CI_VARIABLES)


def is_container(*, env: Mapping[str, str]) -> bool:
    """Whether the process runs in a container: a marker file, a marker variable that is not empty, or PID 1's cgroup."""
    if any(Path(marker).exists() for marker in CONTAINER_MARKER_FILES):
        return True
    if any(env.get(variable, "").strip() for variable in CONTAINER_MARKER_VARIABLES):
        return True
    try:
        cgroup_text = Path(CONTAINER_CGROUP_FILE).read_text(encoding="utf-8", errors="replace")
    except OSError:
        # No such file outside Linux, or one this process may not read: no evidence of a container either way.
        return False
    return any(word in cgroup_text for word in CONTAINER_CGROUP_WORDS)


def declared_host(*, env: Mapping[str, str]) -> UsageStatsHost | None:
    """The host `PIPELEX_USAGE_STATS_HOST` declares: one of the contract's values, `other` for any other, `None` when unset or empty."""
    value = read_switch_value(env=env, name=UsageStatsEnvVar.HOST)
    if not value:
        return None
    try:
        return UsageStatsHost(value)
    except ValueError:
        return UsageStatsHost.OTHER


def current_os() -> UsageStatsOs:
    if sys.platform.startswith("linux"):
        return UsageStatsOs.LINUX
    if sys.platform == "darwin":
        return UsageStatsOs.DARWIN
    if sys.platform in {"win32", "cygwin"}:
        return UsageStatsOs.WINDOWS
    return UsageStatsOs.OTHER


def current_arch() -> UsageStatsArch:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64", "x64"}:
        return UsageStatsArch.X86_64
    if machine in {"arm64", "aarch64"}:
        return UsageStatsArch.ARM64
    return UsageStatsArch.OTHER


def current_language_runtime() -> str:
    return f"python-{sys.version_info.major}.{sys.version_info.minor}"


def release_version(*, version: str) -> str:
    """The version as the `release_version` pattern admits it: as it is when it matches, else its leading three numbers.

    A build from a checkout can carry a local segment (`0.74.0+g1a2b3c`), which the pattern refuses so that no path or
    hash can ride the version; the release it was built from is what the property means.
    """
    if re.fullmatch(RELEASE_VERSION_PATTERN, version):
        return version
    leading = _LEADING_RELEASE.match(version)
    return leading.group(0) if leading else "0.0.0"
