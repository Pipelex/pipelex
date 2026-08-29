"""Centralized, env-tunable ceilings for fetched method packages.

A fetched package is content this process pulled from a remote repository, so its size is
bounded here rather than trusted. Values are read once at import time — a change requires
a process restart. The pattern mirrors the request-size ceilings of `pipelex-api`.
"""

from pipelex import log
from pipelex.system.environment import get_optional_env

DEFAULT_MAX_FETCHED_PACKAGE_FILES = 256
DEFAULT_MAX_FETCHED_PACKAGE_TOTAL_KIB = 8 * 1024  # 8 MiB across the selected package


def _read_positive_int(*, env_var: str, default: int) -> int:
    raw = get_optional_env(env_var)
    if not raw:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        log.warning(f"Invalid {env_var}={raw!r}, falling back to {default}")
        return default
    if parsed <= 0:
        log.warning(f"{env_var} must be positive (got {parsed}), falling back to {default}")
        return default
    return parsed


MAX_FETCHED_PACKAGE_FILES = _read_positive_int(env_var="PIPELEX_MAX_FETCHED_PACKAGE_FILES", default=DEFAULT_MAX_FETCHED_PACKAGE_FILES)
MAX_FETCHED_PACKAGE_TOTAL_BYTES = (
    _read_positive_int(env_var="PIPELEX_MAX_FETCHED_PACKAGE_TOTAL_KIB", default=DEFAULT_MAX_FETCHED_PACKAGE_TOTAL_KIB) * 1024
)
