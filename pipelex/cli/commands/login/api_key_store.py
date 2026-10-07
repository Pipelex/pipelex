"""Where `pipelex login` keeps the Pipelex API key, and where `pipelex init` looks for one already set.

The key is saved as `PIPELEX_API_KEY` in the `.env` of the home configuration directory (`~/.pipelex/.env`, or under
`PIPELEX_HOME`), the file the runtime loads into the environment at import, so a hosted run finds it with nothing
exported. The file keeps its other lines and is readable by its owner only.
"""

import os
from pathlib import Path

from pipelex.cli.commands.init.credentials import get_global_env_path, read_env_file_value, set_env_file_entry
from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY


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

    The runtime loads the home `.env` into the environment at import, so the second read only matters when the file
    was written after that, or under a `PIPELEX_HOME` set since.
    """
    from_environment = os.environ.get(PIPELEX_API_KEY_ENV_KEY)
    if from_environment:
        return from_environment
    return read_saved_pipelex_api_key()
