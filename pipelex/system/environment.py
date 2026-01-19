import os
from pathlib import Path

from dotenv import load_dotenv

from pipelex.system.exceptions import ToolError
from pipelex.tools.misc.placeholder import value_is_placeholder

load_dotenv(dotenv_path=".env", override=True)

# Environment variable for specifying library directories (PATH-style, colon-separated on Unix, semicolon on Windows)
PIPELEXPATH_ENV_KEY = "PIPELEXPATH"


class EnvVarNotFoundError(ToolError):
    pass


def get_required_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        msg = f"Environment variable '{key}' is required but not set"
        raise EnvVarNotFoundError(msg)
    return value


def get_optional_env(key: str) -> str | None:
    return os.getenv(key)


def is_env_var_set(key: str) -> bool:
    return os.getenv(key) is not None


def all_env_vars_are_set(keys: list[str]) -> bool:
    return all(is_env_var_set(each_key) for each_key in keys)


def any_env_var_is_placeholder(keys: list[str]) -> bool:
    for each_key in keys:
        env_value = os.getenv(each_key)
        if value_is_placeholder(env_value):
            return True
    return False


def set_env(key: str, value: str) -> None:
    os.environ[key] = value


def is_env_var_truthy(key: str) -> bool:
    """Return True if the env var is set and not a falsy sentinel ("false" or "0")."""
    value = get_optional_env(key)
    return (value is not None) and (value.lower() not in {"false", "0"})


def get_pipelexpath_dirs() -> list[Path] | None:
    """Get library directories from PIPELEXPATH environment variable.

    PIPELEXPATH uses PATH-style syntax: colon-separated on Unix, semicolon-separated on Windows.

    Returns:
        List of Path objects for each directory in PIPELEXPATH, or None if not set.
    """
    pipelexpath = get_optional_env(PIPELEXPATH_ENV_KEY)
    if pipelexpath is None:
        return None
    return [Path(path_str) for path_str in pipelexpath.split(os.pathsep) if path_str]
