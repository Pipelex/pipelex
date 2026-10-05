import os
from pathlib import Path

from dotenv import load_dotenv

from pipelex.system.exceptions import EnvVarNotFoundError
from pipelex.tools.misc.placeholder import value_is_placeholder

# The name of a configuration directory, in the user's home directory and in a project
CONFIG_DIR_NAME = ".pipelex"

# Environment variable relocating the home configuration directory, which is ~/.pipelex otherwise
PIPELEX_HOME_ENV_KEY = "PIPELEX_HOME"

# Environment variable for specifying library directories (PATH-style, colon-separated on Unix, semicolon on Windows)
PIPELEXPATH_ENV_KEY = "PIPELEXPATH"


def get_pipelex_home_dir() -> Path:
    """The home configuration directory: `PIPELEX_HOME` when it is set and not empty, else `~/.pipelex`.

    This is the one place that locates it. The `.env` loaded below asks, and so does
    `ConfigLoader.global_config_dir`, through which every other reader goes, so the variable moves
    the configuration layers, the inference files and their overrides, the first-boot copy of the
    kit, `pipelex init` and `pipelex doctor` with `--global`, and `pipelex migrate` together.

    The variable names the directory itself, the equivalent of `~/.pipelex`, not its parent. `~` is
    expanded and a relative value resolves against the working directory.
    """
    configured_home = os.environ.get(PIPELEX_HOME_ENV_KEY)
    if not configured_home:
        return Path.home() / CONFIG_DIR_NAME
    return Path(configured_home).expanduser().resolve()


def _load_dotenv_files() -> None:
    """Load the home `.env`, then the project's `.env` from the working directory, which wins.

    `PIPELEX_HOME` is read from the process environment only. The home `.env` is found through it,
    so a `.env` that set it would leave the process reading its configuration from one directory and
    its credentials from another: whatever either file says about it is discarded. A relative value
    is pinned to the absolute path it resolves to at import, so that a later change of directory, or
    a subprocess started from elsewhere, finds the same home directory as this load did.
    """
    configured_home = os.environ.get(PIPELEX_HOME_ENV_KEY)
    home_dir = get_pipelex_home_dir()
    if configured_home and not Path(configured_home).is_absolute():
        configured_home = str(home_dir)

    home_env_path = home_dir / ".env"
    if home_env_path.is_file():
        load_dotenv(dotenv_path=str(home_env_path), override=True)
    load_dotenv(dotenv_path=".env", override=True)

    if configured_home is None:
        os.environ.pop(PIPELEX_HOME_ENV_KEY, None)
    else:
        os.environ[PIPELEX_HOME_ENV_KEY] = configured_home


_load_dotenv_files()


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
