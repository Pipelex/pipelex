"""Where `pipelex login` keeps the Pipelex API key, and where `pipelex init` looks for one already set.

The key is saved as `PIPELEX_API_KEY` in the `.env` of the home configuration directory (`~/.pipelex/.env`, or under
`PIPELEX_HOME`), the file the runtime loads into the environment at import, so a hosted run finds it with nothing
exported. The file keeps its other lines and is readable by its owner only.

The runtime then loads the working directory's `.env`, which wins: a `PIPELEX_API_KEY` line there, even an empty one,
is what every command run in that directory sends, whatever the home file holds.
"""

import os
from pathlib import Path
from typing import NamedTuple

from dotenv import dotenv_values

from pipelex.cli.commands.init.credentials import get_global_env_path, read_env_file_value, set_env_file_entry
from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY

#: The working directory's `.env`, which the runtime loads after the home one (see `pipelex.system.environment`).
WORKING_DIRECTORY_ENV_FILE_NAME = ".env"


def save_pipelex_api_key(*, api_key: str) -> Path:
    """Save the key as `PIPELEX_API_KEY` in the home `.env`, and set it in this process's environment.

    Args:
        api_key: A Pipelex API key, already checked to be well formed.

    Returns:
        The file it was saved to.
    """
    env_path = get_global_env_path()
    set_env_file_entry(env_path=env_path, key=PIPELEX_API_KEY_ENV_KEY, value=api_key)
    # The rest of this command, init's later steps included, sees the key as a new process would.
    os.environ[PIPELEX_API_KEY_ENV_KEY] = api_key
    return env_path


def read_saved_pipelex_api_key() -> str | None:
    """The key saved in the home `.env`, or `None` when it holds none."""
    return read_env_file_value(env_path=get_global_env_path(), key=PIPELEX_API_KEY_ENV_KEY)


def find_pipelex_api_key() -> str | None:
    """The key a hosted run would use: `PIPELEX_API_KEY` in the environment, else the one saved in the home `.env`.

    A variable present in the environment decides, even when empty: an empty value is what the next process sends, so it
    is no key, and the saved one is not looked at. The runtime loads the home `.env` into the environment at import, so
    the saved key only matters when the file was written after that, or under a `PIPELEX_HOME` set since.
    """
    if PIPELEX_API_KEY_ENV_KEY in os.environ:
        return os.environ[PIPELEX_API_KEY_ENV_KEY] or None
    return read_saved_pipelex_api_key()


class ShadowingEnvFile(NamedTuple):
    """The working directory's `.env`, when its `PIPELEX_API_KEY` line overrides the saved key."""

    path: Path
    #: Whether it sets the variable to an empty value, rather than to another key.
    sets_empty_value: bool


def find_shadowing_env_file() -> ShadowingEnvFile | None:
    """The working directory's `.env` when it sets `PIPELEX_API_KEY` to something other than the key saved in the home `.env`.

    The runtime loads that file after the home one, both overriding, so its value, an empty one included, is what every
    command run in this directory sends. A key set there alone, with none saved, is that directory's key and shadows
    nothing. Neither value is returned.
    """
    working_env_path = Path(WORKING_DIRECTORY_ENV_FILE_NAME).resolve()
    if not working_env_path.is_file() or working_env_path == get_global_env_path().resolve():
        return None
    values = dotenv_values(working_env_path)
    if PIPELEX_API_KEY_ENV_KEY not in values:
        return None
    working_value = values[PIPELEX_API_KEY_ENV_KEY] or ""
    saved_key = read_saved_pipelex_api_key()
    if working_value and (saved_key is None or working_value == saved_key):
        return None
    return ShadowingEnvFile(path=working_env_path, sets_empty_value=not working_value)
