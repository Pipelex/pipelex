"""Centralized, env-tunable size limits for incoming requests.

Every endpoint that accepts user-supplied content bounds it via constants
imported from this module. Values are read once at import time — change
requires a process restart.
"""

from pipelex import log
from pipelex.system.environment import get_optional_env

DEFAULT_MAX_REQUEST_BODY_MIB = 100
DEFAULT_MAX_MTHDS_FILE_KIB = 1024  # 1 MiB per .mthds file
DEFAULT_MAX_MTHDS_FILES_PER_REQUEST = 16
DEFAULT_MAX_PIPE_CODE_LEN = 256
MAX_METHOD_REF_LEN = 512  # `method_ref` selector strings; a fixed schema bound, not env-tunable
DEFAULT_MAX_CALLBACK_URLS = 5
DEFAULT_MAX_CALLBACK_URL_LEN = 2048
DEFAULT_MAX_AGENT_SPEC_KIB = 256  # 256 KiB for JSON concept/pipe specs
DEFAULT_MAX_BUNDLE_FILES = 128  # entries in a materialized method bundle (.mthds + .py + requirements.txt)
DEFAULT_MAX_BUNDLE_TOTAL_KIB = 8 * 1024  # 8 MiB decompressed across the whole bundle (zip-bomb guard)
DEFAULT_MAX_METHOD_CACHE_CLONES = 64  # cached method-package clones (one per resolved commit SHA)
DEFAULT_MAX_METHOD_CACHE_TOTAL_KIB = 512 * 1024  # 512 MiB across all cached clones
DEFAULT_MAX_METHOD_CACHE_AGE_HOURS = 24  # a cached clone unused for this long is evicted


def _read_positive_int(env_var: str, default: int) -> int:
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


MAX_REQUEST_BODY_MIB = _read_positive_int("MAX_REQUEST_BODY_MIB", DEFAULT_MAX_REQUEST_BODY_MIB)
MAX_REQUEST_BODY_BYTES = MAX_REQUEST_BODY_MIB * 1024 * 1024

MAX_MTHDS_FILE_BYTES = _read_positive_int("MAX_MTHDS_FILE_KIB", DEFAULT_MAX_MTHDS_FILE_KIB) * 1024
MAX_MTHDS_FILES_PER_REQUEST = _read_positive_int("MAX_MTHDS_FILES_PER_REQUEST", DEFAULT_MAX_MTHDS_FILES_PER_REQUEST)
MAX_PIPE_CODE_LEN = _read_positive_int("MAX_PIPE_CODE_LEN", DEFAULT_MAX_PIPE_CODE_LEN)

MAX_CALLBACK_URLS = _read_positive_int("MAX_CALLBACK_URLS", DEFAULT_MAX_CALLBACK_URLS)
MAX_CALLBACK_URL_LEN = _read_positive_int("MAX_CALLBACK_URL_LEN", DEFAULT_MAX_CALLBACK_URL_LEN)

MAX_AGENT_SPEC_BYTES = _read_positive_int("MAX_AGENT_SPEC_KIB", DEFAULT_MAX_AGENT_SPEC_KIB) * 1024

MAX_BUNDLE_FILES = _read_positive_int("MAX_BUNDLE_FILES", DEFAULT_MAX_BUNDLE_FILES)
MAX_BUNDLE_TOTAL_BYTES = _read_positive_int("MAX_BUNDLE_TOTAL_KIB", DEFAULT_MAX_BUNDLE_TOTAL_KIB) * 1024

MAX_METHOD_CACHE_CLONES = _read_positive_int("MAX_METHOD_CACHE_CLONES", DEFAULT_MAX_METHOD_CACHE_CLONES)
MAX_METHOD_CACHE_TOTAL_BYTES = _read_positive_int("MAX_METHOD_CACHE_TOTAL_KIB", DEFAULT_MAX_METHOD_CACHE_TOTAL_KIB) * 1024
MAX_METHOD_CACHE_AGE_SECONDS = _read_positive_int("MAX_METHOD_CACHE_AGE_HOURS", DEFAULT_MAX_METHOD_CACHE_AGE_HOURS) * 3600
